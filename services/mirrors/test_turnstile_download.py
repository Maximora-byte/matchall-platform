import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

_tmp = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _tmp.name
os.environ["SESSION_SECRET_FILE"] = str(Path(_tmp.name) / "session.secret")
os.environ["TURNSTILE_SITE_KEY"] = "1x00000000000000000000AA"
os.environ["TURNSTILE_SECRET_FILE"] = str(Path(_tmp.name) / "turnstile.secret")
os.environ["EDGE_DOWNLOAD_BASE"] = "https://edge.example.invalid"
os.environ["EDGE_DOWNLOAD_SECRET_FILE"] = str(Path(_tmp.name) / "edge.secret")
os.environ["EDGE_CN_CIDRS_FILE"] = str(Path(_tmp.name) / "cn-cidrs.txt")
os.environ["EDGE_ROLLOUT_PERCENT"] = "100"
os.environ["EDGE_HEALTH_FILE"] = str(Path(_tmp.name) / "edge-health.ok")
Path(os.environ["SESSION_SECRET_FILE"]).write_text("test-session-secret")
Path(os.environ["TURNSTILE_SECRET_FILE"]).write_text("1x0000000000000000000000000000000AA")
Path(os.environ["EDGE_DOWNLOAD_SECRET_FILE"]).write_text("test-edge-secret")
Path(os.environ["EDGE_CN_CIDRS_FILE"]).write_text("1.0.1.0/24\n240e::/16\n")
Path(os.environ["EDGE_HEALTH_FILE"]).write_text("ok")

import app
from fastapi.testclient import TestClient


class TurnstileDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app.app)
        now = 1_700_000_000
        with app.db() as con:
            con.execute("INSERT INTO projects(slug,name,summary,description,homepage,license,icon,public,created_at,updated_at,access_mode,visibility) VALUES('demo','Demo','Demo','','','','D',1,?,?, 'free','public')", (now, now))
            project_id = con.execute("SELECT id FROM projects WHERE slug='demo'").fetchone()[0]
            con.execute("INSERT INTO releases(project_id,version,channel,notes,published_at,status) VALUES(?, '1.0','stable','',?,'published')", (project_id, now))
            release_id = con.execute("SELECT id FROM releases WHERE project_id=?", (project_id,)).fetchone()[0]
            target = Path(_tmp.name) / "files" / "demo.bin"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"demo")
            con.execute("INSERT INTO artifacts(release_id,filename,local_path,size,sha256,created_at,storage_provider) VALUES(?, 'demo.bin','demo.bin',4,?,?,'local')", (release_id, "sha", now))
            cls.artifact_id = con.execute("SELECT id FROM artifacts WHERE release_id=?", (release_id,)).fetchone()[0]

    def test_web_download_requires_turnstile_and_grant_is_single_use(self):
        response = self.client.get(f"/download/{self.artifact_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cf-turnstile", response.text)
        with patch.object(app, "verify_turnstile", return_value=True):
            verified = self.client.post(f"/download/{self.artifact_id}/verify", data={"cf-turnstile-response": "ok"}, follow_redirects=False)
        self.assertEqual(verified.status_code, 303)
        location = verified.headers["location"]
        first = self.client.get(location)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.content, b"demo")
        second = self.client.get(location)
        self.assertEqual(second.status_code, 200)
        self.assertIn("cf-turnstile", second.text)

    def test_latest_api_uses_short_lived_machine_route(self):
        anonymous = self.client.get("/api/v1/projects/demo/latest").json()["data"]
        self.assertEqual(urlparse(anonymous["download_url"]).path, f"/download/{self.artifact_id}")
        raw_token = "mat_test-token"
        now = 1_700_000_000
        with app.db() as con:
            con.execute("INSERT OR REPLACE INTO users(sub,username,email,created_at,updated_at) VALUES('test-user','test','test@example.invalid',?,?)", (now, now))
            con.execute("INSERT INTO api_tokens(user_sub,token_hash,label,created_at) VALUES('test-user',?,'test',?)", (__import__('hashlib').sha256(raw_token.encode()).hexdigest(), now))
        latest = self.client.get("/api/v1/projects/demo/latest", headers={"Authorization": f"Bearer {raw_token}"}).json()["data"]
        parsed = urlparse(latest["download_url"])
        self.assertEqual(parsed.path, f"/api/v1/download/{self.artifact_id}")
        token = parse_qs(parsed.query)["token"][0]
        response = self.client.get(f"{parsed.path}?token={token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"demo")
        self.assertEqual(self.client.get(f"{parsed.path}?token=bad").status_code, 403)

    def test_turnstile_failure_does_not_issue_grant(self):
        with patch.object(app, "verify_turnstile", return_value=False):
            response = self.client.post(f"/download/{self.artifact_id}/verify", data={"cf-turnstile-response": "bad"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("验证未通过", response.text)

    def test_cn_client_redirects_to_signed_edge_and_other_clients_stay_local(self):
        cn = self.client.get(f"/api/v1/download/{self.artifact_id}", params={"token": app.serializer.dumps({"purpose": "machine-download", "artifact_id": self.artifact_id})}, headers={"X-Mirror-Client-IP": "1.0.1.8"}, follow_redirects=False)
        self.assertEqual(cn.status_code, 302)
        self.assertTrue(cn.headers["location"].startswith("https://edge.example.invalid/artifact/"))
        self.assertEqual(cn.headers["x-mirror-source"], "cn-edge")
        other = self.client.get(f"/api/v1/download/{self.artifact_id}", params={"token": app.serializer.dumps({"purpose": "machine-download", "artifact_id": self.artifact_id})}, headers={"X-Mirror-Client-IP": "8.8.8.8"})
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.content, b"demo")

    def test_cn_client_can_force_international_origin(self):
        token = app.serializer.dumps({"purpose": "machine-download", "artifact_id": self.artifact_id})
        response = self.client.get(
            f"/api/v1/download/{self.artifact_id}",
            params={"token": token, "source": "international"},
            headers={"X-Mirror-Client-IP": "1.0.1.8"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"demo")
        self.assertNotIn("x-mirror-source", response.headers)

    def test_international_source_survives_turnstile_grant(self):
        page = self.client.get(f"/download/{self.artifact_id}?source=international")
        self.assertIn('name="source" value="international"', page.text)
        with patch.object(app, "verify_turnstile", return_value=True):
            verified = self.client.post(
                f"/download/{self.artifact_id}/verify",
                data={"cf-turnstile-response": "ok", "source": "international"},
                follow_redirects=False,
            )
        self.assertEqual(verified.status_code, 303)
        self.assertIn("source=international", verified.headers["location"])
        downloaded = self.client.get(verified.headers["location"], headers={"X-Mirror-Client-IP": "1.0.1.8"})
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, b"demo")

    def test_stale_edge_health_falls_back_to_origin(self):
        old = __import__('time').time() - app.EDGE_HEALTH_MAX_AGE - 10
        os.utime(app.EDGE_HEALTH_FILE, (old, old))
        response = self.client.get(f"/api/v1/download/{self.artifact_id}", params={"token": app.serializer.dumps({"purpose": "machine-download", "artifact_id": self.artifact_id})}, headers={"X-Mirror-Client-IP": "1.0.1.8"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"demo")
        app.EDGE_HEALTH_FILE.write_text("ok")


if __name__ == "__main__":
    unittest.main()
