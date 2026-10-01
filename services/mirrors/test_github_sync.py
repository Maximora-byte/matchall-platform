import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

import github_sync as sync


def create_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE projects(id INTEGER PRIMARY KEY,slug TEXT UNIQUE NOT NULL,name TEXT NOT NULL,summary TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',homepage TEXT NOT NULL DEFAULT '',license TEXT NOT NULL DEFAULT '',icon TEXT NOT NULL DEFAULT '📦',
      public INTEGER NOT NULL DEFAULT 1,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,access_mode TEXT NOT NULL DEFAULT 'free',
      product_id INTEGER,team_id INTEGER,visibility TEXT NOT NULL DEFAULT 'public');
    CREATE TABLE releases(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      version TEXT NOT NULL,channel TEXT NOT NULL DEFAULT 'stable',notes TEXT NOT NULL DEFAULT '',published_at INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'published',rollout_percentage INTEGER NOT NULL DEFAULT 100,approved_by TEXT NOT NULL DEFAULT '',
      approved_at INTEGER,rolled_back_at INTEGER,UNIQUE(project_id,version,channel));
    CREATE TABLE artifacts(id INTEGER PRIMARY KEY,release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
      os TEXT NOT NULL DEFAULT 'any',arch TEXT NOT NULL DEFAULT 'any',filename TEXT NOT NULL,local_path TEXT NOT NULL DEFAULT '',
      external_url TEXT NOT NULL DEFAULT '',size INTEGER NOT NULL DEFAULT 0,sha256 TEXT NOT NULL DEFAULT '',downloads INTEGER NOT NULL DEFAULT 0,
      created_at INTEGER NOT NULL,storage_provider TEXT NOT NULL DEFAULT 'local',storage_key TEXT NOT NULL DEFAULT '');
    CREATE TABLE audit_log(id INTEGER PRIMARY KEY,actor_sub TEXT NOT NULL,team_id INTEGER,project_id INTEGER,
      action TEXT NOT NULL,detail TEXT NOT NULL DEFAULT '',created_at INTEGER NOT NULL);
    """)
    con.close()


class Response:
    def __init__(self, data=None, body=b'', status=200):
        self.data, self.body, self.status_code = data, body, status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')
    def json(self): return self.data
    def iter_bytes(self, _size): yield self.body
    def __enter__(self): return self
    def __exit__(self, *_): return False


class Client:
    def __init__(self, releases, bodies): self.releases, self.bodies = releases, bodies
    def get(self, url, headers=None):
        repo = url.split('/repos/', 1)[1].split('/releases/', 1)[0]
        return Response(data=self.releases[repo])
    def stream(self, method, url, headers=None, follow_redirects=True):
        return Response(body=self.bodies[url])


class GitHubSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'files'; self.root.mkdir()
        self.db = Path(self.tmp.name) / 'mirror.db'; create_db(self.db)
        self.old_reserve = sync.MIN_FREE_BYTES; sync.MIN_FREE_BYTES = 0
    def tearDown(self):
        sync.MIN_FREE_BYTES = self.old_reserve; self.tmp.cleanup()

    def release(self, repo, release_id, tag, assets):
        return {'id': release_id, 'tag_name': tag, 'name': tag, 'body': 'notes', 'draft': False, 'prerelease': False,
                'published_at': '2026-01-02T03:04:05Z', 'html_url': f'https://github.com/{repo}/releases/tag/{tag}', 'assets': assets}

    def test_upstream_project_is_public_free_and_does_not_copy(self):
        source = sync.SOURCES[0]; release = self.release(source['repo'], 10, '2.0', [])
        result = sync.sync_source(Client({source['repo']: release}, {}), source, self.db, self.root)
        self.assertEqual(result, 'updated')
        con = sqlite3.connect(self.db); con.row_factory = sqlite3.Row
        project = con.execute("SELECT * FROM projects WHERE slug='pcl'").fetchone()
        artifact = con.execute('SELECT * FROM artifacts').fetchone()
        self.assertEqual((project['public'], project['visibility'], project['access_mode']), (1, 'public', 'free'))
        self.assertEqual(artifact['external_url'], release['html_url'])
        self.assertFalse((self.root / 'github' / 'pcl').exists())

    def test_mirror_downloads_assets_computes_hash_and_is_idempotent(self):
        source = sync.SOURCES[1]; repo = source['repo']; body = b'official-binary'
        url = f'https://github.com/{repo}/releases/download/v1/PCL2_CE_Release_x64.exe'
        assets = [{'id': 101, 'name': 'PCL2_CE_Release_x64.exe', 'size': len(body), 'browser_download_url': url}]
        release = self.release(repo, 11, 'v1', assets); client = Client({repo: release}, {url: body})
        self.assertEqual(sync.sync_source(client, source, self.db, self.root), 'updated')
        self.assertEqual(sync.sync_source(client, source, self.db, self.root), 'unchanged')
        con = sqlite3.connect(self.db); con.row_factory = sqlite3.Row
        rows = con.execute('SELECT * FROM artifacts').fetchall()
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['arch'], 'x64')
        self.assertEqual(rows[0]['sha256'], hashlib.sha256(body).hexdigest())
        self.assertTrue((self.root / rows[0]['local_path']).is_file())

    def test_new_release_replaces_old_only_after_complete_download(self):
        source = sync.SOURCES[1]; repo = source['repo']
        url1 = f'https://github.com/{repo}/releases/download/v1/a.exe'; body1 = b'one'
        r1 = self.release(repo, 21, 'v1', [{'id': 201, 'name': 'a.exe', 'size': 3, 'browser_download_url': url1}])
        sync.sync_source(Client({repo: r1}, {url1: body1}), source, self.db, self.root)
        url2 = f'https://github.com/{repo}/releases/download/v2/b.exe'
        r2 = self.release(repo, 22, 'v2', [{'id': 202, 'name': 'b.exe', 'size': 4, 'browser_download_url': url2}])
        with self.assertRaises(ValueError):
            sync.sync_source(Client({repo: r2}, {url2: b'bad'}), source, self.db, self.root)
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute('SELECT version FROM releases').fetchone()[0], '1')
        self.assertTrue((self.root / 'github' / 'pcl-ce' / '21' / 'a.exe').is_file())

    def test_rejects_prerelease_and_unsafe_asset(self):
        source = sync.SOURCES[1]; repo = source['repo']
        release = self.release(repo, 30, 'v3', []); release['prerelease'] = True
        with self.assertRaises(ValueError):
            sync.sync_source(Client({repo: release}, {}), source, self.db, self.root)
        release['prerelease'] = False
        release['assets'] = [{'id': 1, 'name': '../evil.exe', 'size': 1,
                              'browser_download_url': f'https://github.com/{repo}/releases/download/v3/evil.exe'}]
        with self.assertRaises(ValueError):
            sync.sync_source(Client({repo: release}, {}), source, self.db, self.root)

    def test_rejects_upstream_digest_mismatch(self):
        source = sync.SOURCES[1]; repo = source['repo']; url = f'https://github.com/{repo}/releases/download/v4/app.exe'
        release = self.release(repo, 40, 'v4', [{'id': 4, 'name': 'app.exe', 'size': 3,
            'digest': 'sha256:' + ('0' * 64), 'browser_download_url': url}])
        with self.assertRaises(ValueError):
            sync.sync_source(Client({repo: release}, {url: b'abc'}), source, self.db, self.root)

    def test_flclash_platform_and_architecture_mapping(self):
        cases = {
            'FlClash-0.8.98-android-arm64-v8a.apk': ('android', 'arm64'),
            'FlClash-0.8.98-android-armeabi-v7a.apk': ('android', 'armv7'),
            'FlClash-0.8.98-android-x86_64.apk': ('android', 'x64'),
            'FlClash-0.8.98-linux-amd64.AppImage': ('linux', 'x64'),
            'FlClash-0.8.98-linux-arm64.deb': ('linux', 'arm64'),
            'FlClash-0.8.98-macos-amd64.dmg': ('macos', 'x64'),
            'FlClash-0.8.98-macos-arm64.dmg': ('macos', 'arm64'),
            'FlClash-0.8.98-windows-amd64-setup.exe': ('windows', 'x64'),
            'FlClash-0.8.98-windows-arm64.zip': ('windows', 'arm64'),
            'SHA256SUMS': ('any', 'any'),
        }
        self.assertEqual(sync.SOURCES[2]['repo'], 'chen08209/FlClash')
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(sync.platform_for(filename), expected)

    def test_v2ray_platform_and_architecture_mapping(self):
        cases = {
            'v2rayN-linux-64.deb': ('linux', 'x64'),
            'v2rayN-linux-arm64.zip.sig': ('linux', 'arm64'),
            'v2rayN-linux-loong64.deb': ('linux', 'loong64'),
            'v2rayN-linux-rhel-riscv64.rpm': ('linux', 'riscv64'),
            'v2rayN-macos-64.dmg': ('macos', 'x64'),
            'v2rayN-windows-86-desktop.zip': ('windows', 'x86'),
            'v2rayN-windows-arm64.zip.sig': ('windows', 'arm64'),
            'v2rayNG_2.2.6_arm64-v8a.apk.sig': ('android', 'arm64'),
            'v2rayNG_2.2.6_armeabi-v7a.apk': ('android', 'armv7'),
            'v2rayNG_2.2.6_x86.apk.sig': ('android', 'x86'),
            'v2rayNG_2.2.6_x86_64.apk': ('android', 'x64'),
            'v2rayN-public-key.asc': ('any', 'any'),
        }
        self.assertEqual(sync.SOURCES[3]['repo'], '2dust/v2rayN')
        self.assertEqual(sync.SOURCES[4]['repo'], '2dust/v2rayNG')
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(sync.platform_for(filename), expected)


if __name__ == '__main__': unittest.main()
