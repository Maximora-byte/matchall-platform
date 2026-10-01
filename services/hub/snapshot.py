import json
import os
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

OUT = Path(os.getenv("HUB_SNAPSHOT_DIR", "/srv/personal-blog/hub-platform/data/snapshots"))
XBOARD_DB = Path("/srv/xboard/.docker/.data/database.sqlite")
MIRROR_DB = Path("/srv/personal-blog/mirror-platform/data/mirror.db")


def atomic_json(name, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=OUT)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        os.chmod(tmp, 0o600)
        # The hub container runs as uid 10001 and receives this directory as a
        # read-only operational snapshot mount.
        os.chown(tmp, 10001, 10001)
        os.replace(tmp, OUT / f"{name}.json")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def sqlite_snapshot(path):
    source = sqlite3.connect(path)
    fd, tmp = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    dest = sqlite3.connect(tmp)
    source.backup(dest)
    dest.close(); source.close()
    con = sqlite3.connect(tmp); con.row_factory = sqlite3.Row
    return con, tmp


def xboard():
    con, tmp = sqlite_snapshot(XBOARD_DB)
    try:
        rows = [dict(x) for x in con.execute("""
          SELECT i.subject,i.email,u.email username,u.banned,u.t,u.u,u.d,u.transfer_enable,u.expired_at,
                 COALESCE(p.name,'') plan_name,COALESCE(NULLIF(u.device_limit,0),p.device_limit,0) device_limit,
                 u.online_count,u.last_online_at,u.speed_limit,
                 (SELECT COUNT(*) FROM v2_order o WHERE o.user_id=u.id) order_count,
                 (SELECT COUNT(*) FROM v2_order o WHERE o.user_id=u.id AND o.status=3) paid_orders
          FROM v2_authentik_oidc_identities i JOIN v2_user u ON u.id=i.user_id LEFT JOIN v2_plan p ON p.id=u.plan_id
        """)]
        for row in rows:
            row["used"] = int(row.pop("u") or 0) + int(row.pop("d") or 0)
        atomic_json("xboard", {"generated_at": int(time.time()), "users": rows})
    finally:
        con.close(); os.unlink(tmp)


def mirrors():
    con, tmp = sqlite_snapshot(MIRROR_DB)
    try:
        rows = [dict(x) for x in con.execute("""
          SELECT u.sub subject,u.username,u.email,
            (SELECT COUNT(*) FROM orders o WHERE o.user_sub=u.sub) order_count,
            (SELECT COUNT(*) FROM orders o WHERE o.user_sub=u.sub AND o.status='paid') paid_orders,
            (SELECT COUNT(*) FROM entitlements e WHERE e.user_sub=u.sub AND e.active=1 AND (e.ends_at IS NULL OR e.ends_at>strftime('%s','now'))) active_entitlements,
            (SELECT COUNT(*) FROM api_tokens t WHERE t.user_sub=u.sub AND t.revoked=0 AND (t.expires_at IS NULL OR t.expires_at>strftime('%s','now'))) active_tokens
          FROM users u
        """)]
        atomic_json("mirrors", {"generated_at": int(time.time()), "users": rows})
    finally:
        con.close(); os.unlink(tmp)


def nextcloud():
    listing = subprocess.run(["docker", "exec", "personal-blog-nextcloud-1", "php", "occ", "user:list", "--output=json"], check=True, capture_output=True, text=True)
    users = []
    for username in json.loads(listing.stdout):
        info = subprocess.run(["docker", "exec", "personal-blog-nextcloud-1", "php", "occ", "user:info", username, "--output=json"], check=True, capture_output=True, text=True)
        data = json.loads(info.stdout)
        users.append({"username": username, "email": data.get("email", ""), "display_name": data.get("display_name", ""),
                      "enabled": data.get("enabled", True), "used": data.get("storage", {}).get("used", 0),
                      "quota": data.get("storage", {}).get("quota", 0), "free": data.get("storage", {}).get("free", 0),
                      "last_seen": data.get("last_seen", 0)})
    atomic_json("nextcloud", {"generated_at": int(time.time()), "users": users})


if __name__ == "__main__":
    xboard(); mirrors(); nextcloud()
