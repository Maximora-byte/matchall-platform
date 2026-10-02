"""Durable, at-least-once delivery of approved release notifications.

This module never opens a database or starts a worker on import. The caller
supplies its database context manager, HTTP client and current configuration.
"""

import asyncio
import hashlib
import hmac
import json
import secrets
import socket
import time

import httpx
from fastapi import HTTPException


MAX_ATTEMPTS = 8
LEASE_SECONDS = 60
REQUEST_TIMEOUT = 8.0
ATTEMPT_TIMEOUT = 10.0
VALIDATION_TIMEOUT = 3.0


def ensure_schema(con):
    """Add the outbox without changing existing rows or transaction boundaries."""
    con.execute("""CREATE TABLE IF NOT EXISTS release_event_outbox (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
      webhook_id INTEGER REFERENCES project_webhooks(id) ON DELETE CASCADE,
      event_id TEXT NOT NULL,
      event_type TEXT NOT NULL,
      destination_key TEXT NOT NULL,
      payload BLOB NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      attempts INTEGER NOT NULL DEFAULT 0,
      next_attempt_at INTEGER NOT NULL,
      claim_token TEXT NOT NULL DEFAULT '',
      leased_until INTEGER NOT NULL DEFAULT 0,
      status_code INTEGER NOT NULL DEFAULT 0,
      last_error TEXT NOT NULL DEFAULT '',
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL,
      sent_at INTEGER,
      UNIQUE(event_id, destination_key)
    )""")
    con.execute("""CREATE INDEX IF NOT EXISTS idx_release_event_due
      ON release_event_outbox(status, next_attempt_at, leased_until)""")


def enqueue_release_event(con, project, release_id, version, channel, base_url, now):
    """Enqueue destinations in the same transaction that approves the release."""
    project = dict(project)
    now = int(now)
    visibility = project.get("visibility", "private")
    is_public = visibility == "public"
    event_id = f"release:{project['slug']}:{channel}:{version}"
    event = {
        "id": event_id, "type": "release.published", "severity": "info",
        "title": f"{project['name']} {version} 已发布",
        "body": f"{channel} 通道已有新版本。",
        "url": f"{base_url.rstrip('/')}/project/{project['slug']}",
        "audience": "users" if is_public else "private", "visibility": visibility,
        "project": project["slug"], "version": version, "channel": channel,
        "created_at": now,
    }
    raw = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    destinations = [("hub", None)] if is_public else []
    destinations.extend((f"webhook:{row['id']}", row["id"]) for row in con.execute(
        "SELECT id,events FROM project_webhooks WHERE project_id=? AND active=1 ORDER BY id",
        (project["id"],)).fetchall() if _release_subscribed(row["events"]))
    inserted = 0
    for destination, webhook_id in destinations:
        result = con.execute("""INSERT OR IGNORE INTO release_event_outbox
          (project_id,release_id,webhook_id,event_id,event_type,destination_key,payload,
           next_attempt_at,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)""",
          (project["id"], release_id, webhook_id, event_id, "release.published",
           destination, raw, now, now, now))
        inserted += result.rowcount
    return inserted


def _release_subscribed(events):
    return "release.published" in {item.strip() for item in str(events or "").split(",")}


def claim_event(db, now):
    """Atomically claim one due row, recovering abandoned claims after 60 seconds."""
    now = int(now)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        # The final attempt may have been interrupted before completion. Keep its
        # payload for owner inspection, but do not exceed the configured cap.
        con.execute("""UPDATE release_event_outbox
          SET status='failed',claim_token='',leased_until=0,next_attempt_at=0,
              last_error='lease_expired',updated_at=?
          WHERE status='processing' AND leased_until<=? AND attempts>=?""",
          (now, now, MAX_ATTEMPTS))
        row = con.execute("""SELECT * FROM release_event_outbox
          WHERE attempts<? AND ((status='pending' AND next_attempt_at<=?)
            OR (status='processing' AND leased_until<=?))
          ORDER BY next_attempt_at,id LIMIT 1""", (MAX_ATTEMPTS, now, now)).fetchone()
        if row is None:
            return None
        token = secrets.token_hex(24)
        con.execute("""UPDATE release_event_outbox SET status='processing',
          attempts=attempts+1,claim_token=?,leased_until=?,updated_at=? WHERE id=?""",
          (token, now + LEASE_SECONDS, now, row["id"]))
        return dict(con.execute("SELECT * FROM release_event_outbox WHERE id=?",
                                (row["id"],)).fetchone())


def _current_destination(db, event):
    """Check current authorization and status without holding a network transaction."""
    with db() as con:
        row = con.execute("""SELECT r.status release_status,r.version,r.channel,
          p.visibility,w.project_id hook_project_id,w.active hook_active,
          w.url hook_url,w.secret hook_secret,w.events hook_events
          FROM release_event_outbox o
          JOIN releases r ON r.id=o.release_id AND r.project_id=o.project_id
          JOIN projects p ON p.id=o.project_id
          LEFT JOIN project_webhooks w ON w.id=o.webhook_id
          WHERE o.id=? AND o.status='processing' AND o.claim_token=?""",
          (event["id"], event["claim_token"])).fetchone()
    return dict(row) if row is not None else None


