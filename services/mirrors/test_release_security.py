import asyncio
import hashlib
import hmac
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

_import_data = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _import_data.name
os.environ["SESSION_SECRET_FILE"] = str(Path(_import_data.name) / "missing-session-secret")

import app
import release_events
from fastapi import UploadFile
from fastapi.testclient import TestClient


class ReleaseSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        config = patch.multiple(app, DATA_DIR=root, FILES_DIR=root / "files", DB_PATH=root / "mirror.db",
                                STORAGE_PROVIDER="local", EDGE_DOWNLOAD_BASE="")
        config.start()
        self.addCleanup(config.stop)
        storage = patch.object(app, "s3_client", return_value=None)
        storage.start()
        self.addCleanup(storage.stop)
        app.init_db()
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)
        self.user = {"sub": "owner", "preferred_username": "owner", "csrf": "test-csrf"}
        self.client.cookies.set("mirror_session", app.serializer.dumps(self.user))
        self.api_token = "mdp_test-only-release-token"
        with app.db() as con:
            self.team = con.execute("INSERT INTO teams(slug,name,owner_sub,created_at) VALUES('test-team','Test','owner',0)").lastrowid
            con.execute("INSERT INTO team_members(team_id,user_sub,role,created_at) VALUES(?,'owner','owner',0)", (self.team,))
            self.project = con.execute("""INSERT INTO projects(slug,name,summary,team_id,visibility,created_at,updated_at)
                VALUES('test-project','Test project','Synthetic fixture',?,'public',0,0)""", (self.team,)).lastrowid
            con.execute("""INSERT INTO developer_tokens(team_id,token_hash,created_by,created_at)
                VALUES(?,?,'owner',0)""", (self.team, hashlib.sha256(self.api_token.encode()).hexdigest()))

    def upload(self, content=b"new draft", channel="stable", version="1.0", filename="package.zip", api=False):
        return self.client.post("/api/v1/developer/releases/upload" if api else "/developer/releases",
            data={"project_slug": "test-project", "version": version, "channel": channel, "csrf_token": "test-csrf"},
            files={"upload": (filename, content, "application/octet-stream")},
            headers={"Authorization": f"Bearer {self.api_token}"} if api else {}, follow_redirects=False)

    def admin_upload(self, content=b"admin release", channel="stable", version="1.0", filename="package.zip"):
        self.client.cookies.set("mirror_session", app.serializer.dumps({**self.user, "is_superuser": True}))
        return self.client.post("/admin/releases",
            data={"project_slug": "test-project", "version": version, "channel": channel, "csrf_token": "test-csrf"},
            files={"upload": (filename, content, "application/octet-stream")}, follow_redirects=False)

    def artifacts(self):
        with app.db() as con:
            return [dict(row) for row in con.execute("""SELECT a.*,r.status,r.channel FROM artifacts a
                JOIN releases r ON r.id=a.release_id WHERE r.project_id=? ORDER BY a.id""", (self.project,))]

    def download(self, artifact):
        token = app.serializer.dumps({"purpose": "machine-download", "artifact_id": artifact["id"]})
        return self.client.get(f"/api/v1/download/{artifact['id']}", params={"token": token, "source": "international"})

    def assert_artifact_bytes(self, artifact, content):
        response = self.download(artifact)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, content)
        self.assertEqual(response.headers["x-checksum-sha256"], hashlib.sha256(content).hexdigest())
        self.assertIn('filename="package.zip"', response.headers["content-disposition"])

    def publish(self, artifact):
        with app.db() as con:
            con.execute("UPDATE releases SET status='published' WHERE id=?", (artifact["release_id"],))

    def test_web_draft_in_another_channel_cannot_overwrite_published_file(self):
        self.assertEqual(self.upload(b"published").status_code, 303)
        original = self.artifacts()[0]
        self.publish(original)
        self.assertEqual(self.upload(b"unapproved", channel="beta").status_code, 303)
        first, second = self.artifacts()
        self.assertNotEqual(first["local_path"], second["local_path"])
        self.assertEqual(first["status"], "published")
        self.assertEqual(second["status"], "draft")
        self.assert_artifact_bytes(first, b"published")
        self.assertEqual(self.download(second).status_code, 404)

    def test_repeated_web_draft_keeps_each_artifact_immutable(self):
        self.assertEqual(self.upload(b"first").status_code, 303)
        self.assertEqual(self.upload(b"second").status_code, 303)
        first, second = self.artifacts()
        self.assertNotEqual(first["local_path"], second["local_path"])
        self.publish(second)
        self.assert_artifact_bytes(first, b"first")
        self.assert_artifact_bytes(second, b"second")

    def test_concurrent_uploads_use_distinct_complete_files(self):
        async def run():
            async def save(content):
                chunks = iter((content, b""))
                async def read(_):
                    await asyncio.sleep(0)
                    return next(chunks)
                upload = Mock(filename="package.zip", read=read)
                return await app.store_release_upload(upload, "test-project", "1.0")
            return await asyncio.gather(save(b"first"), save(b"second"))
        first, second = asyncio.run(run())
        self.assertNotEqual(first[-1], second[-1])
        self.assertEqual((app.FILES_DIR / first[-1]).read_bytes(), b"first")
        self.assertEqual((app.FILES_DIR / second[-1]).read_bytes(), b"second")

    def test_api_uploads_remain_randomized_and_keep_response_contract(self):
        for content, channel in [(b"api-stable", "stable"), (b"api-beta", "beta")]:
            response = self.upload(content, channel=channel, api=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"], {"project": "test-project", "version": "1.0",
                "channel": channel, "status": "draft", "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content), "storage": "local"})
        first, second = self.artifacts()
        self.assertNotEqual(first["local_path"], second["local_path"])
        self.publish(first)
        self.assert_artifact_bytes(first, b"api-stable")

    def test_existing_fixed_path_artifact_and_checksum_still_download(self):
        legacy = app.FILES_DIR / "test-project" / "1.0" / "package.zip"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"legacy")
        with app.db() as con:
            release = con.execute("""INSERT INTO releases(project_id,version,channel,published_at,status)
                VALUES(?,'1.0','stable',0,'published')""", (self.project,)).lastrowid
            con.execute("""INSERT INTO artifacts(release_id,filename,local_path,size,sha256,created_at)
                VALUES(?,'package.zip',?,6,?,0)""", (release, str(legacy.relative_to(app.FILES_DIR)), hashlib.sha256(b"legacy").hexdigest()))
        self.assertEqual(self.upload(b"new beta", channel="beta").status_code, 303)
        self.assertEqual(self.admin_upload(b"admin alpha", channel="alpha").status_code, 303)
        self.assert_artifact_bytes(self.artifacts()[0], b"legacy")

    def test_admin_repeated_and_cross_channel_publications_preserve_prior_bytes(self):
        for content, channel in ((b"first", "stable"), (b"second", "stable"), (b"beta", "beta")):
            self.assertEqual(self.admin_upload(content, channel=channel).status_code, 303)
        artifacts = self.artifacts()
        self.assertEqual(len({item["local_path"] for item in artifacts}), 3)
        for artifact, content in zip(artifacts, (b"first", b"second", b"beta")):
            self.assertEqual(artifact["status"], "published")
            self.assert_artifact_bytes(artifact, content)

    def test_admin_paths_cannot_follow_old_project_directory_symlink(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "package.zip").write_bytes(b"untouched")
        (app.FILES_DIR / "test-project").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.admin_upload(version="..", filename="../../package.zip").status_code, 303)
        artifact = self.artifacts()[0]
        self.assertEqual((app.FILES_DIR / artifact["local_path"]).parent, app.FILES_DIR)
        self.assertEqual((outside / "package.zip").read_bytes(), b"untouched")
        self.assert_artifact_bytes(artifact, b"admin release")

    def test_admin_storage_stays_local_and_failed_upload_preserves_published_file(self):
        with patch.object(app, "s3_client", side_effect=AssertionError("Admin uploads remain local")):
            self.assertEqual(self.admin_upload(b"published").status_code, 303)
        original = self.artifacts()[0]
        self.assertEqual(original["storage_provider"], "local")
        before = set(app.FILES_DIR.iterdir())
        with patch.object(app, "MAX_UPLOAD", 3):
            self.assertEqual(self.admin_upload(b"too big").status_code, 413)
        self.assertEqual(set(app.FILES_DIR.iterdir()), before)
        self.assert_artifact_bytes(original, b"published")

    def test_storage_paths_ignore_filename_and_version_directories(self):
        for version in ("..", ".", "../../escape"):
            with self.subTest(version=version):
                self.assertEqual(self.upload(version=version, filename="../../package.zip").status_code, 303)
        for artifact in self.artifacts():
            self.assertEqual(artifact["filename"], "package.zip")
            path = app.FILES_DIR / artifact["local_path"]
            self.assertEqual(path.parent, app.FILES_DIR)
            self.assertTrue(path.name.startswith("artifact-"))

    def test_exclusive_storage_does_not_follow_existing_file_or_symlink(self):
        victim = app.FILES_DIR / "artifact-existing"
        victim.write_bytes(b"unchanged")
        symlink = app.FILES_DIR / "artifact-link"
        symlink.symlink_to(victim)
        with patch.object(app.tempfile, "_get_candidate_names", return_value=iter(["existing", "link", "new"])):
            result = asyncio.run(app.store_release_upload(UploadFile(io.BytesIO(b"draft"), filename="package.zip"), "test-project", "1.0"))
        self.assertEqual(result[-1], "artifact-new")
        self.assertEqual(victim.read_bytes(), b"unchanged")
        self.assertTrue(symlink.is_symlink())

    def test_oversize_uploads_clean_up_without_changing_existing_artifacts(self):
        self.assertEqual(self.upload(b"published").status_code, 303)
        original = self.artifacts()[0]
        self.publish(original)
        before = set(app.FILES_DIR.iterdir())
        for api in (False, True):
            with self.subTest(api=api), patch.object(app, "MAX_UPLOAD", 3):
                self.assertEqual(self.upload(b"too large", channel="beta", api=api).status_code, 413)
                self.assertEqual(set(app.FILES_DIR.iterdir()), before)
                self.assertEqual(len(self.artifacts()), 1)
        self.assert_artifact_bytes(original, b"published")

    def test_read_error_and_cancellation_remove_partial_files(self):
        for error in (OSError("synthetic read failure"), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                upload = Mock(filename="package.zip", read=AsyncMock(side_effect=[b"partial", error]))
                before = set(app.FILES_DIR.iterdir())
                with self.assertRaises(type(error)):
                    asyncio.run(app.store_release_upload(upload, "test-project", "1.0"))
                self.assertEqual(set(app.FILES_DIR.iterdir()), before)

    def test_failed_storage_finalization_removes_partial_file(self):
        before = set(app.FILES_DIR.iterdir())
        with patch.object(app, "finalize_hosted_file", side_effect=RuntimeError("synthetic storage failure")):
            with self.assertRaises(RuntimeError):
                asyncio.run(app.store_release_upload(UploadFile(io.BytesIO(b"draft"), filename="package.zip"), "test-project", "1.0"))
        self.assertEqual(set(app.FILES_DIR.iterdir()), before)

    def test_database_failure_removes_new_local_file_and_rolls_back(self):
        self.assertEqual(self.upload(b"published").status_code, 303)
        original = self.artifacts()[0]
        self.publish(original)
        before = set(app.FILES_DIR.iterdir())
        for api in (False, True):
            with self.subTest(api=api), patch.object(app, "audit", side_effect=sqlite3.OperationalError("synthetic db failure")):
                with self.assertRaises(sqlite3.OperationalError):
                    self.upload(b"uncommitted", channel="beta", api=api)
                self.assertEqual(set(app.FILES_DIR.iterdir()), before)
                self.assertEqual(len(self.artifacts()), 1)
        self.assert_artifact_bytes(original, b"published")

    def test_s3_finalization_preserves_random_keys_and_cleans_local_staging(self):
        client = Mock()
        captured = []
        client.upload_file.side_effect = lambda path, bucket, key, **kwargs: captured.append((key, Path(path).read_bytes()))
        before = set(app.FILES_DIR.iterdir())
        with patch.object(app, "s3_client", return_value=client):
            for api in (False, True):
                response = self.upload(b"s3 content", api=api)
                self.assertEqual(response.status_code, 200 if api else 303)
        first, second = self.artifacts()
        self.assertEqual(first["storage_provider"], "s3")
        self.assertEqual(first["local_path"], "")
        self.assertNotEqual(first["storage_key"], second["storage_key"])
        self.assertEqual(captured, [(first["storage_key"], b"s3 content"), (second["storage_key"], b"s3 content")])
        self.assertEqual(set(app.FILES_DIR.iterdir()), before)

    def approve_with_mock_delivery(self, visibility, hook=False):
        self.assertEqual(self.upload().status_code, 303)
        release = self.artifacts()[0]["release_id"]
        with app.db() as con:
            con.execute("UPDATE projects SET visibility=? WHERE id=?", (visibility, self.project))
            if hook:
                con.execute("INSERT INTO project_webhooks(project_id,url,secret,created_at) VALUES(?,'https://hook.example.invalid/events','hook-test-secret',0)", (self.project,))
        client = AsyncMock()
        client.post.return_value = Mock(status_code=200)
        client.__aenter__.return_value = client
        with patch.object(app.httpx, "AsyncClient", return_value=client) as client_factory:
            response = self.client.post(f"/developer/releases/{release}/approve", data={"csrf_token": "test-csrf"}, follow_redirects=False)
        client_factory.assert_not_called()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.artifacts()[0]["status"], "published")
        client.post.assert_not_awaited()
        asyncio.run(release_events.deliver_pending_events(app.db, client=client, hub_url=app.HUB_EVENT_URL,
            hub_secret=lambda: "hub-test-secret", validate_url=Mock(side_effect=lambda value: value)))
        return client

    def test_private_release_is_published_without_hub_broadcast(self):
        client = self.approve_with_mock_delivery("private")
        client.post.assert_not_awaited()

    def test_private_release_keeps_project_scoped_webhook(self):
        client = self.approve_with_mock_delivery("private", hook=True)
        client.post.assert_awaited_once()
        call = client.post.call_args
        self.assertEqual(call.args[0], "https://hook.example.invalid/events")
        event = json.loads(call.kwargs["content"])
        self.assertEqual(event["audience"], "private")
        self.assertEqual(event["visibility"], "private")
        with app.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM webhook_deliveries WHERE status='delivered'").fetchone()[0], 1)

    def test_public_release_keeps_signed_hub_and_project_notifications(self):
        client = self.approve_with_mock_delivery("public", hook=True)
        self.assertEqual(client.post.await_count, 2)
        hub_call = client.post.call_args_list[0]
        self.assertEqual(hub_call.args[0], app.HUB_EVENT_URL)
        event = json.loads(hub_call.kwargs["content"])
        self.assertEqual(event["audience"], "users")
        self.assertEqual(event["visibility"], "public")
        signature = hmac.new(b"hub-test-secret", hub_call.kwargs["content"], hashlib.sha256).hexdigest()
        self.assertEqual(hub_call.kwargs["headers"]["x-matchall-signature"], f"sha256={signature}")

    def test_missing_visibility_fails_closed_for_hub_broadcast(self):
        client = AsyncMock()
        self.assertEqual(self.upload().status_code, 303)
        release = self.artifacts()[0]["release_id"]
        with app.db() as con:
            con.execute("UPDATE releases SET status='published' WHERE id=?", (release,))
            release_events.enqueue_release_event(con, {"id": self.project, "slug": "test-project", "name": "Test"},
                release, "1.0", "stable", app.BASE_URL, 100)
        asyncio.run(release_events.deliver_pending_events(app.db, client=client, hub_url=app.HUB_EVENT_URL,
            hub_secret=lambda: "hub-test-secret", validate_url=Mock(side_effect=lambda value: value)))
        client.post.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
