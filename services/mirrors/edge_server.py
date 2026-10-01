import hashlib
import hmac
import os
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

DATA_DIR = Path(os.getenv("EDGE_DATA_DIR", "/srv/mirror-edge"))
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "mirror.db"
SECRET_FILE = Path(os.getenv("EDGE_SECRET_FILE", "/etc/mirror-edge/download.secret"))

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def secret() -> bytes:
    return SECRET_FILE.read_text().strip().encode()


def artifact(artifact_id: int):
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return con.execute("SELECT id,filename,local_path,size,sha256 FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
    finally:
        con.close()


@app.get("/healthz")
def health():
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT local_path,size FROM artifacts "
                "WHERE storage_provider='local' AND local_path IS NOT NULL"
            ).fetchall()
        finally:
            con.close()
        ready = 0
        for local_path, size in rows:
            path = FILES_DIR / local_path
            if (
                path.is_file()
                and FILES_DIR in path.resolve().parents
                and path.stat().st_size == size
            ):
                ready += 1
        ok = bool(rows) and ready == len(rows)
        return JSONResponse(
            {"ok": ok, "artifacts": len(rows), "ready": ready},
            status_code=200 if ok else 503,
        )
    except (OSError, sqlite3.Error):
        return JSONResponse({"ok": False, "artifacts": 0, "ready": 0}, status_code=503)


@app.api_route("/artifact/{artifact_id}", methods=["GET", "HEAD"])
def download(artifact_id: int, request: Request, expires: int, signature: str):
    row = artifact(artifact_id)
    if not row or expires < int(time.time()) or expires > int(time.time()) + 3600:
        raise HTTPException(403)
    message = f"{artifact_id}:{row['local_path']}:{expires}"
    expected = hmac.new(secret(), message.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(403)
    path = FILES_DIR / row["local_path"]
    if not path.is_file() or FILES_DIR not in path.resolve().parents:
        raise HTTPException(404)
    return FileResponse(path, filename=row["filename"], headers={"ETag": row["sha256"], "X-Checksum-SHA256": row["sha256"], "Cache-Control": "private, no-store"})
