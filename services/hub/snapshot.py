"""Operator-run account summaries; importing this module never starts collection."""
import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from contextlib import ExitStack, contextmanager

OUT = Path(os.getenv("HUB_SNAPSHOT_DIR", "/srv/personal-blog/hub-platform/data/snapshots"))
XBOARD_DB = Path("/srv/xboard/.docker/.data/database.sqlite")
MIRROR_DB = Path("/srv/personal-blog/mirror-platform/data/mirror.db")


class CollectionTimeout(TimeoutError):
    pass


class Deadline:
    def __init__(self, seconds):
        self.end = time.monotonic() + seconds

    def expired(self):
        return time.monotonic() >= self.end

    def remaining(self):
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise CollectionTimeout("collection_timeout")
        return remaining


def atomic_json(name, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=OUT)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        # The hub container runs as uid 10001 and receives this directory as a
        # read-only operational snapshot mount.
        os.chown(tmp, 10001, 10001)
        os.replace(tmp, OUT / f"{name}.json")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def sqlite_snapshot(path, deadline):
    """Copy a read-only source, bounding busy retries and query work cooperatively."""
    with ExitStack() as cleanup:
        source = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True,
                                 timeout=min(5, deadline.remaining()))
        cleanup.callback(source.close)
        fd, tmp = tempfile.mkstemp(suffix=".sqlite")
        cleanup.callback(Path(tmp).unlink, missing_ok=True)
        os.close(fd)
        dest = sqlite3.connect(tmp, timeout=min(5, deadline.remaining()))
        cleanup.callback(dest.close)

        def progress(status, remaining, total):
            # SQLite also calls this when BUSY/LOCKED; never retry indefinitely.
            deadline.remaining()

        source.backup(dest, pages=128, progress=progress, sleep=0.05)
        deadline.remaining()
        dest.close()
        source.close()
        con = sqlite3.connect(tmp, timeout=min(5, deadline.remaining()))
        cleanup.callback(con.close)
        con.row_factory = sqlite3.Row
        con.set_progress_handler(lambda: int(deadline.expired()), 1000)
        try:
            yield con
        except sqlite3.OperationalError:
            if deadline.expired():
                raise CollectionTimeout("collection_timeout") from None
            raise


def query_rows(con, query, deadline):
    rows = []
    deadline.remaining()
    for row in con.execute(query):
        deadline.remaining()
        rows.append(dict(row))
    deadline.remaining()
    return rows


def xboard(deadline, command_timeout):
    with sqlite_snapshot(XBOARD_DB, deadline) as con:
        rows = query_rows(con, """
          SELECT i.subject,i.email,u.email username,u.banned,u.t,u.u,u.d,u.transfer_enable,u.expired_at,
                 COALESCE(p.name,'') plan_name,COALESCE(NULLIF(u.device_limit,0),p.device_limit,0) device_limit,
                 u.online_count,u.last_online_at,u.speed_limit,
                 (SELECT COUNT(*) FROM v2_order o WHERE o.user_id=u.id) order_count,
                 (SELECT COUNT(*) FROM v2_order o WHERE o.user_id=u.id AND o.status=3) paid_orders
          FROM v2_authentik_oidc_identities i JOIN v2_user u ON u.id=i.user_id LEFT JOIN v2_plan p ON p.id=u.plan_id
        """, deadline)
        for row in rows:
            deadline.remaining()
            row["used"] = int(row.pop("u") or 0) + int(row.pop("d") or 0)
        return rows


def mirrors(deadline, command_timeout):
    with sqlite_snapshot(MIRROR_DB, deadline) as con:
        return query_rows(con, """
          SELECT u.sub subject,u.username,u.email,
            (SELECT COUNT(*) FROM orders o WHERE o.user_sub=u.sub) order_count,
            (SELECT COUNT(*) FROM orders o WHERE o.user_sub=u.sub AND o.status='paid') paid_orders,
            (SELECT COUNT(*) FROM entitlements e WHERE e.user_sub=u.sub AND e.active=1 AND (e.ends_at IS NULL OR e.ends_at>strftime('%s','now'))) active_entitlements,
            (SELECT COUNT(*) FROM api_tokens t WHERE t.user_sub=u.sub AND t.revoked=0 AND (t.expires_at IS NULL OR t.expires_at>strftime('%s','now'))) active_tokens
          FROM users u
        """, deadline)


