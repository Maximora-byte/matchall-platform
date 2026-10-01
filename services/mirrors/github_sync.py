#!/usr/bin/env python3
import argparse
import hashlib
import os
import re
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx


DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "mirror.db"
INTERVAL = max(300, int(os.getenv("GITHUB_SYNC_INTERVAL", "1800")))
MIN_FREE_BYTES = max(1024**3, int(os.getenv("GITHUB_SYNC_MIN_FREE_BYTES", str(10 * 1024**3))))
MAX_ASSET_BYTES = max(1024**2, int(os.getenv("GITHUB_SYNC_MAX_ASSET_BYTES", str(5 * 1024**3))))
USER_AGENT = "MatchAll-Mirrors-GitHub-Sync/1.0"

SOURCES = (
    {
        "repo": "Meloong-Git/PCL",
        "slug": "pcl",
        "name": "Plain Craft Launcher",
        "summary": "PCL 最新正式版本信息；下载由 GitHub 上游提供。",
        "description": "上游未提供 Release 附件且仓库未声明再分发许可证，因此仅同步版本说明并链接 GitHub 官方发布页。",
        "license": "上游未声明",
        "icon": "PCL",
        "mode": "upstream",
    },
    {
        "repo": "PCL-Community/PCL-CE",
        "slug": "pcl-ce",
        "name": "PCL Community Edition",
        "summary": "PCL-CE 最新稳定版的本地校验镜像。",
        "description": "从 GitHub 官方 Release 自动同步最新正式版附件；文件下载后由 MatchAll 计算 SHA-256。",
        "license": "Apache-2.0",
        "icon": "PCL",
        "mode": "mirror",
    },
    {
        "repo": "chen08209/FlClash",
        "slug": "flclash",
        "name": "FlClash",
        "summary": "FlClash 最新稳定版的多平台本地校验镜像。",
        "description": "从 GitHub 官方 Release 自动同步最新正式版附件，覆盖 Android、Linux、macOS 与 Windows；文件下载后由 MatchAll 复核 SHA-256。",
        "license": "GPL-3.0",
        "icon": "FC",
        "mode": "mirror",
    },
    {
        "repo": "2dust/v2rayN",
        "slug": "v2rayn",
        "name": "v2rayN",
        "summary": "v2rayN 最新稳定版的多平台本地校验镜像。",
        "description": "从 GitHub 官方 Release 自动同步最新正式版附件及签名，覆盖 Linux、macOS 与 Windows；文件下载后由 MatchAll 复核 SHA-256。",
        "license": "GPL-3.0",
        "icon": "V2",
        "mode": "mirror",
    },
    {
        "repo": "2dust/v2rayNG",
        "slug": "v2rayng",
        "name": "v2rayNG",
        "summary": "v2rayNG 最新稳定版的 Android 本地校验镜像。",
        "description": "从 GitHub 官方 Release 自动同步最新正式版 APK、签名与公钥；文件下载后由 MatchAll 复核 SHA-256。",
        "license": "GPL-3.0",
        "icon": "V2",
        "mode": "mirror",
    },
)