def _finish_event(db, event, *, now, outcome, status_code=0, error=""):
    """Finish only the current claim; stale workers cannot overwrite newer results."""
    now = int(now)
    status = outcome
    next_attempt = 0
    if outcome == "retry":
        status = "failed" if event["attempts"] >= MAX_ATTEMPTS else "pending"
        if status == "pending":
            next_attempt = now + min(30 * 2 ** (event["attempts"] - 1), 3600)
    sent_at = now if status == "delivered" else None
    with db() as con:
        result = con.execute("""UPDATE release_event_outbox SET status=?,
          next_attempt_at=?,claim_token='',leased_until=0,status_code=?,last_error=?,
          updated_at=?,sent_at=?,payload=CASE WHEN ? IN ('delivered','cancelled')
            THEN X'' ELSE payload END
          WHERE id=? AND status='processing' AND claim_token=?""",
          (status, next_attempt, status_code, error, now, sent_at, status,
           event["id"], event["claim_token"]))
        if result.rowcount != 1:
            return None
        if event["webhook_id"] is not None and outcome != "cancelled":
            con.execute("""INSERT INTO webhook_deliveries
              (webhook_id,event_id,event_type,status,status_code,error,created_at,sent_at)
              VALUES(?,?,?,?,?,?,?,?)""",
              (event["webhook_id"], event["event_id"], event["event_type"],
               "delivered" if status == "delivered" else "failed",
               status_code, error, now, now))
    return status


async def _deliver_event(db, event, *, client, hub_url, hub_secret, validate_url):
    current = _current_destination(db, event)
    if current is None:
        return "lost", 0, ""
    try:
        raw = bytes(event["payload"])
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError
    except (TypeError, ValueError):
        return "failed", 0, "invalid_payload"
    if (current["release_status"] != "published"
            or current["version"] != payload.get("version")
            or current["channel"] != payload.get("channel")):
        return "cancelled", 0, "release_changed"
    if current["visibility"] != payload.get("visibility"):
        return "cancelled", 0, "visibility_changed"
    if event["destination_key"] == "hub":
        if current["visibility"] != "public" or payload.get("audience") != "users":
            return "cancelled", 0, "visibility_changed"
        secret = hub_secret()
        if not secret:
            return "retry", 0, "missing_hub_secret"
        url = hub_url
    else:
        if (event["destination_key"] != f"webhook:{event['webhook_id']}"
                or current["hook_active"] != 1
                or current["hook_project_id"] != event["project_id"]
                or not _release_subscribed(current["hook_events"])):
            return "cancelled", 0, "destination_disabled"
        url = current["hook_url"]
        try:
            # DNS can block. Bound the await and keep it off the event loop;
            # cancellation cannot forcibly stop the underlying resolver thread.
            await asyncio.wait_for(asyncio.to_thread(validate_url, url),
                                   timeout=VALIDATION_TIMEOUT)
        except (TimeoutError, socket.gaierror, OSError):
            return "retry", 0, "webhook_resolution_failed"
        except HTTPException as exc:
            if isinstance(exc.__cause__, socket.gaierror):
                return "retry", 0, "webhook_resolution_failed"
            return "failed", 0, "unsafe_webhook_url"
        except (TypeError, ValueError):
            return "failed", 0, "unsafe_webhook_url"
        secret = current["hook_secret"]
        if not secret:
            return "retry", 0, "missing_webhook_secret"
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {
        "content-type": "application/json",
        "x-matchall-signature": f"sha256={signature}",
    }
    if event["webhook_id"] is not None:
        headers["x-matchall-event"] = event["event_type"]
        headers["x-matchall-event-id"] = event["event_id"]
    try:
        response = await client.post(url, content=raw, headers=headers,
                                     timeout=REQUEST_TIMEOUT, follow_redirects=False)
    except httpx.TimeoutException:
        return "retry", 0, "network_timeout"
    except httpx.HTTPError:
        return "retry", 0, "network_error"
    code = response.status_code
    return ("delivered", code, "") if 200 <= code < 300 else ("retry", code, "http_error")


async def deliver_pending_events(db, *, client, hub_url, hub_secret, validate_url,
                                 now=None, limit=20):
    """Attempt a bounded batch, leaving interrupted claims recoverable via their lease."""
    clock = now if now is not None else time.time
    counts = dict.fromkeys(("claimed", "delivered", "retried", "cancelled", "failed", "lost_claim"), 0)
    for _ in range(limit):
        event = claim_event(db, int(clock()))
        if event is None:
            break
        counts["claimed"] += 1
        try:
            async with asyncio.timeout(ATTEMPT_TIMEOUT):
                outcome, code, error = await _deliver_event(
                    db, event, client=client, hub_url=hub_url,
                    hub_secret=hub_secret, validate_url=validate_url)
        except TimeoutError:
            outcome, code, error = "retry", 0, "attempt_timeout"
        except Exception:
            # Diagnostics may contain URLs, credentials or response bodies.
            # Persist only this fixed class; task cancellation propagates.
            outcome, code, error = "retry", 0, "delivery_error"
        if outcome == "lost":
            counts["lost_claim"] += 1
            continue
        status = _finish_event(db, event, now=int(clock()), outcome=outcome,
                               status_code=code, error=error)
        if status is None:
            counts["lost_claim"] += 1
        else:
            counts["retried" if status == "pending" else status] += 1
    return counts