def nextcloud_command(arguments, deadline, command_timeout):
    result = subprocess.run(
        ["docker", "exec", "personal-blog-nextcloud-1", "php", "occ", *arguments],
        check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        encoding="utf-8", timeout=min(command_timeout, deadline.remaining()),
    )
    deadline.remaining()
    return json.loads(result.stdout)


def nextcloud(deadline, command_timeout):
    listing = nextcloud_command(["user:list", "--output=json"], deadline, command_timeout)
    # PHP encodes an empty user map as [], not {}.
    if listing == []:
        listing = {}
    if not isinstance(listing, dict) or any(not isinstance(name, str) or not name for name in listing):
        raise ValueError("invalid_user_list")
    users = []
    for username in listing:
        data = nextcloud_command(["user:info", username, "--output=json"], deadline, command_timeout)
        if not isinstance(data, dict) or not isinstance(data.get("storage"), dict):
            raise ValueError("invalid_user_info")
        storage = data["storage"]
        if (type(data.get("enabled")) not in (bool, int) or data["enabled"] not in (False, True) or
                type(storage.get("used")) is not int or storage["used"] < 0 or
                type(storage.get("quota")) is not int):
            raise ValueError("invalid_user_info")
        users.append({"username": username, "email": data.get("email", ""), "display_name": data.get("display_name", ""),
                      "enabled": data["enabled"], "used": storage["used"],
                      "quota": storage["quota"], "free": storage.get("free", 0),
                      "last_seen": data.get("last_seen", 0)})
    return users


def error_snapshot(code):
    # A null success timestamp also makes legacy Hub readers fail closed.
    return {"generated_at": None, "users": [], "collection_state": "error",
            "attempted_at": int(time.time()), "error_code": code}


def collect_all(*, source_timeout=120, command_timeout=15):
    if (type(source_timeout) is not int or not 1 <= source_timeout <= 900 or
            type(command_timeout) is not int or not 1 <= command_timeout <= 120):
        raise ValueError("invalid_collection_timeouts")
    results = {}
    for name, collect in (("xboard", xboard), ("mirrors", mirrors), ("nextcloud", nextcloud)):
        deadline = Deadline(source_timeout)
        code = None
        try:
            rows = collect(deadline, command_timeout)
            deadline.remaining()
            payload = {"generated_at": int(time.time()), "users": rows}
        except (CollectionTimeout, subprocess.TimeoutExpired):
            code = "collection_timeout"
            payload = error_snapshot(code)
        except Exception:
            # Never publish commands, paths, SQL, stdout, usernames or exception text.
            code = "collection_failed"
            payload = error_snapshot(code)
        try:
            atomic_json(name, payload)
        except Exception:
            code = "publication_failed"
            # A serialization/permission failure may still allow a small error marker.
            # A persistent filesystem failure leaves the prior file to age out.
            try:
                atomic_json(name, error_snapshot(code))
            except Exception:
                pass
        results[name] = {"state": "error" if code else "ok", "error_code": code}
    return {"ok": all(item["state"] == "ok" for item in results.values()), "sources": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect read-only Console summaries (operator use only).")
    parser.add_argument("--source-timeout", type=int, default=120, help="Per-source budget in seconds (1-900)")
    parser.add_argument("--command-timeout", type=int, default=15, help="Per-Docker-client timeout in seconds (1-120)")
    args = parser.parse_args(argv)
    try:
        report = collect_all(source_timeout=args.source_timeout, command_timeout=args.command_timeout)
    except ValueError:
        parser.error("timeouts must be within the documented ranges")
    print(json.dumps(report, separators=(",", ":")))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