def connect(db_path=DB_PATH):
    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def ensure_schema(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS github_sync_sources (
      repo TEXT PRIMARY KEY,
      project_slug TEXT UNIQUE NOT NULL,
      mode TEXT NOT NULL CHECK(mode IN ('mirror','upstream')),
      release_id INTEGER,
      tag TEXT NOT NULL DEFAULT '',
      checked_at INTEGER,
      synced_at INTEGER,
      status TEXT NOT NULL DEFAULT 'pending',
      error TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS github_sync_assets (
      repo TEXT NOT NULL REFERENCES github_sync_sources(repo) ON DELETE CASCADE,
      asset_id INTEGER NOT NULL,
      release_id INTEGER NOT NULL,
      filename TEXT NOT NULL,
      size INTEGER NOT NULL,
      sha256 TEXT NOT NULL DEFAULT '',
      PRIMARY KEY(repo, asset_id)
    );
    """)


def github_json(client, repo):
    response = client.get(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"accept": "application/vnd.github+json", "user-agent": USER_AGENT},
    )
    response.raise_for_status()
    data = response.json()
    if data.get("draft") or data.get("prerelease"):
        raise ValueError("latest release is not a stable published release")
    if not isinstance(data.get("id"), int) or not str(data.get("tag_name", "")).strip():
        raise ValueError("GitHub release is missing id or tag")
    return data


def safe_name(value):
    name = Path(str(value)).name
    if not name or name in {".", ".."} or name != str(value):
        raise ValueError("unsafe asset filename")
    return name


def platform_for(filename):
    lower = filename.lower()
    if "android" in lower or lower.endswith((".apk", ".apk.sig")):
        os_name = "android"
    elif "linux" in lower or lower.endswith((".appimage", ".deb", ".rpm")):
        os_name = "linux"
    elif "macos" in lower or "darwin" in lower or lower.endswith((".dmg", ".pkg")):
        os_name = "macos"
    elif "windows" in lower or lower.endswith((".exe", ".msi", ".exe.asc", ".msi.asc")):
        os_name = "windows"
    else:
        os_name = "any"
    if re.search(r"(?:^|[._-])(arm64|aarch64)(?:[._-]|$)", lower):
        arch = "arm64"
    elif re.search(r"(?:^|[._-])(armeabi-v7a|armv7|armhf)(?:[._-]|$)", lower):
        arch = "armv7"
    elif re.search(r"(?:^|[._-])loong64(?:[._-]|$)", lower):
        arch = "loong64"
    elif re.search(r"(?:^|[._-])riscv64(?:[._-]|$)", lower):
        arch = "riscv64"
    elif re.search(r"(?:^|[._-])(x64|x86_64|amd64|win64|64)(?:[._-]|$)", lower):
        arch = "x64"
    elif re.search(r"(?:^|[._-])(x86|i386|win32|86)(?:[._-]|$)", lower):
        arch = "x86"
    else:
        arch = "any"
    return os_name, arch


def published_timestamp(value):
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return int(time.time())


def validate_assets(repo, release):
    assets = release.get("assets") or []
    seen_names = set()
    result = []
    for asset in assets:
        asset_id = asset.get("id")
        name = safe_name(asset.get("name", ""))
        size = int(asset.get("size", -1))
        url = str(asset.get("browser_download_url", ""))
        upstream_digest = str(asset.get("digest") or "")
        prefix = f"https://github.com/{repo}/releases/download/"
        if not isinstance(asset_id, int) or size < 0 or size > MAX_ASSET_BYTES or not url.startswith(prefix):
            raise ValueError(f"invalid GitHub asset: {name}")
        if name in seen_names:
            raise ValueError(f"duplicate GitHub asset name: {name}")
        seen_names.add(name)
        if upstream_digest and not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", upstream_digest):
            raise ValueError(f"unsupported GitHub asset digest: {name}")
        result.append({"id": asset_id, "name": name, "size": size, "url": url,
                       "upstream_sha256": upstream_digest.removeprefix("sha256:").lower()})
    return result


def download_assets(client, source, release, root=FILES_DIR):
    assets = validate_assets(source["repo"], release)
    if not assets:
        raise ValueError("latest release has no downloadable assets")
    needed = sum(a["size"] for a in assets)
    storage_root = root / "github"
    storage_root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(storage_root).free
    if free - needed < MIN_FREE_BYTES:
        raise OSError("data disk free-space reserve would be crossed")
    base = storage_root / source["slug"]
    incoming = base / f".incoming-{uuid.uuid4().hex}"
    incoming.mkdir(parents=True, exist_ok=False)
    downloaded = []
    try:
        for asset in assets:
            target = incoming / asset["name"]
            digest = hashlib.sha256()
            size = 0
            with client.stream("GET", asset["url"], headers={"user-agent": USER_AGENT}, follow_redirects=True) as response:
                response.raise_for_status()
                with target.open("xb") as output:
                    for chunk in response.iter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > asset["size"] or size > MAX_ASSET_BYTES:
                            raise ValueError(f"asset size exceeded declared limit: {asset['name']}")
                        digest.update(chunk)
                        output.write(chunk)
            if size != asset["size"]:
                raise ValueError(f"asset size mismatch: {asset['name']}")
            sha256 = digest.hexdigest()
            if asset["upstream_sha256"] and sha256 != asset["upstream_sha256"]:
                raise ValueError(f"asset SHA-256 mismatch: {asset['name']}")
            os_name, arch = platform_for(asset["name"])
            downloaded.append({**asset, "sha256": sha256, "os": os_name, "arch": arch})
        final = base / str(release["id"])
        if final.exists():
            shutil.rmtree(final)
        incoming.rename(final)
        return final, downloaded
    except Exception:
        shutil.rmtree(incoming, ignore_errors=True)
        raise


def upsert_project(con, source, now):
    homepage = f"https://github.com/{source['repo']}"
    con.execute("""
      INSERT INTO projects(slug,name,summary,description,homepage,license,icon,public,access_mode,visibility,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,1,'free','public',?,?)
      ON CONFLICT(slug) DO UPDATE SET name=excluded.name,summary=excluded.summary,
        description=excluded.description,homepage=excluded.homepage,license=excluded.license,
        icon=excluded.icon,public=1,access_mode='free',visibility='public',updated_at=excluded.updated_at
    """, (source["slug"], source["name"], source["summary"], source["description"], homepage,
          source["license"], source["icon"], now, now))
    return con.execute("SELECT id FROM projects WHERE slug=?", (source["slug"],)).fetchone()["id"]


def publish_release(con, source, release, downloaded, now):
    project_id = upsert_project(con, source, now)
    tag = str(release["tag_name"]).strip()
    con.execute("""INSERT INTO github_sync_sources(repo,project_slug,mode,release_id,tag,checked_at,status,error)
      VALUES(?,?,?,?,?,?,'syncing','')
      ON CONFLICT(repo) DO UPDATE SET project_slug=excluded.project_slug,mode=excluded.mode,
        release_id=excluded.release_id,tag=excluded.tag,checked_at=excluded.checked_at,status='syncing',error=''""",
                (source["repo"], source["slug"], source["mode"], int(release["id"]), tag, now))
    con.execute("DELETE FROM releases WHERE project_id=?", (project_id,))
    version = tag[1:] if tag.lower().startswith("v") and len(tag) > 1 else tag
    notes = str(release.get("body") or "")[:10000]
    published_at = published_timestamp(release.get("published_at"))
    cur = con.execute("""
      INSERT INTO releases(project_id,version,channel,notes,published_at,status,rollout_percentage,approved_by,approved_at)
      VALUES(?,?, 'stable', ?,?,'published',100,'github-sync',?)
    """, (project_id, version, notes, published_at, now))
    mirror_release_id = cur.lastrowid
    con.execute("DELETE FROM github_sync_assets WHERE repo=?", (source["repo"],))
    if source["mode"] == "upstream":
        filename = f"GitHub 上游发布页 · {tag}"
        con.execute("""INSERT INTO artifacts(release_id,os,arch,filename,external_url,size,sha256,created_at,storage_provider)
          VALUES(?,'any','any',?,?,0,'',?,'external')""",
                    (mirror_release_id, filename, str(release["html_url"]), now))
    else:
        for asset in downloaded:
            local_path = f"github/{source['slug']}/{release['id']}/{asset['name']}"
            con.execute("""INSERT INTO artifacts(release_id,os,arch,filename,local_path,size,sha256,created_at,storage_provider)
              VALUES(?,?,?,?,?,?,?,?,'local')""",
                        (mirror_release_id, asset["os"], asset["arch"], asset["name"], local_path,
                         asset["size"], asset["sha256"], now))
            con.execute("INSERT INTO github_sync_assets(repo,asset_id,release_id,filename,size,sha256) VALUES(?,?,?,?,?,?)",
                        (source["repo"], asset["id"], int(release["id"]), asset["name"], asset["size"], asset["sha256"]))
    con.execute("UPDATE github_sync_sources SET synced_at=?,status='ok',error='' WHERE repo=?", (now, source["repo"]))
    con.execute("INSERT INTO audit_log(actor_sub,project_id,action,detail,created_at) VALUES('github-sync',?,'release.synced',?,?)",
                (project_id, f"{source['repo']}:{tag}:{source['mode']}", now))


def cleanup_old_files(source, current_release_id, root=FILES_DIR):
    base = root / "github" / source["slug"]
    if not base.exists():
        return
    keep = str(current_release_id)
    for child in base.iterdir():
        if child.name != keep:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)


def mark_error(con, source, message, now):
    con.execute("""INSERT INTO github_sync_sources(repo,project_slug,mode,checked_at,status,error)
      VALUES(?,?,?,?, 'error', ?)
      ON CONFLICT(repo) DO UPDATE SET checked_at=excluded.checked_at,status='error',error=excluded.error""",
                (source["repo"], source["slug"], source["mode"], now, str(message)[:500]))


def sync_source(client, source, db_path=DB_PATH, root=FILES_DIR):
    now = int(time.time())
    release = github_json(client, source["repo"])
    con = connect(db_path)
    ensure_schema(con)
    existing = con.execute("SELECT release_id,status FROM github_sync_sources WHERE repo=?", (source["repo"],)).fetchone()
    if existing and existing["release_id"] == int(release["id"]) and existing["status"] == "ok":
        con.execute("UPDATE github_sync_sources SET checked_at=?,error='' WHERE repo=?", (now, source["repo"]))
        con.commit(); con.close()
        if source["mode"] == "mirror":
            cleanup_old_files(source, release["id"], root)
        return "unchanged"
    downloaded = []
    final = None
    try:
        if source["mode"] == "mirror":
            final, downloaded = download_assets(client, source, release, root)
        publish_release(con, source, release, downloaded, now)
        con.commit()
    except Exception:
        con.rollback()
        if final:
            shutil.rmtree(final, ignore_errors=True)
        raise
    finally:
        con.close()
    if source["mode"] == "mirror":
        cleanup_old_files(source, release["id"], root)
    return "updated"


def sync_once(db_path=DB_PATH, root=FILES_DIR, sources=SOURCES, client=None):
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(30, read=300), follow_redirects=True)
    results = {}
    try:
        for source in sources:
            try:
                results[source["repo"]] = sync_source(client, source, db_path, root)
            except Exception as exc:
                results[source["repo"]] = f"error: {exc}"
                con = connect(db_path); ensure_schema(con); mark_error(con, source, exc, int(time.time())); con.commit(); con.close()
    finally:
        if own_client:
            client.close()
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        for repo, result in sync_once().items():
            print(f"{repo}: {result}", flush=True)
        if args.once:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
