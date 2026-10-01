import asyncio
import hashlib
import json
import os
import secrets
import sqlite3
import time
import hmac
import re
import html as html_lib
import smtplib
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
import markdown
from pywebpush import webpush
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from jinja2 import Environment, FileSystemLoader, select_autoescape

os.umask(0o077)

CONSOLE_URL = os.getenv("CONSOLE_URL", "https://console.maximoraverse.org").rstrip("/")
STATUS_URL = os.getenv("STATUS_URL", "https://status.maximoraverse.org").rstrip("/")
DOCS_URL = os.getenv("DOCS_URL", "https://docs.maximoraverse.org").rstrip("/")
OIDC_ENDPOINT = os.getenv("OIDC_ENDPOINT", "https://auth.maximoraverse.org/application/o").rstrip("/")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "matchall-console")
OIDC_CLIENT_SECRET_FILE = os.getenv("OIDC_CLIENT_SECRET_FILE", "/run/secrets/oidc_client_secret")
SESSION_SECRET_FILE = os.getenv("SESSION_SECRET_FILE", "/run/secrets/session_secret")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
SNAPSHOT_DIR = DATA_DIR / "snapshots"
STATUS_DB = DATA_DIR / "status" / "status.db"
NOTIFY_DB = DATA_DIR / "notifications" / "notifications.db"
DOCS_DIR = Path(os.getenv("DOCS_DIR", "/app/docs"))
EVENT_SECRET_FILE = os.getenv("EVENT_SECRET_FILE", "/run/secrets/event_secret")
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_SECURE = os.getenv("SMTP_SECURE", "tls").strip().lower()
SMTP_USER_FILE = os.getenv("SMTP_USER_FILE", "/run/secrets/smtp_user")
SMTP_PASSWORD_FILE = os.getenv("SMTP_PASSWORD_FILE", "/run/secrets/smtp_password")
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or ((os.getenv("MAIL_FROM_ADDRESS", "notifications").strip() or "notifications") + "@" + (os.getenv("MAIL_DOMAIN", "maximoraverse.org").strip() or "maximoraverse.org"))
TELEGRAM_BOT_TOKEN_FILE = os.getenv("TELEGRAM_BOT_TOKEN_FILE", "/run/secrets/telegram_bot_token")
TELEGRAM_CHAT_ID_FILE = os.getenv("TELEGRAM_CHAT_ID_FILE", "/run/secrets/telegram_chat_id")
VAPID_PRIVATE_KEY_FILE = os.getenv("VAPID_PRIVATE_KEY_FILE", "/run/secrets/vapid_private.pem")
VAPID_PUBLIC_KEY_FILE = os.getenv("VAPID_PUBLIC_KEY_FILE", "/run/secrets/vapid_public.txt")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:notifications@maximoraverse.org")
WPS365_CLI = os.getenv("WPS365_CLI", "/usr/local/bin/wps365-cli")
WPS365_CONFIG_DIR = Path(os.getenv("WPS365_CONFIG_DIR", "/data/wps365"))
WPS365_KEYRING_PASSWORD_FILE = os.getenv("WPS365_KEYRING_PASSWORD_FILE", "/run/secrets/wps365_keyring_password")
WPS_AGENT_DIR = DATA_DIR / "wps-agent"
WPS_AGENT_API_KEY_FILE = WPS_AGENT_DIR / "api-key.secret"
WPS_AGENT_STATUS_FILE = WPS_AGENT_DIR / "status.json"
WPS_AGENT_TOKEN_URL = "https://account.wps.cn/api/authorization/agent/v1/token"

_wps_lock = threading.Lock()
_wps_process = None
_wps_process_kind = ""

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#0b1020"/><path d="M32 10 52 32 32 54 12 32Z" fill="#6ea8ff"/><path d="M32 20 42 32 32 44 22 32Z" fill="#f8fafc"/></svg>"""


def read_secret(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except FileNotFoundError:
        return ""


serializer = URLSafeTimedSerializer(read_secret(SESSION_SECRET_FILE) or secrets.token_urlsafe(48), salt="matchall-console")
templates = Environment(loader=FileSystemLoader("templates"), autoescape=select_autoescape(["html", "xml"]))

PROBE_INTERVAL_SECONDS = 60
STALE_AFTER_SECONDS = 180
PROBE_REGION = "MatchAll 服务网络"

SERVICES = [
    {"key": "home", "name": "MatchAll 主站", "name_en": "MatchAll Home", "category": "content", "url": "https://www.maximoraverse.org/", "probe": "https://www.maximoraverse.org/", "expect": [200], "threshold": 1200, "check_type": "HTTPS GET", "scope": "仅验证主站首页可达与返回 HTTP 200；不覆盖站外链接或第三方资源。", "help_url": "https://www.maximoraverse.org/contact/"},
    {"key": "blog", "name": "技术博客", "name_en": "Blog", "category": "content", "url": "https://blog.maximoraverse.org/", "probe": "https://blog.maximoraverse.org/", "expect": [200], "threshold": 1200, "check_type": "HTTPS GET", "scope": "仅验证博客首页可达与返回 HTTP 200；不覆盖搜索、评论或全部文章。", "help_url": "https://blog.maximoraverse.org/docs/"},
    {"key": "account", "name": "统一账户", "name_en": "Account", "category": "identity", "url": "https://auth.maximoraverse.org/", "probe": "http://authentik-server:9000/-/health/live/", "expect": [200, 204], "threshold": 900, "check_type": "应用存活探针", "scope": "验证认证服务进程存活；不执行真实登录、注册、验证码或令牌签发。", "help_url": "https://blog.maximoraverse.org/docs/account-security/"},
    {"key": "drive", "name": "云端网盘", "name_en": "Drive", "category": "data", "url": "https://drive.maximoraverse.org/", "probe": "https://drive.maximoraverse.org/status.php", "expect": [200], "threshold": 1200, "check_type": "公开状态端点", "scope": "验证网盘公开状态端点；不创建文件，不覆盖登录、上传、下载或分享全过程。", "help_url": "https://blog.maximoraverse.org/docs/drive-guide/"},
    {"key": "mirrors", "name": "软件镜像", "name_en": "Mirrors", "category": "distribution", "url": "https://mirrors.maximoraverse.org/", "probe": "http://mirrors:8000/healthz", "expect": [200], "threshold": 900, "check_type": "应用健康端点", "scope": "验证 Mirrors 应用健康端点；不创建发布，不下载大文件，也不验证付费授权全过程。", "help_url": "https://blog.maximoraverse.org/docs/mirrors-user/"},
    {"key": "network", "name": "网络服务", "name_en": "Network", "category": "network", "url": "https://proxyservice.maximoraverse.org/", "probe": "http://xboard:7001/api/v1/guest/comm/config", "expect": [200], "threshold": 1000, "check_type": "只读公共配置 API", "scope": "验证公共配置 API 可响应；不发起购买，不验证节点连通性、订阅更新或端到端流量。", "help_url": "https://blog.maximoraverse.org/docs/network-guide/"},
]

I18N = {
    "zh": {"console": "统一用户中心", "status": "服务状态", "logout": "退出", "login": "使用 MatchAll 账户登录", "skip": "跳到主要内容", "account": "账户", "privacy": "隐私", "terms": "条款", "contact": "联系", "anon_title": "一个账户，管理全部服务。", "anon_desc": "统一查看云存储、网络套餐、软件授权和服务运行状态。Console 只读取汇总信息，不保存业务密码。", "view_status": "查看服务状态", "overall_ok": "所有服务运行正常", "overall_slow": "部分服务响应较慢", "overall_down": "部分服务暂时不可用", "status_desc": "每分钟从业务网络内部执行真实健康探测；状态需要连续两次失败才会标记为中断。", "incident_history": "事件记录", "no_incident": "暂无服务事件", "no_incident_desc": "监控开始后没有记录到连续故障。", "hours": "24小时"},
    "en": {"console": "Unified Console", "status": "Service Status", "logout": "Sign out", "login": "Sign in with MatchAll", "skip": "Skip to content", "account": "Account", "privacy": "Privacy", "terms": "Terms", "contact": "Contact", "anon_title": "One account. Every service.", "anon_desc": "See cloud storage, network plans, software access and live service health in one place. Console reads summaries and never stores service passwords.", "view_status": "View service status", "overall_ok": "All services are operational", "overall_slow": "Some services are responding slowly", "overall_down": "Some services are unavailable", "status_desc": "Real health checks run every minute from the service network. Two consecutive failures are required before an outage is declared.", "incident_history": "Incident history", "no_incident": "No incidents", "no_incident_desc": "No consecutive service failures have been recorded since monitoring began.", "hours": "24 hours"},
    "ja": {"console": "統合ユーザーセンター", "status": "サービス状態", "logout": "ログアウト", "login": "MatchAll アカウントでログイン", "skip": "本文へ移動", "account": "アカウント", "privacy": "プライバシー", "terms": "規約", "contact": "お問い合わせ", "anon_title": "一つのアカウントですべてを管理。", "anon_desc": "クラウド容量、ネットワークプラン、ソフトウェア利用権、サービス状態を一か所で確認。パスワードは保存せず、要約情報のみ読み取ります。", "view_status": "サービス状態を見る", "overall_ok": "すべてのサービスは正常です", "overall_slow": "一部のサービスが遅延しています", "overall_down": "一部のサービスを利用できません", "status_desc": "サービスネットワークから毎分ヘルスチェックを実行し、2回連続で失敗した場合のみ障害として表示します。", "incident_history": "障害履歴", "no_incident": "障害はありません", "no_incident_desc": "監視開始後、連続したサービス障害は記録されていません。", "hours": "24時間"},
}


def status_db():
    STATUS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(STATUS_DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=3000")
    return con


def init_status_db():
    with status_db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS checks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          service_key TEXT NOT NULL,
          checked_at INTEGER NOT NULL,
          ok INTEGER NOT NULL,
          latency_ms INTEGER NOT NULL,
          status_code INTEGER NOT NULL DEFAULT 0,
          detail TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_checks_service_time ON checks(service_key, checked_at DESC);
        CREATE TABLE IF NOT EXISTS incidents (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          service_key TEXT NOT NULL,
          started_at INTEGER NOT NULL,
          resolved_at INTEGER,
          title TEXT NOT NULL,
          detail TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS maintenance (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          service_key TEXT NOT NULL,
          starts_at INTEGER NOT NULL,
          ends_at INTEGER,
          title TEXT NOT NULL,
          detail TEXT NOT NULL DEFAULT '',
          workaround TEXT NOT NULL DEFAULT '',
          next_update_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_maintenance_time ON maintenance(starts_at DESC);
        CREATE TABLE IF NOT EXISTS csp_reports (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          reported_at INTEGER NOT NULL,
          document_uri TEXT NOT NULL DEFAULT '',
          violated_directive TEXT NOT NULL DEFAULT '',
          blocked_uri TEXT NOT NULL DEFAULT '',
          source_file TEXT NOT NULL DEFAULT '',
          line_number INTEGER NOT NULL DEFAULT 0,
          column_number INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_csp_reports_time ON csp_reports(reported_at DESC);
        """)


def notify_db():
    NOTIFY_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(NOTIFY_DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=3000")
    return con


def init_notify_db():
    with notify_db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS notifications (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_key TEXT UNIQUE,
          kind TEXT NOT NULL,
          severity TEXT NOT NULL DEFAULT 'info',
          title TEXT NOT NULL,
          body TEXT NOT NULL,
          action_url TEXT NOT NULL DEFAULT '',
          audience TEXT NOT NULL DEFAULT 'users',
          created_at INTEGER NOT NULL,
          expires_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_time ON notifications(created_at DESC);
        CREATE TABLE IF NOT EXISTS notification_reads (
          notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
          user_sub TEXT NOT NULL,
          read_at INTEGER NOT NULL,
          PRIMARY KEY(notification_id,user_sub)
        );
        CREATE TABLE IF NOT EXISTS docs_feedback (
          article_slug TEXT NOT NULL,
          user_key TEXT NOT NULL,
          helpful INTEGER NOT NULL,
          created_at INTEGER NOT NULL,
          PRIMARY KEY(article_slug,user_key)
        );
        CREATE TABLE IF NOT EXISTS notification_preferences (
          user_sub TEXT PRIMARY KEY,
          email TEXT NOT NULL DEFAULT '',
          email_enabled INTEGER NOT NULL DEFAULT 0,
          webpush_enabled INTEGER NOT NULL DEFAULT 0,
          updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS push_subscriptions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_sub TEXT NOT NULL,
          endpoint TEXT UNIQUE NOT NULL,
          p256dh TEXT NOT NULL,
          auth TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS delivery_jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
          channel TEXT NOT NULL,
          recipient TEXT NOT NULL DEFAULT '',
          user_sub TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt_at INTEGER NOT NULL,
          last_error TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL,
          sent_at INTEGER,
          UNIQUE(notification_id,channel,recipient,user_sub)
        );
        CREATE INDEX IF NOT EXISTS idx_delivery_pending ON delivery_jobs(status,next_attempt_at);
        """)


def enqueue_delivery_jobs(con, notification_id: int):
    now = int(time.time())
    chat_id = read_secret(TELEGRAM_CHAT_ID_FILE)
    if read_secret(TELEGRAM_BOT_TOKEN_FILE) and chat_id:
        con.execute("""INSERT OR IGNORE INTO delivery_jobs
          (notification_id,channel,recipient,status,next_attempt_at,created_at)
          VALUES(?,'telegram',?,'pending',?,?)""", (notification_id, chat_id, now, now))
    for pref in con.execute("SELECT * FROM notification_preferences").fetchall():
        if pref["email_enabled"] and pref["email"] and SMTP_HOST:
            con.execute("""INSERT OR IGNORE INTO delivery_jobs
              (notification_id,channel,recipient,user_sub,status,next_attempt_at,created_at)
              VALUES(?,'email',?,?,'pending',?,?)""", (notification_id, pref["email"], pref["user_sub"], now, now))
        if pref["webpush_enabled"]:
            for sub in con.execute("SELECT endpoint FROM push_subscriptions WHERE user_sub=? AND active=1", (pref["user_sub"],)).fetchall():
                con.execute("""INSERT OR IGNORE INTO delivery_jobs
                  (notification_id,channel,recipient,user_sub,status,next_attempt_at,created_at)
                  VALUES(?,'webpush',?,?,'pending',?,?)""", (notification_id, sub["endpoint"], pref["user_sub"], now, now))


def publish_notification(*, event_key: str, kind: str, severity: str, title: str, body: str,
                         action_url: str = "", audience: str = "users", deliver_external: bool = True):
    with notify_db() as con:
        cur = con.execute("""INSERT OR IGNORE INTO notifications
          (event_key,kind,severity,title,body,action_url,audience,created_at)
          VALUES(?,?,?,?,?,?,?,?)""",
          (event_key, kind, severity, title[:180], body[:2000], action_url[:500], audience, int(time.time())))
        if deliver_external and cur.rowcount:
            row = con.execute("SELECT id FROM notifications WHERE event_key=?", (event_key,)).fetchone()
            if row:
                enqueue_delivery_jobs(con, row["id"])


async def deliver_job(job):
    if job["channel"] == "telegram":
        token = read_secret(TELEGRAM_BOT_TOKEN_FILE)
        if not token:
            raise RuntimeError("telegram_not_configured")
        text = f"{job['title']}\n\n{job['body']}" + (f"\n\n{job['action_url']}" if job["action_url"] else "")
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": job["recipient"], "text": text[:4096], "disable_web_page_preview": True})
            response.raise_for_status()
        return
    if job["channel"] == "email":
        msg = EmailMessage(); msg["Subject"] = job["title"]; msg["From"] = SMTP_FROM; msg["To"] = job["recipient"]
        msg.set_content(job["body"] + (f"\n\n{job['action_url']}" if job["action_url"] else ""))
        user, password = read_secret(SMTP_USER_FILE), read_secret(SMTP_PASSWORD_FILE)
        def send():
            smtp_class = smtplib.SMTP_SSL if SMTP_SECURE in {"ssl", "smtps"} else smtplib.SMTP
            with smtp_class(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
                if SMTP_SECURE not in {"ssl", "smtps", "none", "off", "null", ""}:
                    smtp.starttls()
                if user and user.lower() not in {"none", "off", "null"}:
                    smtp.login(user, password)
                smtp.send_message(msg)
        await asyncio.to_thread(send)
        return
    if job["channel"] == "webpush":
        with notify_db() as con:
            sub = con.execute("SELECT * FROM push_subscriptions WHERE endpoint=? AND active=1", (job["recipient"],)).fetchone()
        if not sub:
            raise RuntimeError("push_subscription_missing")
        payload = json.dumps({"title": job["title"], "body": job["body"], "url": job["action_url"] or f"{CONSOLE_URL}/notifications"}, ensure_ascii=False)
        await asyncio.to_thread(webpush, subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
            data=payload, vapid_private_key=VAPID_PRIVATE_KEY_FILE, vapid_claims={"sub": VAPID_SUBJECT})
        return
    raise RuntimeError("unsupported_channel")


async def delivery_loop():
    while True:
        now = int(time.time())
        with notify_db() as con:
            rows = con.execute("""SELECT j.*,n.title,n.body,n.action_url FROM delivery_jobs j
              JOIN notifications n ON n.id=j.notification_id WHERE j.status='pending' AND j.next_attempt_at<=?
              ORDER BY j.id LIMIT 20""", (now,)).fetchall()
        for row in rows:
            try:
                await deliver_job(row)
                with notify_db() as con:
                    con.execute("UPDATE delivery_jobs SET status='sent',attempts=attempts+1,sent_at=?,last_error='' WHERE id=?", (int(time.time()), row["id"]))
            except Exception as exc:
                attempts = row["attempts"] + 1; status = "failed" if attempts >= 5 else "pending"
                with notify_db() as con:
                    con.execute("UPDATE delivery_jobs SET status=?,attempts=?,next_attempt_at=?,last_error=? WHERE id=?",
                                (status, attempts, int(time.time()) + min(3600, 30 * (2 ** attempts)), exc.__class__.__name__[:120], row["id"]))
        await asyncio.sleep(10)


def active_maintenance(con, key: str, now: int):
    row = con.execute("""SELECT id,service_key,starts_at,ends_at,title,detail,workaround,next_update_at
      FROM maintenance WHERE service_key=? AND starts_at<=? AND (ends_at IS NULL OR ends_at>?)
      ORDER BY starts_at DESC LIMIT 1""", (key, now, now)).fetchone()
    return dict(row) if row else None


def public_status(con, service: dict, now: int | None = None):
    """Return the six-state public status without treating missing data as failure."""
    now = int(now or time.time())
    maintenance = active_maintenance(con, service["key"], now)
    if maintenance:
        return "maintenance", maintenance
    rows = con.execute("SELECT checked_at,ok,latency_ms,status_code,detail FROM checks WHERE service_key=? ORDER BY checked_at DESC LIMIT 3", (service["key"],)).fetchall()
    if not rows or now - int(rows[0]["checked_at"]) > STALE_AFTER_SECONDS:
        return "unknown", None
    if not rows[0]["ok"]:
        if len(rows) >= 2 and not rows[1]["ok"]:
            return "outage", None
        return "partial_outage", None
    if rows[0]["latency_ms"] > service["threshold"]:
        return "degraded", None
    return "operational", None


def legacy_state(status: str):
    return {"operational": "operational", "degraded": "degraded", "maintenance": "degraded",
            "partial_outage": "down", "outage": "down", "unknown": "unknown"}.get(status, "unknown")


def overall_status(services):
    """Return the most actionable public state; unknown never hides a known incident."""
    states = {item.get("status", "unknown") for item in services}
    for state in ("outage", "partial_outage", "degraded", "maintenance", "unknown", "operational"):
        if state in states:
            return state
    return "unknown"


def maintenance_overlap_seconds(con, service_key: str, start: int, end: int):
    rows = con.execute("""SELECT starts_at,ends_at FROM maintenance
      WHERE service_key=? AND starts_at<? AND COALESCE(ends_at,?)>?""",
      (service_key, end, end, start)).fetchall()
    return sum(max(0, min(end, int(row["ends_at"] or end)) - max(start, int(row["starts_at"]))) for row in rows)


def effective_state(con, key: str):
    service = next(s for s in SERVICES if s["key"] == key)
    status, _ = public_status(con, service)
    return legacy_state(status)


async def probe_once():
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for service in SERVICES:
            started = time.perf_counter()
            ok, code, detail = False, 0, ""
            try:
                response = await client.get(service["probe"], headers={"User-Agent": "MatchAll-Status/1.0"})
                code = response.status_code
                ok = code in service["expect"]
                if not ok:
                    detail = f"HTTP {code}"
            except Exception as exc:
                detail = exc.__class__.__name__
            latency = max(1, int((time.perf_counter() - started) * 1000))
            now = int(time.time())
            with status_db() as con:
                before, _ = public_status(con, service, now)
                con.execute("INSERT INTO checks(service_key,checked_at,ok,latency_ms,status_code,detail) VALUES(?,?,?,?,?,?)",
                            (service["key"], now, int(ok), latency, code, detail[:120]))
                after, _ = public_status(con, service, now)
                if after == "outage" and before != "outage":
                    con.execute("INSERT INTO incidents(service_key,started_at,title,detail) VALUES(?,?,?,?)",
                                (service["key"], now, f"{service['name']} 暂时不可用", detail[:120]))
                    publish_notification(event_key=f"status:{service['key']}:down:{now}", kind="status",
                      severity="critical", title=f"{service['name']} 暂时不可用",
                      body="状态监控连续两次未能完成健康检查。", action_url=STATUS_URL, audience="public")
                elif after in {"operational", "degraded"} and before in {"outage", "partial_outage"}:
                    con.execute("UPDATE incidents SET resolved_at=? WHERE service_key=? AND resolved_at IS NULL", (now, service["key"]))
                    publish_notification(event_key=f"status:{service['key']}:resolved:{now}", kind="status",
                      severity="success", title=f"{service['name']} 已恢复",
                      body="服务健康检查已经恢复正常。", action_url=STATUS_URL, audience="public")
                con.execute("DELETE FROM checks WHERE checked_at < ?", (now - 86400 * 90,))


async def probe_loop():
    await probe_once()
    while True:
        await asyncio.sleep(60)
        await probe_once()


@asynccontextmanager
async def lifespan(_: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    init_status_db()
    init_notify_db()
    task = asyncio.create_task(probe_loop())
    delivery_task = asyncio.create_task(delivery_loop())
    try:
        yield
    finally:
        task.cancel()
        delivery_task.cancel()


app = FastAPI(title="MatchAll Hub", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


def request_lang(request: Request):
    value = request.query_params.get("lang") or request.cookies.get("matchall_lang", "")
    if value in I18N:
        return value
    header = request.headers.get("accept-language", "").lower()
    return "ja" if header.startswith("ja") else "en" if header.startswith("en") else "zh"


def render(name: str, request: Request, **context):
    lang = request_lang(request)
    html = templates.get_template(name).render(request=request, lang=lang, t=I18N[lang], now=int(time.time()), **context)
    if name in {"docs_index.html", "docs_article.html", "notifications.html"}:
        html = html.replace("</head>", '<link rel="stylesheet" href="/static/portal.css"></head>')
    response = HTMLResponse(html)
    if request.query_params.get("lang") in I18N:
        response.set_cookie("matchall_lang", lang, max_age=86400 * 365, domain=".maximoraverse.org", secure=True, samesite="lax")
    return response


def get_user(request: Request):
    raw = request.cookies.get("console_session")
    if not raw:
        return None
    try:
        return serializer.loads(raw, max_age=86400 * 7)
    except BadSignature:
        return None


def is_admin(user):
    groups = {str(x).lower() for x in (user or {}).get("groups", [])}
    return bool({"authentik admins", "matchall admins", "admins", "admin"} & groups)


def require_user(request: Request):
    user = get_user(request)
    if not user:
        raise HTTPException(401, "Login required")
    return user


def check_csrf(user, token):
    if not token or not secrets.compare_digest(str(user.get("csrf", "")), str(token)):
        raise HTTPException(403, "CSRF validation failed")


def wps_cli_env():
    env = os.environ.copy()
    env.update({
        "WPS365_CONFIG_DIR": str(WPS365_CONFIG_DIR),
        "WPS365_KEYRING_BACKEND": "file",
        "WPS365_KEYRING_PASSWORD": read_secret(WPS365_KEYRING_PASSWORD_FILE),
        "BROWSER": "/bin/false",
        "NO_COLOR": "1",
    })
    return env


def wps_cli_json(*args):
    try:
        result = subprocess.run([WPS365_CLI, *args, "--output", "json", "--no-color"],
                                env=wps_cli_env(), capture_output=True, text=True, timeout=20, check=False)
        if result.returncode == 0:
            return json.loads(result.stdout), ""
        return {}, (result.stderr or "WPS CLI command failed").strip()[:300]
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {}, str(exc)[:300]


def wps_flow_state():
    global _wps_process, _wps_process_kind
    with _wps_lock:
        process = _wps_process
        running = bool(process and process.poll() is None)
        exit_code = None if not process or running else process.returncode
        kind = _wps_process_kind
    log_path = WPS365_CONFIG_DIR / "setup-flow.log"
    try:
        flow_output = log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
    except FileNotFoundError:
        flow_output = ""
    official_urls = []
    for raw_url in re.findall(r"https://[^\s<>\"]+", flow_output):
        url = raw_url.rstrip(".,;，。；)")
        host = (urlparse(url).hostname or "").lower()
        if (host == "wps.cn" or host.endswith(".wps.cn")) and url not in official_urls:
            official_urls.append(url)
    return {"running": running, "exit_code": exit_code, "kind": kind,
            "output": flow_output, "official_urls": official_urls[:3]}


def start_wps_flow(kind: str):
    global _wps_process, _wps_process_kind
    if kind not in {"app", "login"}:
        raise HTTPException(400, "Invalid WPS flow")
    WPS365_CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = WPS365_CONFIG_DIR / "setup-flow.log"
    with _wps_lock:
        if _wps_process and _wps_process.poll() is None:
            raise HTTPException(409, "A WPS authorization flow is already running")
        command = ([WPS365_CLI, "config", "init", "--new", "--force", "--no-color"] if kind == "app"
                   else [WPS365_CLI, "auth", "login", "--device", "--no-color"])
        log_file = open(log_path, "w", encoding="utf-8")
        os.chmod(log_path, 0o600)
        try:
            _wps_process = subprocess.Popen(command, env=wps_cli_env(), stdin=subprocess.DEVNULL,
                                            stdout=log_file, stderr=subprocess.STDOUT, text=True)
            _wps_process_kind = kind
        finally:
            log_file.close()


def validate_wps_agent_key(api_key: str):
    if not re.fullmatch(r"apik:\S{16,}", api_key):
        raise HTTPException(400, "WPS Agent API Key format is invalid")
    try:
        response = httpx.post(WPS_AGENT_TOKEN_URL,
                              json={"grant_type": "api_key", "api_key": api_key}, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise HTTPException(502, "WPS Agent authentication endpoint is unavailable") from exc
    if payload.get("result") != "ok" or not (payload.get("data") or {}).get("access_token"):
        raise HTTPException(400, "WPS Agent API Key was rejected")
    return int((payload.get("data") or {}).get("expires_in") or 0)


def save_wps_agent_key(api_key: str, *, verified_by: str, expires_in: int):
    WPS_AGENT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_temp = WPS_AGENT_DIR / "api-key.secret.tmp"
    key_temp.write_text(api_key, encoding="utf-8")
    os.chmod(key_temp, 0o600)
    os.replace(key_temp, WPS_AGENT_API_KEY_FILE)
    status_temp = WPS_AGENT_DIR / "status.json.tmp"
    status_temp.write_text(json.dumps({"verified_at": int(time.time()), "verified_by": verified_by,
                                       "token_lifetime_seconds": expires_in}), encoding="utf-8")
    os.chmod(status_temp, 0o600)
    os.replace(status_temp, WPS_AGENT_STATUS_FILE)


def wps_agent_status():
    status = {"configured": WPS_AGENT_API_KEY_FILE.is_file(), "verified_at": 0,
              "token_lifetime_seconds": 0}
    try:
        status.update(json.loads(WPS_AGENT_STATUS_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    status.pop("verified_by", None)
    return status


def load_docs():
    articles = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = {}, text
        if text.startswith("---\n"):
            head, body = text[4:].split("\n---\n", 1)
            for line in head.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
        plain = re.sub(r"[`#>*_\[\]()]", " ", body)
        articles.append({"slug": path.stem, "title": meta.get("title", path.stem),
          "summary": meta.get("summary", ""), "category": meta.get("category", "指南"),
          "version": meta.get("version", "1.0"), "updated": meta.get("updated", ""),
          "body": body, "plain": re.sub(r"\s+", " ", plain).strip()})
    return articles


def load_snapshot(name: str):
    try:
        return json.loads((SNAPSHOT_DIR / f"{name}.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"generated_at": 0, "users": []}


def find_record(rows, user, *, subject=True, username=True, email=True):
    user_sub = user.get("sub")
    if not isinstance(user_sub, str) or not user_sub:
        return None
    rows = list(rows)
    if subject:
        matches = [row for row in rows if row.get("subject") == user_sub]
        if matches:
            return matches[0] if len(matches) == 1 else None
    # Legacy snapshots (including Drive) can lack a shared subject. A fallback
    # must be unique and must never override an explicitly conflicting subject.
    user_name, user_email = user.get("preferred_username"), user.get("email")
    matches = []
    for row in rows:
        name_match = username and isinstance(user_name, str) and bool(user_name) and row.get("username") == user_name
        row_email = row.get("email")
        email_match = email and isinstance(user_email, str) and bool(user_email) and isinstance(row_email, str) and row_email.lower() == user_email.lower()
        if name_match or email_match:
            matches.append(row)
    if len(matches) != 1:
        return None
    match = matches[0]
    return match if not match.get("subject") or match["subject"] == user_sub else None


def bytes_human(value):
    value = int(value or 0)
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def timestamp_human(value):
    if not value:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(value)))
    except (ValueError, TypeError):
        return str(value)


templates.globals.update(bytes_human=bytes_human, timestamp_human=timestamp_human)


def status_summary(now: int | None = None):
    now = int(now or time.time())
    cutoff_24h = now - 86400
    today_utc = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_30d = int((today_utc - timedelta(days=29)).timestamp())
    result = []
    with status_db() as con:
        for service in SERVICES:
            latest = con.execute("SELECT * FROM checks WHERE service_key=? ORDER BY checked_at DESC LIMIT 1", (service["key"],)).fetchone()
            last_success = con.execute("SELECT checked_at FROM checks WHERE service_key=? AND ok=1 ORDER BY checked_at DESC LIMIT 1", (service["key"],)).fetchone()
            stats_24h = con.execute("""SELECT COUNT(*) total,SUM(ok) good,
              AVG(CASE WHEN ok=1 THEN latency_ms END) avg_latency FROM checks c
              WHERE service_key=? AND checked_at>=? AND NOT EXISTS (
                SELECT 1 FROM maintenance m WHERE m.service_key=c.service_key
                AND m.starts_at<=c.checked_at AND (m.ends_at IS NULL OR m.ends_at>c.checked_at))""",
              (service["key"], cutoff_24h)).fetchone()
            stats_30d = con.execute("""SELECT COUNT(*) total,SUM(ok) good,MIN(checked_at) first_at,MAX(checked_at) last_at
              FROM checks c WHERE service_key=? AND checked_at>=? AND NOT EXISTS (
                SELECT 1 FROM maintenance m WHERE m.service_key=c.service_key
                AND m.starts_at<=c.checked_at AND (m.ends_at IS NULL OR m.ends_at>c.checked_at))""",
              (service["key"], cutoff_30d)).fetchone()
            first_ever = con.execute("SELECT MIN(checked_at) first_at FROM checks WHERE service_key=?", (service["key"],)).fetchone()
            history = con.execute("SELECT ok,latency_ms FROM checks WHERE service_key=? ORDER BY checked_at DESC LIMIT 72", (service["key"],)).fetchall()[::-1]
            total_24h, good_24h = int(stats_24h["total"] or 0), int(stats_24h["good"] or 0)
            total_30d, good_30d = int(stats_30d["total"] or 0), int(stats_30d["good"] or 0)
            coverage_start = max(cutoff_30d, int(first_ever["first_at"])) if first_ever and first_ever["first_at"] is not None else None
            coverage_end = min(now, int(stats_30d["last_at"])) if stats_30d["last_at"] is not None else None
            covered_seconds = max(0, now - coverage_start) if coverage_start is not None else 0
            maintained_seconds = maintenance_overlap_seconds(con, service["key"], coverage_start, now) if covered_seconds else 0
            expected_30d = max(0, (covered_seconds - maintained_seconds) // PROBE_INTERVAL_SECONDS + (1 if total_30d else 0))
            coverage_ratio = min(100.0, total_30d * 100 / expected_30d) if expected_30d else None
            status, maintenance = public_status(con, service, now)
            latest_dict = dict(latest) if latest else None
            result.append({**service, "status": status, "state": legacy_state(status), "latest": latest_dict,
                           "last_checked_at": int(latest["checked_at"]) if latest else None,
                           "last_success_at": int(last_success["checked_at"]) if last_success else None,
                           "stale": not latest or now - int(latest["checked_at"]) > STALE_AFTER_SECONDS,
                           "uptime": round(good_24h * 100 / total_24h, 3) if total_24h else None,
                           "uptime_30d": round(good_30d * 100 / total_30d, 3) if total_30d else None,
                           "sample_count_24h": total_24h, "sample_count_30d": total_30d,
                           "successful_samples_30d": good_30d,
                           "monitoring_started_at": int(first_ever["first_at"]) if first_ever and first_ever["first_at"] is not None else None,
                           "coverage_start_at": coverage_start, "coverage_end_at": coverage_end,
                           "expected_samples_30d": expected_30d,
                           "coverage_ratio_30d": round(coverage_ratio, 2) if coverage_ratio is not None else None,
                           "coverage_complete_30d": bool(coverage_start is not None and coverage_start <= cutoff_30d + PROBE_INTERVAL_SECONDS and coverage_ratio is not None and coverage_ratio >= 95),
                           "maintenance_seconds_30d": maintained_seconds,
                           "avg_latency": int(stats_24h["avg_latency"]) if stats_24h["avg_latency"] is not None else None,
                           "latency_window": "24h", "probe_region": PROBE_REGION,
                           "probe_interval_seconds": PROBE_INTERVAL_SECONDS, "maintenance": maintenance,
                           "history": ["up" if x["ok"] else "down" for x in history]})
        incidents = [dict(x) for x in con.execute("SELECT * FROM incidents ORDER BY started_at DESC LIMIT 12").fetchall()]
    return result, incidents


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/robots.txt", include_in_schema=False)
def robots(request: Request):
    host = request.headers.get("host", "").split(":", 1)[0].lower()
    if host.startswith("console."):
        body = "User-agent: *\nDisallow: /\n"
    elif host.startswith("docs."):
        body = f"User-agent: *\nAllow: /\nSitemap: {DOCS_URL}/sitemap.xml\n"
    else:
        body = f"User-agent: *\nAllow: /\nSitemap: {STATUS_URL}/sitemap.xml\n"
    return Response(body, media_type="text/plain", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request):
    host = request.headers.get("host", "").split(":", 1)[0].lower()
    if host.startswith("console."):
        raise HTTPException(status_code=404, detail="not found")
    urls = [f"{STATUS_URL}/", f"{STATUS_URL}/feed.xml"]
    if host.startswith("docs."):
        urls = [f"{DOCS_URL}/"] + [f"{DOCS_URL}/docs/{a['slug']}" for a in load_docs()]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
        f"  <url><loc>{html_lib.escape(url)}</loc></url>\n" for url in urls
    ) + "</urlset>\n"
    return Response(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    host = request.headers.get("host", "").split(":")[0]
    if host.startswith("status."):
        return status_page(request)
    if host.startswith("docs."):
        return docs_home(request)
    return console_page(request)


@app.get("/console", response_class=HTMLResponse)
def console_page(request: Request):
    user = get_user(request)
    services, _ = status_summary()
    if not user:
        return render("console.html", request, user=None, services=services, network=None, drive=None, mirrors=None, synced_at=0)
    xboard = load_snapshot("xboard")
    nextcloud = load_snapshot("nextcloud")
    mirror = load_snapshot("mirrors")
    network = find_record(xboard.get("users", []), user)
    drive = find_record(nextcloud.get("users", []), user, subject=False)
    mirrors = find_record(mirror.get("users", []), user)
    synced_at = min([x for x in [xboard.get("generated_at", 0), nextcloud.get("generated_at", 0), mirror.get("generated_at", 0)] if x] or [0])
    return render("console.html", request, user=user, services=services, network=network, drive=drive, mirrors=mirrors, synced_at=synced_at)


@app.get("/login")
def login():
    verifier = secrets.token_urlsafe(64)
    challenge = __import__("base64").urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(24)
    params = {"client_id": OIDC_CLIENT_ID, "response_type": "code", "redirect_uri": f"{CONSOLE_URL}/auth/callback",
              "scope": "openid profile email", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    response = RedirectResponse(f"{OIDC_ENDPOINT}/authorize/?{urlencode(params)}", status_code=302)
    response.set_cookie("console_oidc", serializer.dumps({"state": state, "verifier": verifier}), max_age=600, secure=True, httponly=True, samesite="lax")
    return response


@app.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    raw = request.cookies.get("console_oidc")
    if not raw or not code or not state:
        raise HTTPException(400, "OIDC callback invalid")
    try:
        saved = serializer.loads(raw, max_age=600)
    except BadSignature as exc:
        raise HTTPException(400, "OIDC state expired") from exc
    if not secrets.compare_digest(saved.get("state", ""), state):
        raise HTTPException(400, "OIDC state mismatch")
    secret = read_secret(OIDC_CLIENT_SECRET_FILE)
    async with httpx.AsyncClient(timeout=15.0) as client:
        token = await client.post(f"{OIDC_ENDPOINT}/token/", data={"grant_type": "authorization_code", "code": code,
                                  "redirect_uri": f"{CONSOLE_URL}/auth/callback", "client_id": OIDC_CLIENT_ID,
                                  "client_secret": secret, "code_verifier": saved["verifier"]})
        if token.status_code != 200:
            raise HTTPException(502, "OIDC token exchange failed")
        access = token.json().get("access_token", "")
        userinfo = await client.get(f"{OIDC_ENDPOINT}/userinfo/", headers={"Authorization": f"Bearer {access}"})
        if userinfo.status_code != 200:
            raise HTTPException(502, "OIDC userinfo failed")
        claims = userinfo.json()
    if not claims.get("sub"):
        raise HTTPException(502, "OIDC subject missing")
    session = {"sub": claims["sub"], "preferred_username": claims.get("preferred_username") or claims.get("nickname", ""),
               "name": claims.get("name", ""), "email": claims.get("email", ""), "groups": claims.get("groups", []),
               "csrf": secrets.token_urlsafe(24)}
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("console_oidc")
    response.set_cookie("console_session", serializer.dumps(session), max_age=86400 * 7, secure=True, httponly=True, samesite="lax")
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("console_session")
    return response


@app.get("/integrations/wps", response_class=HTMLResponse)
def wps_integration(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not is_admin(user):
        raise HTTPException(403, "Admin required")
    return render("wps_integration.html", request, user=user, agent=wps_agent_status())


@app.post("/integrations/wps/start")
def wps_integration_start(request: Request, csrf_token: str = Form(...), kind: str = Form(...)):
    user = require_user(request)
    check_csrf(user, csrf_token)
    if not is_admin(user):
        raise HTTPException(403, "Admin required")
    raise HTTPException(410, "WPS enterprise OAuth setup has been replaced by Agent API Key authentication")


@app.post("/integrations/wps/agent-key")
def wps_agent_key_save(request: Request, csrf_token: str = Form(...), agent_api_key: str = Form(...)):
    user = require_user(request)
    check_csrf(user, csrf_token)
    if not is_admin(user):
        raise HTTPException(403, "Admin required")
    api_key = agent_api_key.strip()
    expires_in = validate_wps_agent_key(api_key)
    save_wps_agent_key(api_key, verified_by=user["sub"], expires_in=expires_in)
    return RedirectResponse("/integrations/wps?configured=1", status_code=303)


@app.get("/status", response_class=HTMLResponse)
def status_page(request: Request):
    services, incidents = status_summary()
    overall = overall_status(services)
    return render("status.html", request, services=services, incidents=incidents, overall=overall)


@app.get("/api/status")
def status_api():
    services, incidents = status_summary()
    fields = ["key", "name", "name_en", "category", "url", "status", "state", "uptime", "uptime_30d",
              "sample_count_24h", "sample_count_30d", "avg_latency", "latency_window", "last_checked_at",
              "last_success_at", "stale", "probe_region", "probe_interval_seconds", "check_type", "scope",
              "help_url", "maintenance", "successful_samples_30d", "monitoring_started_at", "coverage_start_at",
              "coverage_end_at", "expected_samples_30d", "coverage_ratio_30d", "coverage_complete_30d",
              "maintenance_seconds_30d"]
    return JSONResponse({"schema_version": 2, "generated_at": int(time.time()), "stale_after_seconds": STALE_AFTER_SECONDS,
                         "services": [{k: x.get(k) for k in fields} for x in services], "incidents": incidents},
                        headers={"Cache-Control": "public, max-age=30"})


@app.get("/api/status/history")
def status_history(days: int = 30):
    """Return privacy-safe daily aggregates from the existing probe database."""
    days = max(1, min(int(days), 90))
    now = int(time.time())
    today = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    first_day = today - timedelta(days=days - 1)
    cutoff = int(first_day.timestamp())
    by_service = {service["key"]: {"key": service["key"], "name": service["name"], "days": []} for service in SERVICES}
    with status_db() as con:
        rows = con.execute("""
          SELECT service_key, date(checked_at, 'unixepoch') AS day,
                 COUNT(*) AS total, SUM(ok) AS good,
                 AVG(CASE WHEN ok=1 THEN latency_ms END) AS avg_latency
          FROM checks c WHERE checked_at >= ? AND NOT EXISTS (
            SELECT 1 FROM maintenance m WHERE m.service_key=c.service_key
            AND m.starts_at<=c.checked_at AND (m.ends_at IS NULL OR m.ends_at>c.checked_at))
          GROUP BY service_key, day ORDER BY day ASC
        """, (cutoff,)).fetchall()
    for row in rows:
        target = by_service.get(row["service_key"])
        if target is None:
            continue
        total, good = int(row["total"] or 0), int(row["good"] or 0)
        target["days"].append({
            "date": row["day"],
            "uptime": round(good * 100 / total, 3) if total else None,
            "avg_latency": int(row["avg_latency"] or 0),
            "checks": total,
        })
        maintenance_rows = con.execute("""SELECT service_key,starts_at,ends_at FROM maintenance
          WHERE starts_at<? AND COALESCE(ends_at,?)>?""", (now, now, cutoff)).fetchall()
    expected_dates = [(first_day + timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(days)]
    for target in by_service.values():
        indexed = {row["date"]: row for row in target["days"]}
        target["days"] = []
        for offset, day in enumerate(expected_dates):
            day_start = int((first_day + timedelta(days=offset)).timestamp())
            day_end = min(now, day_start + 86400)
            maintenance_seconds = sum(max(0, min(day_end, int(row["ends_at"] or now)) - max(day_start, int(row["starts_at"])))
                                      for row in maintenance_rows if row["service_key"] == target["key"])
            item = indexed.get(day, {"date": day, "uptime": None, "avg_latency": None, "checks": 0})
            item["maintenance_minutes"] = maintenance_seconds // 60
            target["days"].append(item)
    available = max((sum(1 for day in item["days"] if day["checks"] > 0) for item in by_service.values()), default=0)
    return JSONResponse({
        "generated_at": int(time.time()), "requested_days": days,
        "available_days": available, "services": list(by_service.values()),
    }, headers={"Cache-Control": "public, max-age=60"})


@app.get("/api/incidents")
def incidents_api(limit: int = 30):
    limit = max(1, min(int(limit), 100))
    with status_db() as con:
        incidents = [dict(row) for row in con.execute(
            "SELECT id,service_key,started_at,resolved_at,title,detail FROM incidents ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()]
    return JSONResponse({"generated_at": int(time.time()), "incidents": incidents}, headers={"Cache-Control": "public, max-age=60"})


@app.get("/api/incidents/{incident_id}")
def incident_api(incident_id: int):
    with status_db() as con:
        incident = con.execute(
            "SELECT id,service_key,started_at,resolved_at,title,detail FROM incidents WHERE id=?",
            (incident_id,),
        ).fetchone()
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return JSONResponse(dict(incident), headers={"Cache-Control": "public, max-age=60"})


@app.post("/api/csp-report", status_code=204)
async def csp_report(request: Request):
    """Collect privacy-minimized CSP reports during report-only rollout."""
    if int(request.headers.get("content-length", "0") or 0) > 65536:
        raise HTTPException(status_code=413, detail="report too large")
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(status_code=413, detail="report too large")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid report")
    items = payload if isinstance(payload, list) else [payload]
    if not items or len(items) > 50:
        raise HTTPException(status_code=400, detail="invalid report batch")
    now = int(time.time())
    with status_db() as con:
        con.execute("DELETE FROM csp_reports WHERE reported_at < ?", (now - 14 * 86400,))
        for item in items:
            if not isinstance(item, dict):
                continue
            report = item.get("csp-report", item.get("body", item))
            if not isinstance(report, dict):
                continue

            def clean(*names, limit=1024):
                for name in names:
                    if name in report:
                        return str(report.get(name, ""))[:limit]
                return ""

            con.execute("""INSERT INTO csp_reports
              (reported_at,document_uri,violated_directive,blocked_uri,source_file,line_number,column_number)
              VALUES(?,?,?,?,?,?,?)""", (
                now, clean("document-uri", "documentURL"),
                clean("violated-directive", "effectiveDirective", limit=256),
                clean("blocked-uri", "blockedURL"), clean("source-file", "sourceFile"),
                int(report.get("line-number", report.get("lineNumber", 0)) or 0),
                int(report.get("column-number", report.get("columnNumber", 0)) or 0),
            ))
        con.execute("""DELETE FROM csp_reports WHERE id NOT IN
          (SELECT id FROM csp_reports ORDER BY id DESC LIMIT 10000)""")
    return Response(status_code=204)


@app.get("/feed.xml")
def feed():
    _, incidents = status_summary()
    items = "".join(f"<item><title>{x['title']}</title><guid>{STATUS_URL}/#incident-{x['id']}</guid><pubDate>{time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(x['started_at']))}</pubDate><description>{x['detail'] or 'Status transition detected'}</description></item>" for x in incidents)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>MatchAll Status</title><link>{STATUS_URL}</link><description>MatchAll service incidents</description>{items}</channel></rss>'
    return Response(xml, media_type="application/rss+xml", headers={"Cache-Control": "public, max-age=60"})


@app.get("/docs", response_class=HTMLResponse)
def docs_home(request: Request, q: str = "", category: str = ""):
    articles = load_docs()
    if q:
        query = q.casefold()
        articles = [a for a in articles if query in f"{a['title']} {a['summary']} {a['plain']}".casefold()]
    if category:
        articles = [a for a in articles if a["category"] == category]
    categories = sorted({a["category"] for a in load_docs()})
    return render("docs_index.html", request, articles=articles, categories=categories, q=q, category=category)


@app.get("/docs/{slug}", response_class=HTMLResponse)
def docs_article(slug: str, request: Request):
    article = next((a for a in load_docs() if a["slug"] == slug), None)
    if not article:
        raise HTTPException(404, "Document not found")
    article["html"] = markdown.markdown(article["body"], extensions=["fenced_code", "tables", "toc"])
    return render("docs_article.html", request, article=article)


@app.get("/api/docs/search")
def docs_search(q: str = ""):
    query = q.strip().casefold()
    if len(query) < 2:
        return {"results": []}
    rows = [a for a in load_docs() if query in f"{a['title']} {a['summary']} {a['plain']}".casefold()]
    return {"results": [{k: a[k] for k in ["slug", "title", "summary", "category", "version"]} for a in rows[:20]]}


@app.post("/docs/{slug}/feedback")
async def docs_feedback(slug: str, request: Request, helpful: int = Form(...)):
    if not any(a["slug"] == slug for a in load_docs()):
        raise HTTPException(404, "Document not found")
    user = get_user(request)
    user_key = user["sub"] if user else hashlib.sha256((request.client.host + read_secret(SESSION_SECRET_FILE)).encode()).hexdigest()
    with notify_db() as con:
        con.execute("INSERT OR REPLACE INTO docs_feedback(article_slug,user_key,helpful,created_at) VALUES(?,?,?,?)",
                    (slug, user_key, 1 if helpful else 0, int(time.time())))
    return RedirectResponse(f"/docs/{slug}?feedback=thanks", status_code=303)


def notification_rows(user):
    with notify_db() as con:
        rows = con.execute("""SELECT n.*,CASE WHEN r.read_at IS NULL THEN 0 ELSE 1 END AS is_read
          FROM notifications n LEFT JOIN notification_reads r ON r.notification_id=n.id AND r.user_sub=?
          WHERE n.audience IN ('users','public') AND (n.expires_at IS NULL OR n.expires_at>?)
          ORDER BY n.created_at DESC LIMIT 100""", (user["sub"], int(time.time()))).fetchall()
    return [dict(x) for x in rows]


@app.get("/notifications", response_class=HTMLResponse)
def notification_center(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    rows = notification_rows(user)
    with notify_db() as con:
        pref = con.execute("SELECT * FROM notification_preferences WHERE user_sub=?", (user["sub"],)).fetchone()
        deliveries = [dict(x) for x in con.execute("""SELECT channel,status,COUNT(*) count FROM delivery_jobs
          GROUP BY channel,status ORDER BY channel,status""").fetchall()] if is_admin(user) else []
    return render("notifications.html", request, user=user, notifications=rows,
                  unread=sum(1 for x in rows if not x["is_read"]), admin=is_admin(user),
                  pref=dict(pref) if pref else {}, deliveries=deliveries,
                  smtp_ready=bool(SMTP_HOST), telegram_ready=bool(read_secret(TELEGRAM_BOT_TOKEN_FILE) and read_secret(TELEGRAM_CHAT_ID_FILE)),
                  vapid_public_key=read_secret(VAPID_PUBLIC_KEY_FILE))


@app.post("/notifications/preferences")
def notification_preferences(request: Request, csrf_token: str = Form(...), email_enabled: bool = Form(False),
                             webpush_enabled: bool = Form(False)):
    user = require_user(request); check_csrf(user, csrf_token)
    email = (user.get("email") or "").strip()
    with notify_db() as con:
        con.execute("""INSERT INTO notification_preferences(user_sub,email,email_enabled,webpush_enabled,updated_at)
          VALUES(?,?,?,?,?) ON CONFLICT(user_sub) DO UPDATE SET email=excluded.email,
          email_enabled=excluded.email_enabled,webpush_enabled=excluded.webpush_enabled,updated_at=excluded.updated_at""",
          (user["sub"], email, int(bool(email_enabled and email and SMTP_HOST)), int(bool(webpush_enabled and read_secret(VAPID_PUBLIC_KEY_FILE))), int(time.time())))
    return RedirectResponse("/notifications", status_code=303)


@app.post("/api/notifications/push-subscriptions")
async def push_subscription(request: Request):
    user = require_user(request); check_csrf(user, request.headers.get("x-csrf-token", ""))
    payload = await request.json(); endpoint = str(payload.get("endpoint", ""))[:2000]
    keys = payload.get("keys") or {}; p256dh = str(keys.get("p256dh", ""))[:500]; auth = str(keys.get("auth", ""))[:500]
    if not endpoint.startswith("https://") or not p256dh or not auth:
        raise HTTPException(400, "Invalid push subscription")
    now = int(time.time())
    with notify_db() as con:
        con.execute("""INSERT INTO push_subscriptions(user_sub,endpoint,p256dh,auth,active,created_at,updated_at)
          VALUES(?,?,?,?,1,?,?) ON CONFLICT(endpoint) DO UPDATE SET user_sub=excluded.user_sub,p256dh=excluded.p256dh,
          auth=excluded.auth,active=1,updated_at=excluded.updated_at""", (user["sub"], endpoint, p256dh, auth, now, now))
    return {"ok": True}


@app.api_route("/push-sw.js", methods=["GET", "HEAD"])
def push_service_worker():
    script = """self.addEventListener('push',e=>{const d=e.data?e.data.json():{};e.waitUntil(self.registration.showNotification(d.title||'MatchAll',{body:d.body||'',icon:'/favicon.ico',data:{url:d.url||'/notifications'}}))});self.addEventListener('notificationclick',e=>{e.notification.close();e.waitUntil(clients.openWindow(e.notification.data.url))});"""
    return Response(script, media_type="application/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.post("/notifications/{notification_id}/read")
def notification_read(notification_id: int, request: Request, csrf_token: str = Form(...)):
    user = require_user(request)
    check_csrf(user, csrf_token)
    with notify_db() as con:
        con.execute("INSERT OR REPLACE INTO notification_reads(notification_id,user_sub,read_at) VALUES(?,?,?)",
                    (notification_id, user["sub"], int(time.time())))
    return RedirectResponse("/notifications", status_code=303)


@app.post("/notifications/admin")
def notification_create(request: Request, csrf_token: str = Form(...), title: str = Form(...), body: str = Form(...),
                        severity: str = Form("info"), action_url: str = Form(""), audience: str = Form("users"),
                        deliver_external: bool = Form(False)):
    user = require_user(request)
    check_csrf(user, csrf_token)
    if not is_admin(user):
        raise HTTPException(403, "Admin required")
    if severity not in {"info", "success", "warning", "critical"} or audience not in {"users", "public"}:
        raise HTTPException(400, "Invalid notification")
    now = int(time.time())
    publish_notification(event_key=f"manual:{user['sub']}:{now}:{hashlib.sha256(title.encode()).hexdigest()[:10]}",
                         kind="announcement", severity=severity, title=title, body=body,
                         action_url=action_url, audience=audience, deliver_external=deliver_external)
    return RedirectResponse("/notifications", status_code=303)


@app.post("/internal/events")
async def internal_event(request: Request):
    raw = await request.body()
    expected = hmac.new(read_secret(EVENT_SECRET_FILE).encode(), raw, hashlib.sha256).hexdigest()
    supplied = request.headers.get("x-matchall-signature", "").removeprefix("sha256=")
    if not expected or not secrets.compare_digest(expected, supplied):
        raise HTTPException(403, "Invalid signature")
    event = json.loads(raw)
    publish_notification(event_key=event["id"], kind=event.get("type", "event"), severity=event.get("severity", "info"),
                         title=event["title"], body=event.get("body", ""), action_url=event.get("url", ""),
                         audience=event.get("audience", "users"))
    return {"accepted": True}


@app.get("/notifications/feed.xml")
def notification_feed():
    with notify_db() as con:
        rows = con.execute("SELECT * FROM notifications WHERE audience='public' ORDER BY created_at DESC LIMIT 30").fetchall()
    items = "".join(f"<item><title>{html_lib.escape(x['title'])}</title><guid>{CONSOLE_URL}/notifications#{x['id']}</guid><pubDate>{time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(x['created_at']))}</pubDate><description>{html_lib.escape(x['body'])}</description></item>" for x in rows)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>MatchAll Notifications</title><link>{CONSOLE_URL}/notifications</link><description>Public MatchAll announcements</description>{items}</channel></rss>'
    return Response(xml, media_type="application/rss+xml", headers={"Cache-Control": "public, max-age=60"})
