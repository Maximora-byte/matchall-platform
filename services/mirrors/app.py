import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import ipaddress
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode

import httpx
import boto3
import bleach
import markdown
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

os.umask(0o077)

BASE_URL = os.getenv("BASE_URL", "https://mirrors.maximoraverse.org").rstrip("/")
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "https://auth.maximoraverse.org/application/o/matchall-mirrors/").rstrip("/")
OIDC_ENDPOINT_BASE = os.getenv("OIDC_ENDPOINT_BASE", "https://auth.maximoraverse.org/application/o").rstrip("/")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "matchall-mirrors")
OIDC_CLIENT_SECRET_FILE = os.getenv("OIDC_CLIENT_SECRET_FILE", "/run/secrets/oidc_client_secret")
SESSION_SECRET_FILE = os.getenv("SESSION_SECRET_FILE", "/run/secrets/session_secret")
ADMIN_USERS = {x.strip() for x in os.getenv("ADMIN_USERS", "admin").split(",") if x.strip()}
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "mirror.db"
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024**3)))
STRIPE_SECRET_FILE = os.getenv("STRIPE_SECRET_FILE", "/run/secrets/stripe_secret")
STRIPE_WEBHOOK_SECRET_FILE = os.getenv("STRIPE_WEBHOOK_SECRET_FILE", "/run/secrets/stripe_webhook_secret")
HUB_EVENT_SECRET_FILE = os.getenv("HUB_EVENT_SECRET_FILE", "/run/secrets/hub_event_secret")
HUB_EVENT_URL = os.getenv("HUB_EVENT_URL", "http://hub:8000/internal/events")
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local").strip().lower()
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "").strip() or None
S3_REGION = os.getenv("S3_REGION", "auto").strip()
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
S3_ACCESS_KEY_FILE = os.getenv("S3_ACCESS_KEY_FILE", "/run/secrets/s3_access_key")
S3_SECRET_KEY_FILE = os.getenv("S3_SECRET_KEY_FILE", "/run/secrets/s3_secret_key")
S3_PRESIGN_SECONDS = max(60, min(int(os.getenv("S3_PRESIGN_SECONDS", "300")), 3600))
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "").strip()
TURNSTILE_SECRET_FILE = os.getenv("TURNSTILE_SECRET_FILE", "/run/secrets/turnstile_secret")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
DOWNLOAD_GRANT_SECONDS = max(30, min(int(os.getenv("DOWNLOAD_GRANT_SECONDS", "180")), 600))
MACHINE_DOWNLOAD_SECONDS = max(60, min(int(os.getenv("MACHINE_DOWNLOAD_SECONDS", "300")), 1800))
EDGE_DOWNLOAD_BASE = os.getenv("EDGE_DOWNLOAD_BASE", "").strip().rstrip("/")
EDGE_DOWNLOAD_SECRET_FILE = os.getenv("EDGE_DOWNLOAD_SECRET_FILE", "/run/secrets/edge_download_secret")
EDGE_CN_CIDRS_FILE = os.getenv("EDGE_CN_CIDRS_FILE", "/data/cn-cidrs.txt")
EDGE_ROLLOUT_PERCENT = max(0, min(int(os.getenv("EDGE_ROLLOUT_PERCENT", "0")), 100))
EDGE_TOKEN_SECONDS = max(60, min(int(os.getenv("EDGE_TOKEN_SECONDS", "600")), 3600))
EDGE_HEALTH_FILE = Path(os.getenv("EDGE_HEALTH_FILE", "/data/edge-health.ok"))
EDGE_HEALTH_MAX_AGE = max(30, min(int(os.getenv("EDGE_HEALTH_MAX_AGE", "180")), 900))
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
CHANNELS = {"stable", "beta", "alpha"}
CURRENCIES = {"HKD", "JPY", "USD"}

app = FastAPI(title="MatchAll Mirrors", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Environment(loader=FileSystemLoader("templates"), autoescape=select_autoescape(["html", "xml"]))

RELEASE_NOTE_TAGS = {
    "a", "blockquote", "br", "code", "details", "em", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "li", "ol", "p", "pre", "strong", "summary", "ul",
}
RELEASE_NOTE_ATTRIBUTES = {"a": ["href", "title", "rel"]}
DOWNLOAD_MEDIA_TYPES = {
    ".apk": "application/vnd.android.package-archive",
    ".appimage": "application/octet-stream",
    ".asc": "application/pgp-keys",
    ".deb": "application/vnd.debian.binary-package",
    ".dmg": "application/x-apple-diskimage",
    ".exe": "application/vnd.microsoft.portable-executable",
    ".msi": "application/x-msi",
    ".rpm": "application/x-rpm",
    ".sig": "application/pgp-signature",
    ".zip": "application/zip",
}


def normalize_orphan_summaries(value: str) -> str:
    def replace(match):
        lines = match.group(1).strip().splitlines()
        quoted = "\n".join("> " + line if line.strip() else ">" for line in lines)
        return f"\n> **版本摘要**\n>\n{quoted}\n"
    return re.sub(r"<summary>\s*(.*?)\s*</summary>", replace, str(value or ""), flags=re.I | re.S)


def render_release_markdown(value: str) -> Markup:
    raw = markdown.markdown(normalize_orphan_summaries(value), extensions=["extra", "sane_lists"])
    clean = bleach.clean(raw, tags=RELEASE_NOTE_TAGS, attributes=RELEASE_NOTE_ATTRIBUTES,
                         protocols={"http", "https"}, strip=True, strip_comments=True)
    clean = bleach.linkify(clean, callbacks=[bleach.callbacks.nofollow], skip_tags={"pre", "code"})
    return Markup(clean)


templates.filters["release_markdown"] = render_release_markdown


def download_media_type(filename: str) -> str:
    return DOWNLOAD_MEDIA_TYPES.get(Path(str(filename)).suffix.lower(), "application/octet-stream")


def read_secret(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def load_edge_networks():
    networks = []
    try:
        for raw in Path(EDGE_CN_CIDRS_FILE).read_text().splitlines():
            value = raw.strip()
            if value and not value.startswith("#"):
                networks.append(ipaddress.ip_network(value, strict=False))
    except OSError:
        return ()
    return tuple(networks)


EDGE_CN_NETWORKS = load_edge_networks()


def mirror_client_ip(request: Request) -> str:
    # Caddy overwrites this header and the application is reachable only on the
    # private Docker network/loopback. Never accept an arbitrary forwarded chain.
    value = request.headers.get("x-mirror-client-ip", "").strip()
    return value or (request.client.host if request.client else "")


def use_cn_edge(request: Request, artifact_id: int) -> bool:
    if not (EDGE_DOWNLOAD_BASE and EDGE_ROLLOUT_PERCENT and EDGE_CN_NETWORKS and read_secret(EDGE_DOWNLOAD_SECRET_FILE)):
        return False
    try:
        if EDGE_HEALTH_FILE.read_text().strip() != "ok" or time.time() - EDGE_HEALTH_FILE.stat().st_mtime > EDGE_HEALTH_MAX_AGE:
            return False
    except OSError:
        return False
    try:
        address = ipaddress.ip_address(mirror_client_ip(request))
    except ValueError:
        return False
    if not any(address in network for network in EDGE_CN_NETWORKS if network.version == address.version):
        return False
    bucket = int(hashlib.sha256(f"edge:{address}:{artifact_id}".encode()).hexdigest()[:8], 16) % 100
    return bucket < EDGE_ROLLOUT_PERCENT


def edge_download_url(artifact_id: int, local_path: str) -> str:
    expires = int(time.time()) + EDGE_TOKEN_SECONDS
    message = f"{artifact_id}:{local_path}:{expires}"
    signature = hmac.new(read_secret(EDGE_DOWNLOAD_SECRET_FILE).encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"{EDGE_DOWNLOAD_BASE}/artifact/{artifact_id}?expires={expires}&signature={signature}"


def turnstile_ready() -> bool:
    return bool(TURNSTILE_SITE_KEY and read_secret(TURNSTILE_SECRET_FILE))


def verify_turnstile(response_token: str, remote_ip: str = "") -> bool:
    secret = read_secret(TURNSTILE_SECRET_FILE)
    if not TURNSTILE_SITE_KEY or not secret or not response_token:
        return False
    payload = {"secret": secret, "response": response_token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        response = httpx.post(TURNSTILE_VERIFY_URL, data=payload, timeout=8.0)
        return response.status_code == 200 and response.json().get("success") is True
    except (httpx.HTTPError, ValueError):
        return False


def s3_client():
    access, secret = read_secret(S3_ACCESS_KEY_FILE), read_secret(S3_SECRET_KEY_FILE)
    if STORAGE_PROVIDER != "s3" or not S3_BUCKET or not access or not secret:
        return None
    return boto3.client("s3", endpoint_url=S3_ENDPOINT_URL, region_name=S3_REGION,
                        aws_access_key_id=access, aws_secret_access_key=secret)


def finalize_hosted_file(target: Path, project_slug: str, version: str, filename: str):
    client = s3_client()
    if not client:
        return "local", "", str(target.relative_to(FILES_DIR))
    key = f"releases/{project_slug}/{re.sub(r'[^A-Za-z0-9._-]', '_', version)}/{secrets.token_hex(6)}-{filename}"
    client.upload_file(str(target), S3_BUCKET, key, ExtraArgs={"ContentType": "application/octet-stream"})
    target.unlink(missing_ok=True)
    return "s3", key, ""


serializer = URLSafeTimedSerializer(read_secret(SESSION_SECRET_FILE) or secrets.token_urlsafe(48), salt="matchall-mirrors")


@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          slug TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          summary TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          homepage TEXT NOT NULL DEFAULT '',
          license TEXT NOT NULL DEFAULT '',
          icon TEXT NOT NULL DEFAULT '📦',
          public INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS releases (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          version TEXT NOT NULL,
          channel TEXT NOT NULL DEFAULT 'stable',
          notes TEXT NOT NULL DEFAULT '',
          published_at INTEGER NOT NULL,
          UNIQUE(project_id, version, channel)
        );
        CREATE TABLE IF NOT EXISTS artifacts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
          os TEXT NOT NULL DEFAULT 'any',
          arch TEXT NOT NULL DEFAULT 'any',
          filename TEXT NOT NULL,
          local_path TEXT NOT NULL DEFAULT '',
          external_url TEXT NOT NULL DEFAULT '',
          size INTEGER NOT NULL DEFAULT 0,
          sha256 TEXT NOT NULL DEFAULT '',
          downloads INTEGER NOT NULL DEFAULT 0,
          created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_release_project ON releases(project_id, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_artifact_release ON artifacts(release_id);
        CREATE TABLE IF NOT EXISTS users (
          sub TEXT PRIMARY KEY,
          username TEXT NOT NULL DEFAULT '',
          email TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          price_minor INTEGER NOT NULL,
          currency TEXT NOT NULL DEFAULT 'HKD',
          duration_days INTEGER NOT NULL DEFAULT 0,
          all_projects INTEGER NOT NULL DEFAULT 0,
          stripe_price_id TEXT NOT NULL DEFAULT '',
          active INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_projects (
          product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
          project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          PRIMARY KEY(product_id, project_id)
        );
        CREATE TABLE IF NOT EXISTS orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          order_no TEXT UNIQUE NOT NULL,
          user_sub TEXT NOT NULL,
          product_id INTEGER NOT NULL REFERENCES products(id),
          amount_minor INTEGER NOT NULL,
          currency TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          provider TEXT NOT NULL DEFAULT 'manual',
          provider_ref TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL,
          paid_at INTEGER,
          refunded_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS entitlements (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_sub TEXT NOT NULL,
          product_id INTEGER REFERENCES products(id),
          project_id INTEGER REFERENCES projects(id),
          source_type TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          starts_at INTEGER NOT NULL,
          ends_at INTEGER,
          active INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL,
          UNIQUE(user_sub, source_type, source_ref)
        );
        CREATE TABLE IF NOT EXISTS redemption_codes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code_hash TEXT UNIQUE NOT NULL,
          label TEXT NOT NULL DEFAULT '',
          product_id INTEGER NOT NULL REFERENCES products(id),
          max_uses INTEGER NOT NULL DEFAULT 1,
          uses INTEGER NOT NULL DEFAULT 0,
          expires_at INTEGER,
          active INTEGER NOT NULL DEFAULT 1,
          created_by TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS api_tokens (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          token_hash TEXT UNIQUE NOT NULL,
          user_sub TEXT NOT NULL,
          label TEXT NOT NULL DEFAULT '',
          last_used_at INTEGER,
          expires_at INTEGER,
          revoked INTEGER NOT NULL DEFAULT 0,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS webhook_events (
          provider TEXT NOT NULL,
          event_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          received_at INTEGER NOT NULL,
          PRIMARY KEY(provider, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_sub, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_entitlements_user ON entitlements(user_sub, active, ends_at);
        CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
        CREATE TABLE IF NOT EXISTS teams (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          slug TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          owner_sub TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS team_members (
          team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
          user_sub TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'viewer',
          created_at INTEGER NOT NULL,
          PRIMARY KEY(team_id,user_sub)
        );
        CREATE TABLE IF NOT EXISTS developer_tokens (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
          token_hash TEXT UNIQUE NOT NULL,
          label TEXT NOT NULL DEFAULT '',
          scopes TEXT NOT NULL DEFAULT 'release:write',
          created_by TEXT NOT NULL,
          last_used_at INTEGER,
          expires_at INTEGER,
          revoked INTEGER NOT NULL DEFAULT 0,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_webhooks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          url TEXT NOT NULL,
          secret TEXT NOT NULL,
          events TEXT NOT NULL DEFAULT 'release.published',
          active INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          webhook_id INTEGER REFERENCES project_webhooks(id) ON DELETE CASCADE,
          event_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          status TEXT NOT NULL,
          status_code INTEGER NOT NULL DEFAULT 0,
          error TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL,
          sent_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          actor_sub TEXT NOT NULL,
          team_id INTEGER,
          project_id INTEGER,
          action TEXT NOT NULL,
          detail TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS download_grants (
          token_hash TEXT PRIMARY KEY,
          artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
          expires_at INTEGER NOT NULL,
          consumed_at INTEGER,
          created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_download_grants_expiry ON download_grants(expires_at);
        """)
        columns = {row[1] for row in con.execute("PRAGMA table_info(projects)")}
        if "access_mode" not in columns:
            con.execute("ALTER TABLE projects ADD COLUMN access_mode TEXT NOT NULL DEFAULT 'free'")
        if "product_id" not in columns:
            con.execute("ALTER TABLE projects ADD COLUMN product_id INTEGER")
        if "team_id" not in columns:
            con.execute("ALTER TABLE projects ADD COLUMN team_id INTEGER")
        if "visibility" not in columns:
            con.execute("ALTER TABLE projects ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public'")
        release_columns = {row[1] for row in con.execute("PRAGMA table_info(releases)")}
        if "status" not in release_columns:
            con.execute("ALTER TABLE releases ADD COLUMN status TEXT NOT NULL DEFAULT 'published'")
        if "rollout_percentage" not in release_columns:
            con.execute("ALTER TABLE releases ADD COLUMN rollout_percentage INTEGER NOT NULL DEFAULT 100")
        if "approved_by" not in release_columns:
            con.execute("ALTER TABLE releases ADD COLUMN approved_by TEXT NOT NULL DEFAULT ''")
        if "approved_at" not in release_columns:
            con.execute("ALTER TABLE releases ADD COLUMN approved_at INTEGER")
        if "rolled_back_at" not in release_columns:
            con.execute("ALTER TABLE releases ADD COLUMN rolled_back_at INTEGER")
        artifact_columns = {row[1] for row in con.execute("PRAGMA table_info(artifacts)")}
        if "storage_provider" not in artifact_columns:
            con.execute("ALTER TABLE artifacts ADD COLUMN storage_provider TEXT NOT NULL DEFAULT 'local'")
        if "storage_key" not in artifact_columns:
            con.execute("ALTER TABLE artifacts ADD COLUMN storage_key TEXT NOT NULL DEFAULT ''")
        order_columns = {row[1] for row in con.execute("PRAGMA table_info(orders)")}
        if "stripe_session_id" not in order_columns:
            con.execute("ALTER TABLE orders ADD COLUMN stripe_session_id TEXT NOT NULL DEFAULT ''")
        # Before this column, pending orders kept the Checkout Session in
        # provider_ref, which is replaced by the PaymentIntent after payment.
        con.execute("""UPDATE orders SET stripe_session_id=provider_ref
          WHERE provider='stripe' AND stripe_session_id='' AND substr(provider_ref,1,3)='cs_'""")
        count = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        if count == 0:
            now = int(time.time())
            con.execute("INSERT INTO projects(slug,name,summary,description,homepage,license,icon,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        ("matchall-mirrors", "MatchAll Mirrors", "面向开源软件的版本发布与高速分发平台。", "提供稳定版、测试版、多平台构建、文件校验与自动更新 API。", BASE_URL, "AGPL-3.0", "🪞", now, now))
        seeded = con.execute("SELECT COUNT(*) FROM releases").fetchone()[0]
        if seeded == 0:
            now = int(time.time())
            project_id = con.execute("SELECT id FROM projects WHERE slug='matchall-mirrors'").fetchone()[0]
            content = ("MatchAll Mirrors API\n\n"
                       "Project catalog: /api/v1/projects\n"
                       "Latest release: /api/v1/projects/{slug}/latest?channel=stable&system=any&arch=any\n"
                       "Every hosted file includes a SHA-256 response header.\n").encode()
            seed_dir = FILES_DIR / "matchall-mirrors" / "1.0.0"
            seed_dir.mkdir(parents=True, exist_ok=True)
            seed_file = seed_dir / "matchall-mirrors-api.txt"
            seed_file.write_bytes(content)
            checksum = hashlib.sha256(content).hexdigest()
            cur = con.execute("INSERT INTO releases(project_id,version,channel,notes,published_at) VALUES(?,?,?,?,?)",
                              (project_id, "1.0.0", "stable", "首个可用版本：项目目录、版本发布、下载统计与更新检查 API。", now))
            con.execute("INSERT INTO artifacts(release_id,os,arch,filename,local_path,size,sha256,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (cur.lastrowid, "any", "any", seed_file.name, str(seed_file.relative_to(FILES_DIR)), len(content), checksum, now))


init_db()


def render(name: str, request: Request, status_code: int = 200, **context):
    user = get_user(request)
    html = templates.get_template(name).render(request=request, user=user, is_admin=is_admin(user), base_url=BASE_URL, **context)
    if name == "developer.html":
        html = html.replace("</head>", '<link rel="stylesheet" href="/static/developer.css"></head>')
    return HTMLResponse(html, status_code=status_code)


def get_user(request: Request):
    value = request.cookies.get("mirror_session")
    if not value:
        return None
    try:
        return serializer.loads(value, max_age=86400 * 7)
    except BadSignature:
        return None


def is_admin(user) -> bool:
    if not user:
        return False
    groups = set(user.get("groups") or [])
    return user.get("preferred_username") in ADMIN_USERS or user.get("is_superuser") is True or "authentik Admins" in groups


def require_admin(request: Request):
    user = get_user(request)
    if not is_admin(user):
        raise HTTPException(403, "需要 MatchAll 管理员权限")
    return user


def require_user(request: Request):
    user = get_user(request)
    if not user or not user.get("sub"):
        raise HTTPException(401, "请先使用 MatchAll 账户登录")
    return user


def upsert_user(con, user):
    now = int(time.time())
    con.execute("""INSERT INTO users(sub,username,email,created_at,updated_at) VALUES(?,?,?,?,?)
      ON CONFLICT(sub) DO UPDATE SET username=excluded.username,email=excluded.email,updated_at=excluded.updated_at""",
      (user.get("sub", ""), user.get("preferred_username", ""), user.get("email", ""), now, now))


def api_identity(request: Request, con):
    user = get_user(request)
    if user and user.get("sub"):
        return user
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer mat_"):
        return None
    raw = auth.split(None, 1)[1]
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    now = int(time.time())
    row = con.execute("""SELECT t.user_sub,u.username,u.email FROM api_tokens t
      LEFT JOIN users u ON u.sub=t.user_sub
      WHERE t.token_hash=? AND t.revoked=0 AND (t.expires_at IS NULL OR t.expires_at>?)""",
      (token_hash, now)).fetchone()
    if not row:
        return None
    con.execute("UPDATE api_tokens SET last_used_at=? WHERE token_hash=?", (now, token_hash))
    return {"sub": row["user_sub"], "preferred_username": row["username"], "email": row["email"]}


def developer_identity(request: Request, con):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer mdp_"):
        return None
    raw = auth.split(None, 1)[1]
    now = int(time.time())
    row = con.execute("""SELECT * FROM developer_tokens WHERE token_hash=? AND revoked=0
      AND (expires_at IS NULL OR expires_at>?)""", (hashlib.sha256(raw.encode()).hexdigest(), now)).fetchone()
    if row:
        con.execute("UPDATE developer_tokens SET last_used_at=? WHERE id=?", (now, row["id"]))
    return dict(row) if row else None


def team_role(con, team_id, user):
    if is_admin(user):
        return "owner"
    if not user or not team_id:
        return ""
    row = con.execute("SELECT role FROM team_members WHERE team_id=? AND user_sub=?", (team_id, user.get("sub"))).fetchone()
    return row["role"] if row else ""


def project_visible(con, project, user):
    return project["visibility"] == "public" or bool(team_role(con, project["team_id"], user))


def project_allowed(con, project, user) -> bool:
    if not project_visible(con, project, user):
        return False
    if project["visibility"] == "private":
        return True
    if project["access_mode"] == "free":
        return True
    if not user or not user.get("sub"):
        return False
    now = int(time.time())
    found = con.execute("""SELECT 1 FROM entitlements e
      LEFT JOIN products p ON p.id=e.product_id
      LEFT JOIN product_projects pp ON pp.product_id=e.product_id
      WHERE e.user_sub=? AND e.active=1 AND e.starts_at<=? AND (e.ends_at IS NULL OR e.ends_at>?)
        AND (e.project_id=? OR p.all_projects=1 OR pp.project_id=? OR e.product_id=?) LIMIT 1""",
      (user["sub"], now, now, project["id"], project["id"], project["product_id"] or -1)).fetchone()
    return bool(found)


def product_for_project(con, project):
    if not project["product_id"]:
        return None
    row = con.execute("SELECT * FROM products WHERE id=? AND active=1", (project["product_id"],)).fetchone()
    return dict(row) if row else None


def money(product):
    if not product:
        return ""
    amount = product["price_minor"] / 100
    return f"{product['currency']} {amount:,.2f}"


def grant_product(con, user_sub: str, product_id: int, source_type: str, source_ref: str):
    product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        raise HTTPException(404, "商品不存在")
    now = int(time.time())
    ends_at = now + product["duration_days"] * 86400 if product["duration_days"] else None
    con.execute("""INSERT INTO entitlements(user_sub,product_id,source_type,source_ref,starts_at,ends_at,created_at)
      VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_sub,source_type,source_ref)
      DO UPDATE SET product_id=excluded.product_id,starts_at=excluded.starts_at,ends_at=excluded.ends_at,active=1""",
      (user_sub, product_id, source_type, source_ref, now, ends_at, now))


def mark_order_paid(con, order_no: str, provider_ref: str = ""):
    order = con.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order["status"] == "paid":
        return
    now = int(time.time())
    con.execute("UPDATE orders SET status='paid',paid_at=?,provider_ref=CASE WHEN ?='' THEN provider_ref ELSE ? END WHERE order_no=?",
                (now, provider_ref, provider_ref, order_no))
    grant_product(con, order["user_sub"], order["product_id"], "order", order_no)


def revoke_order(con, order_no: str):
    now = int(time.time())
    con.execute("UPDATE orders SET status='refunded',refunded_at=? WHERE order_no=?", (now, order_no))
    con.execute("UPDATE entitlements SET active=0 WHERE source_type='order' AND source_ref=?", (order_no,))


def stripe_object_id(value) -> str:
    # Stripe expandable references can be an ID or an expanded object.
    value = value.get("id") if isinstance(value, dict) else value
    return value if isinstance(value, str) else ""


def stripe_amount_matches(obj, order) -> bool:
    amount, currency = obj.get("amount_total"), obj.get("currency")
    return (type(amount) is int and amount == order["amount_minor"]
            and isinstance(currency, str) and currency.upper() == order["currency"].upper())


def apply_stripe_checkout(con, obj):
    metadata = obj.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise HTTPException(400, "Invalid checkout metadata")
    order_no = metadata.get("order_no") or obj.get("client_reference_id")
    if not isinstance(order_no, str) or not order_no:
        raise HTTPException(400, "Checkout order reference missing")
    order = con.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    if not order:
        raise HTTPException(404, "Order not found")
    if (order["provider"] != "stripe" or not stripe_amount_matches(obj, order)
            or obj.get("mode") != "payment"
            or metadata.get("user_sub") != order["user_sub"]
            or (obj.get("client_reference_id") and obj["client_reference_id"] != order_no)):
        raise HTTPException(400, "Checkout does not match the order")
    session_id, payment_intent = obj.get("id"), stripe_object_id(obj.get("payment_intent"))
    if not isinstance(session_id, str) or not session_id or not payment_intent:
        raise HTTPException(400, "Checkout payment binding missing")
    stored_session = order["stripe_session_id"]
    if not stored_session and order["provider_ref"].startswith("cs_"):
        stored_session = order["provider_ref"]
    if stored_session and stored_session != session_id:
        raise HTTPException(400, "Checkout session does not match the order")
    if order["status"] in {"paid", "refunded"}:
        if order["provider_ref"] != payment_intent:
            raise HTTPException(400, "Checkout payment does not match the order")
        # Legacy paid orders may have lost their original session ID. They can
        # acknowledge the same payment, but must never grant/renew access again.
        return
    if order["status"] != "pending" or not stored_session:
        raise HTTPException(409, "Checkout binding is not ready")
    if con.execute("SELECT 1 FROM orders WHERE provider='stripe' AND provider_ref=? AND order_no<>?",
                   (payment_intent, order_no)).fetchone():
        raise HTTPException(400, "Payment is already bound to another order")
    con.execute("UPDATE orders SET stripe_session_id=? WHERE order_no=?", (stored_session, order_no))
    mark_order_paid(con, order_no, payment_intent)


@app.middleware("http")
async def protect_admin_routes(request: Request, call_next):
    if request.url.path == "/admin" or request.url.path.startswith("/admin/"):
        if not is_admin(get_user(request)):
            return render("error.html", request, status_code=403, status=403, message="需要 MatchAll 管理员权限")
    return await call_next(request)


def csrf(request: Request, submitted: str):
    user = get_user(request)
    if not user or not secrets.compare_digest(user.get("csrf", ""), submitted or ""):
        raise HTTPException(403, "CSRF validation failed")


def valid_slug(value: str) -> str:
    value = value.strip().lower()
    if not SLUG_RE.fullmatch(value):
        raise HTTPException(400, "标识仅支持小写字母、数字、点、下划线和连字符")
    return value


def validate_webhook_url(value: str) -> str:
    from urllib.parse import urlparse
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Webhook 必须使用不含凭据的 HTTPS URL")
    try:
        addresses = {x[4][0] for x in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise HTTPException(400, "Webhook 域名无法解析") from exc
    if any(ipaddress.ip_address(x).is_private or ipaddress.ip_address(x).is_loopback or ipaddress.ip_address(x).is_link_local for x in addresses):
        raise HTTPException(400, "Webhook 不允许访问私有网络")
    return value


def audit(con, user_sub, action, *, team_id=None, project_id=None, detail=""):
    con.execute("INSERT INTO audit_log(actor_sub,team_id,project_id,action,detail,created_at) VALUES(?,?,?,?,?,?)",
                (user_sub, team_id, project_id, action, detail[:500], int(time.time())))


async def dispatch_release_event(project, version, channel):
    event_id = f"release:{project['slug']}:{channel}:{version}"
    event = {"id": event_id, "type": "release.published", "severity": "info",
             "title": f"{project['name']} {version} 已发布",
             "body": f"{channel} 通道已有新版本。", "url": f"{BASE_URL}/project/{project['slug']}",
             "audience": "users", "project": project["slug"], "version": version, "channel": channel,
             "created_at": int(time.time())}
    raw = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode()
    hub_secret = read_secret(HUB_EVENT_SECRET_FILE)
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
        if hub_secret:
            signature = hmac.new(hub_secret.encode(), raw, hashlib.sha256).hexdigest()
            try:
                await client.post(HUB_EVENT_URL, content=raw, headers={"content-type": "application/json", "x-matchall-signature": f"sha256={signature}"})
            except httpx.HTTPError:
                pass
        with db() as con:
            hooks = [dict(x) for x in con.execute("SELECT * FROM project_webhooks WHERE project_id=? AND active=1", (project["id"],)).fetchall()]
        for hook in hooks:
            signature = hmac.new(hook["secret"].encode(), raw, hashlib.sha256).hexdigest()
            status, code, error = "failed", 0, ""
            try:
                response = await client.post(hook["url"], content=raw, headers={"content-type": "application/json",
                  "x-matchall-event": "release.published", "x-matchall-event-id": event_id,
                  "x-matchall-signature": f"sha256={signature}"})
                code = response.status_code
                status = "delivered" if 200 <= code < 300 else "failed"
                error = "" if status == "delivered" else f"HTTP {code}"
            except httpx.HTTPError as exc:
                error = exc.__class__.__name__
            with db() as con:
                con.execute("""INSERT INTO webhook_deliveries(webhook_id,event_id,event_type,status,status_code,error,created_at,sent_at)
                  VALUES(?,?,?,?,?,?,?,?)""", (hook["id"], event_id, "release.published", status, code, error, int(time.time()), int(time.time())))


def project_view(con, slug, user=None):
    project = con.execute("SELECT * FROM projects WHERE slug=?", (slug,)).fetchone()
    if not project or not project_visible(con, project, user):
        raise HTTPException(404)
    releases = con.execute("SELECT * FROM releases WHERE project_id=? AND status='published' ORDER BY published_at DESC, id DESC", (project["id"],)).fetchall()
    result = dict(project)
    result["allowed"] = project_allowed(con, project, user)
    result["product"] = product_for_project(con, project)
    if result["product"]:
        result["product"]["price_display"] = money(result["product"])
    result["releases"] = []
    for rel in releases:
        item = dict(rel)
        item["artifacts"] = []
        for artifact in con.execute("SELECT id,release_id,os,arch,filename,size,sha256,downloads,created_at FROM artifacts WHERE release_id=? ORDER BY os,arch", (rel["id"],)).fetchall():
            asset = dict(artifact)
            asset["download_url"] = f"/download/{asset['id']}" if result["allowed"] else ""
            asset["international_download_url"] = f"/download/{asset['id']}?source=international" if result["allowed"] else ""
            item["artifacts"].append(asset)
        result["releases"].append(item)
    return result


@app.get("/healthz")
def health():
    with db() as con:
        con.execute("SELECT 1").fetchone()
    return {"status": "ok", "service": "matchall-mirrors"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str = ""):
    user = get_user(request)
    with db() as con:
        if q:
            rows = con.execute("SELECT * FROM projects WHERE public=1 AND visibility='public' AND (name LIKE ? OR summary LIKE ? OR slug LIKE ?) ORDER BY updated_at DESC", (f"%{q}%",) * 3).fetchall()
        else:
            rows = con.execute("SELECT * FROM projects WHERE public=1 AND visibility='public' ORDER BY updated_at DESC").fetchall()
        projects = []
        for row in rows:
            item = dict(row)
            latest = con.execute("SELECT version,published_at FROM releases WHERE project_id=? AND channel='stable' AND status='published' ORDER BY published_at DESC LIMIT 1", (row["id"],)).fetchone()
            item["latest"] = dict(latest) if latest else None
            item["downloads"] = con.execute("SELECT COALESCE(SUM(a.downloads),0) FROM artifacts a JOIN releases r ON r.id=a.release_id WHERE r.project_id=?", (row["id"],)).fetchone()[0]
            item["allowed"] = project_allowed(con, row, user)
            item["product"] = product_for_project(con, row)
            if item["product"]:
                item["product"]["price_display"] = money(item["product"])
            projects.append(item)
        stats = {
            "projects": con.execute("SELECT COUNT(*) FROM projects WHERE public=1 AND visibility='public'").fetchone()[0],
            "releases": con.execute("SELECT COUNT(*) FROM releases").fetchone()[0],
            "downloads": con.execute("SELECT COALESCE(SUM(downloads),0) FROM artifacts").fetchone()[0],
        }
    return render("index.html", request, projects=projects, stats=stats, q=q)


@app.get("/project/{slug}", response_class=HTMLResponse)
def project_page(slug: str, request: Request):
    with db() as con:
        project = project_view(con, slug, get_user(request))
    return render("project.html", request, project=project)


@app.get("/api/v1/projects")
def api_projects():
    with db() as con:
        rows = con.execute("SELECT slug,name,summary,homepage,license,updated_at FROM projects WHERE public=1 AND visibility='public' ORDER BY updated_at DESC").fetchall()
    return {"code": 0, "data": [dict(x) for x in rows]}


@app.get("/api/v1/projects/{slug}")
def api_project(slug: str, request: Request):
    with db() as con:
        return {"code": 0, "data": project_view(con, slug, api_identity(request, con))}


@app.get("/api/v1/projects/{slug}/latest")
def api_latest(slug: str, request: Request, channel: str = "stable", system: str = "any", os_name: str = "", arch: str = "any", current: str = "", client_id: str = ""):
    if channel not in CHANNELS:
        raise HTTPException(400, "invalid channel")
    os_name = (os_name or system).lower()
    with db() as con:
        user = api_identity(request, con)
        project = con.execute("SELECT * FROM projects WHERE slug=?", (slug,)).fetchone()
        if not project or not project_visible(con, project, user):
            raise HTTPException(404)
        if not project_allowed(con, project, user):
            product = product_for_project(con, project)
            return JSONResponse({"code": 403, "message": "upgrade_required", "data": {
                "project": slug, "login_url": f"{BASE_URL}/login", "purchase_url": f"{BASE_URL}/pricing",
                "product": product["name"] if product else ""}}, status_code=403)
        rows = con.execute("""SELECT r.*,a.id artifact_id,a.os,a.arch,a.filename,a.size,a.sha256
          FROM releases r JOIN artifacts a ON a.release_id=r.id
          WHERE r.project_id=? AND r.channel=? AND r.status='published' AND a.os IN (?, 'any') AND a.arch IN (?, 'any')
          ORDER BY r.published_at DESC, CASE WHEN a.os=? THEN 0 ELSE 1 END, CASE WHEN a.arch=? THEN 0 ELSE 1 END""",
          (project["id"], channel, os_name, arch, os_name, arch)).fetchall()
        row = None
        for candidate in rows:
            percentage = candidate["rollout_percentage"]
            bucket = int(hashlib.sha256(f"{slug}:{client_id}".encode()).hexdigest()[:8], 16) % 100 + 1 if client_id else 100
            if percentage >= bucket:
                row = candidate; break
        if not row:
            raise HTTPException(404, "no matching release")
        data = dict(row)
        data["project"] = slug
        data["current"] = current
        data["update_available"] = not current or current != row["version"]
        if user:
            machine_token = serializer.dumps({"purpose": "machine-download", "artifact_id": row["artifact_id"]})
            data["download_url"] = f"{BASE_URL}/api/v1/download/{row['artifact_id']}?token={machine_token}"
        else:
            data["download_url"] = f"{BASE_URL}/download/{row['artifact_id']}"
        return {"code": 0, "data": data}


def serve_artifact(artifact_id: int, request: Request, force_origin: bool = False):
    with db() as con:
        row = con.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            raise HTTPException(404)
        project = con.execute("""SELECT p.* FROM projects p JOIN releases r ON r.project_id=p.id
          WHERE r.id=? AND r.status='published'""", (row["release_id"],)).fetchone()
        if not project:
            raise HTTPException(404)
        if not project_allowed(con, project, api_identity(request, con)):
            if not get_user(request):
                suffix = "?source=international" if force_origin else ""
                return RedirectResponse(f"/login?next=/download/{artifact_id}{suffix}", status_code=302)
            raise HTTPException(403, "该文件需要购买或兑换访问权")
        if request.method == "GET":
            con.execute("UPDATE artifacts SET downloads=downloads+1 WHERE id=?", (artifact_id,))
        if row["external_url"]:
            return RedirectResponse(row["external_url"], status_code=302)
        if row["storage_provider"] == "s3" and row["storage_key"]:
            client = s3_client()
            if not client:
                raise HTTPException(503, "object storage unavailable")
            url = client.generate_presigned_url("get_object", Params={"Bucket": S3_BUCKET, "Key": row["storage_key"],
                "ResponseContentDisposition": f"attachment; filename={row['filename']}"}, ExpiresIn=S3_PRESIGN_SECONDS)
            return RedirectResponse(url, status_code=302, headers={"Cache-Control": "private, no-store"})
        if not force_origin and use_cn_edge(request, artifact_id):
            return RedirectResponse(edge_download_url(artifact_id, row["local_path"]), status_code=302,
                                    headers={"Cache-Control": "private, no-store", "X-Mirror-Source": "cn-edge"})
        path = FILES_DIR / row["local_path"]
        if not path.is_file() or FILES_DIR not in path.resolve().parents:
            raise HTTPException(404, "file missing")
        return FileResponse(path, filename=row["filename"], media_type=download_media_type(row["filename"]),
                            headers={"ETag": row["sha256"], "X-Checksum-SHA256": row["sha256"]})


@app.get("/download/{artifact_id}", response_class=HTMLResponse)
def download(artifact_id: int, request: Request, grant: str = "", source: str = ""):
    force_origin = source == "international"
    serve_now = False
    with db() as con:
        row = con.execute("SELECT a.id,p.access_mode FROM artifacts a JOIN releases r ON r.id=a.release_id JOIN projects p ON p.id=r.project_id WHERE a.id=? AND r.status='published'", (artifact_id,)).fetchone()
        if not row:
            raise HTTPException(404)
        if row["access_mode"] != "free":
            serve_now = True
        if grant:
            token_hash = hashlib.sha256(grant.encode()).hexdigest()
            now = int(time.time())
            saved = con.execute("SELECT * FROM download_grants WHERE token_hash=? AND artifact_id=?", (token_hash, artifact_id)).fetchone()
            if saved and saved["consumed_at"] is None and saved["expires_at"] >= now:
                con.execute("UPDATE download_grants SET consumed_at=? WHERE token_hash=? AND consumed_at IS NULL", (now, token_hash))
                if con.total_changes == 1:
                    serve_now = True
        if not serve_now and not turnstile_ready():
            raise HTTPException(503, "下载验证暂不可用，请稍后重试")
    if serve_now:
        return serve_artifact(artifact_id, request, force_origin=force_origin)
    return render("download_verify.html", request, artifact_id=artifact_id, source="international" if force_origin else "",
                  turnstile_site_key=TURNSTILE_SITE_KEY)


@app.post("/download/{artifact_id}/verify")
def download_verify(artifact_id: int, request: Request, cf_turnstile_response: str = Form("", alias="cf-turnstile-response"),
                    source: str = Form("")):
    force_origin = source == "international"
    remote_ip = request.client.host if request.client else ""
    if not verify_turnstile(cf_turnstile_response, remote_ip):
        return render("download_verify.html", request, status_code=400, artifact_id=artifact_id,
                      source="international" if force_origin else "",
                      turnstile_site_key=TURNSTILE_SITE_KEY, verify_error="验证未通过，请重试")
    raw = secrets.token_urlsafe(32)
    now = int(time.time())
    with db() as con:
        row = con.execute("SELECT a.id,p.access_mode FROM artifacts a JOIN releases r ON r.id=a.release_id JOIN projects p ON p.id=r.project_id WHERE a.id=? AND r.status='published'", (artifact_id,)).fetchone()
        if not row or row["access_mode"] != "free":
            raise HTTPException(404)
        con.execute("DELETE FROM download_grants WHERE expires_at<? OR consumed_at IS NOT NULL", (now - 3600,))
        con.execute("INSERT INTO download_grants(token_hash,artifact_id,expires_at,created_at) VALUES(?,?,?,?)",
                    (hashlib.sha256(raw.encode()).hexdigest(), artifact_id, now + DOWNLOAD_GRANT_SECONDS, now))
    source_query = "&source=international" if force_origin else ""
    return RedirectResponse(f"/download/{artifact_id}?grant={raw}{source_query}", status_code=303,
                            headers={"Cache-Control": "no-store"})


@app.api_route("/api/v1/download/{artifact_id}", methods=["GET", "HEAD"])
def machine_download(artifact_id: int, request: Request, token: str = "", source: str = ""):
    try:
        payload = serializer.loads(token, max_age=MACHINE_DOWNLOAD_SECONDS)
    except BadSignature:
        raise HTTPException(403, "invalid or expired download token")
    if payload.get("purpose") != "machine-download" or payload.get("artifact_id") != artifact_id:
        raise HTTPException(403, "invalid download token")
    return serve_artifact(artifact_id, request, force_origin=source == "international")


@app.get("/login")
def login(request: Request, next: str = "/account"):
    verifier = secrets.token_urlsafe(64)
    challenge = hashlib.sha256(verifier.encode()).digest()
    import base64
    challenge = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
    state = secrets.token_urlsafe(24)
    next_path = next if next.startswith("/") and not next.startswith("//") else "/account"
    payload = serializer.dumps({"state": state, "verifier": verifier, "next": next_path})
    params = {"client_id": OIDC_CLIENT_ID, "response_type": "code", "redirect_uri": f"{BASE_URL}/auth/callback", "scope": "openid profile email", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    response = RedirectResponse(f"{OIDC_ENDPOINT_BASE}/authorize/?{urlencode(params)}", status_code=302)
    response.set_cookie("mirror_oidc", payload, max_age=600, secure=True, httponly=True, samesite="lax")
    return response


@app.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    raw = request.cookies.get("mirror_oidc", "")
    try:
        saved = serializer.loads(raw, max_age=600)
    except BadSignature:
        raise HTTPException(400, "invalid login state")
    if not code or not secrets.compare_digest(state, saved["state"]):
        raise HTTPException(400, "invalid callback")
    secret = read_secret(OIDC_CLIENT_SECRET_FILE)
    async with httpx.AsyncClient(timeout=15) as client:
        token = await client.post(f"{OIDC_ENDPOINT_BASE}/token/", data={"grant_type": "authorization_code", "code": code, "redirect_uri": f"{BASE_URL}/auth/callback", "client_id": OIDC_CLIENT_ID, "client_secret": secret, "code_verifier": saved["verifier"]})
        if token.status_code != 200:
            raise HTTPException(502, "OIDC token exchange failed")
        access = token.json().get("access_token", "")
        userinfo = await client.get(f"{OIDC_ENDPOINT_BASE}/userinfo/", headers={"Authorization": f"Bearer {access}"})
        if userinfo.status_code != 200:
            raise HTTPException(502, "OIDC userinfo failed")
    claims = userinfo.json()
    session = {"sub": claims.get("sub"), "preferred_username": claims.get("preferred_username") or claims.get("nickname"), "name": claims.get("name"), "email": claims.get("email"), "groups": claims.get("groups", []), "is_superuser": claims.get("is_superuser", False), "csrf": secrets.token_urlsafe(24)}
    if not session["sub"]:
        raise HTTPException(502, "OIDC subject missing")
    with db() as con:
        upsert_user(con, session)
    destination = "/admin" if is_admin(session) and saved.get("next") == "/admin" else saved.get("next", "/account")
    response = RedirectResponse(destination, status_code=302)
    response.set_cookie("mirror_session", serializer.dumps(session), max_age=86400 * 7, secure=True, httponly=True, samesite="lax")
    response.delete_cookie("mirror_oidc")
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("mirror_session")
    return response


@app.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request):
    with db() as con:
        products = [dict(x) for x in con.execute("SELECT * FROM products WHERE active=1 ORDER BY price_minor,id").fetchall()]
        for product in products:
            product["price_display"] = money(product)
            product["projects"] = [dict(x) for x in con.execute("""SELECT p.id,p.slug,p.name FROM projects p
              JOIN product_projects pp ON pp.project_id=p.id WHERE pp.product_id=? ORDER BY p.name""", (product["id"],)).fetchall()]
    return render("pricing.html", request, products=products, stripe_enabled=bool(read_secret(STRIPE_SECRET_FILE)))


@app.get("/account", response_class=HTMLResponse)
def account(request: Request, message: str = ""):
    user = require_user(request)
    now = int(time.time())
    with db() as con:
        upsert_user(con, user)
        orders = [dict(x) for x in con.execute("""SELECT o.*,p.name product_name FROM orders o
          JOIN products p ON p.id=o.product_id WHERE o.user_sub=? ORDER BY o.created_at DESC LIMIT 50""", (user["sub"],)).fetchall()]
        entitlements = [dict(x) for x in con.execute("""SELECT e.*,p.name product_name FROM entitlements e
          LEFT JOIN products p ON p.id=e.product_id WHERE e.user_sub=? ORDER BY e.created_at DESC""", (user["sub"],)).fetchall()]
        tokens = [dict(x) for x in con.execute("SELECT id,label,last_used_at,expires_at,revoked,created_at FROM api_tokens WHERE user_sub=? ORDER BY created_at DESC", (user["sub"],)).fetchall()]
    return render("account.html", request, orders=orders, entitlements=entitlements, tokens=tokens, now=now, message=message)


@app.post("/account/redeem")
def redeem_code(request: Request, csrf_token: str = Form(...), code: str = Form(...)):
    user = require_user(request); csrf(request, csrf_token)
    normalized = re.sub(r"[^A-Z0-9]", "", code.upper())
    code_hash = hashlib.sha256(normalized.encode()).hexdigest()
    now = int(time.time())
    with db() as con:
        row = con.execute("""SELECT * FROM redemption_codes WHERE code_hash=? AND active=1
          AND uses<max_uses AND (expires_at IS NULL OR expires_at>?)""", (code_hash, now)).fetchone()
        if not row:
            return RedirectResponse("/account?message=invalid_code", status_code=303)
        source_ref = f"cdk:{row['id']}:{user['sub']}"
        existing = con.execute("SELECT 1 FROM entitlements WHERE user_sub=? AND source_type='cdk' AND source_ref=?", (user["sub"], source_ref)).fetchone()
        if existing:
            return RedirectResponse("/account?message=already_redeemed", status_code=303)
        grant_product(con, user["sub"], row["product_id"], "cdk", source_ref)
        con.execute("UPDATE redemption_codes SET uses=uses+1 WHERE id=?", (row["id"],))
    return RedirectResponse("/account?message=redeemed", status_code=303)


@app.post("/account/tokens")
def create_api_token(request: Request, csrf_token: str = Form(...), label: str = Form("Updater"), days: int = Form(365)):
    user = require_user(request); csrf(request, csrf_token)
    days = max(1, min(days, 3650))
    raw = "mat_" + secrets.token_urlsafe(32)
    now = int(time.time())
    with db() as con:
        con.execute("INSERT INTO api_tokens(token_hash,user_sub,label,expires_at,created_at) VALUES(?,?,?,?,?)",
                    (hashlib.sha256(raw.encode()).hexdigest(), user["sub"], label.strip()[:80], now + days * 86400, now))
    return render("token_created.html", request, token=raw)


@app.post("/account/tokens/{token_id}/revoke")
def revoke_api_token(token_id: int, request: Request, csrf_token: str = Form(...)):
    user = require_user(request); csrf(request, csrf_token)
    with db() as con:
        con.execute("UPDATE api_tokens SET revoked=1 WHERE id=? AND user_sub=?", (token_id, user["sub"]))
    return RedirectResponse("/account?message=token_revoked", status_code=303)


@app.post("/checkout/{product_id}")
async def checkout(product_id: int, request: Request, csrf_token: str = Form(...)):
    user = require_user(request); csrf(request, csrf_token)
    with db() as con:
        upsert_user(con, user)
        product = con.execute("SELECT * FROM products WHERE id=? AND active=1", (product_id,)).fetchone()
        if not product:
            raise HTTPException(404, "商品不存在")
        order_no = f"MM{time.strftime('%Y%m%d%H%M%S', time.gmtime())}{secrets.token_hex(4).upper()}"
        provider = "stripe" if read_secret(STRIPE_SECRET_FILE) and product["stripe_price_id"] else "manual"
        con.execute("""INSERT INTO orders(order_no,user_sub,product_id,amount_minor,currency,status,provider,created_at)
          VALUES(?,?,?,?,?,'pending',?,?)""", (order_no, user["sub"], product_id, product["price_minor"], product["currency"], provider, int(time.time())))
    if provider == "manual":
        return RedirectResponse("/account?message=order_pending", status_code=303)
    stripe_secret = read_secret(STRIPE_SECRET_FILE)
    data = {
        "mode": "payment", "success_url": f"{BASE_URL}/account?message=payment_processing",
        "cancel_url": f"{BASE_URL}/pricing", "client_reference_id": order_no,
        "line_items[0][price]": product["stripe_price_id"], "line_items[0][quantity]": "1",
        "metadata[order_no]": order_no, "metadata[user_sub]": user["sub"],
    }
    async with httpx.AsyncClient(timeout=20) as client:
        result = await client.post("https://api.stripe.com/v1/checkout/sessions", data=data,
                                   headers={"Authorization": f"Bearer {stripe_secret}"})
    if result.status_code != 200:
        with db() as con:
            con.execute("UPDATE orders SET status='failed' WHERE order_no=?", (order_no,))
        raise HTTPException(502, "支付网关创建结账会话失败")
    payload = result.json()
    if (not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not payload["id"]
            or not stripe_amount_matches(payload, {"amount_minor": product["price_minor"], "currency": product["currency"]})):
        with db() as con:
            con.execute("UPDATE orders SET status='failed' WHERE order_no=?", (order_no,))
        raise HTTPException(502, "支付会话金额或币种与订单不一致，请联系管理员")
    with db() as con:
        con.execute("UPDATE orders SET provider_ref=?,stripe_session_id=? WHERE order_no=?",
                    (payload["id"], payload["id"], order_no))
    return RedirectResponse(payload["url"], status_code=303)


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    webhook_secret = read_secret(STRIPE_WEBHOOK_SECRET_FILE)
    if not webhook_secret:
        raise HTTPException(503, "Stripe webhook is not configured")
    body = await request.body()
    signature = request.headers.get("stripe-signature", "")
    fields = {}
    for part in signature.split(","):
        if "=" in part:
            key, value = part.split("=", 1); fields.setdefault(key, []).append(value)
    try:
        timestamp = int(fields.get("t", ["0"])[0])
    except ValueError:
        raise HTTPException(400, "invalid webhook timestamp")
    expected = hmac.new(webhook_secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    if abs(int(time.time()) - timestamp) > 300 or not any(hmac.compare_digest(expected, value) for value in fields.get("v1", [])):
        raise HTTPException(400, "invalid webhook signature")
    try:
        event = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid webhook event")
    if not isinstance(event, dict):
        raise HTTPException(400, "Invalid webhook event")
    event_id = event.get("id", "")
    event_type = event.get("type", "")
    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(event_id, str) or not event_id or not isinstance(event_type, str) or not event_type or not isinstance(obj, dict):
        raise HTTPException(400, "Invalid webhook event")
    with db() as con:
        try:
            con.execute("INSERT INTO webhook_events(provider,event_id,event_type,received_at) VALUES('stripe',?,?,?)",
                        (event_id, event_type, int(time.time())))
        except sqlite3.IntegrityError:
            return {"received": True, "duplicate": True}
        if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"} and obj.get("payment_status") == "paid":
            apply_stripe_checkout(con, obj)
        elif event_type == "charge.refunded":
            payment_intent = stripe_object_id(obj.get("payment_intent"))
            if not payment_intent:
                raise HTTPException(400, "Refund payment binding missing")
            orders = con.execute("SELECT order_no FROM orders WHERE provider='stripe' AND provider_ref=?", (payment_intent,)).fetchall()
            if len(orders) != 1:
                # Refunds can arrive before checkout completion; roll back the
                # receipt so Stripe can retry after the payment is bound.
                raise HTTPException(409, "Refund payment is not bound to an order")
            revoke_order(con, orders[0]["order_no"])
    return {"received": True}


@app.get("/developer", response_class=HTMLResponse)
def developer_dashboard(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login?next=/developer", status_code=302)
    with db() as con:
        upsert_user(con, user)
        teams = [dict(x) for x in con.execute("""SELECT t.*,m.role FROM teams t JOIN team_members m ON m.team_id=t.id
          WHERE m.user_sub=? ORDER BY t.name""", (user["sub"],)).fetchall()]
        team_ids = [x["id"] for x in teams]
        projects, tokens, hooks, audit_rows, members, releases = [], [], [], [], [], []
        if team_ids:
            marks = ",".join("?" for _ in team_ids)
            projects = [dict(x) for x in con.execute(f"SELECT * FROM projects WHERE team_id IN ({marks}) ORDER BY updated_at DESC", team_ids).fetchall()]
            tokens = [dict(x) for x in con.execute(f"SELECT id,team_id,label,scopes,last_used_at,expires_at,revoked,created_at FROM developer_tokens WHERE team_id IN ({marks}) ORDER BY id DESC", team_ids).fetchall()]
            hooks = [dict(x) for x in con.execute(f"""SELECT w.*,p.name project_name FROM project_webhooks w JOIN projects p ON p.id=w.project_id
              WHERE p.team_id IN ({marks}) ORDER BY w.id DESC""", team_ids).fetchall()]
            audit_rows = [dict(x) for x in con.execute(f"SELECT * FROM audit_log WHERE team_id IN ({marks}) ORDER BY id DESC LIMIT 50", team_ids).fetchall()]
            members = [dict(x) for x in con.execute(f"""SELECT m.*,u.username,u.email,t.name team_name FROM team_members m
              JOIN teams t ON t.id=m.team_id LEFT JOIN users u ON u.sub=m.user_sub WHERE m.team_id IN ({marks}) ORDER BY t.name,m.role""", team_ids).fetchall()]
            releases = [dict(x) for x in con.execute(f"""SELECT r.*,p.name project_name,p.team_id FROM releases r JOIN projects p ON p.id=r.project_id
              WHERE p.team_id IN ({marks}) ORDER BY r.id DESC LIMIT 100""", team_ids).fetchall()]
    return render("developer.html", request, teams=teams, projects=projects, tokens=tokens, hooks=hooks,
                  audit_rows=audit_rows, members=members, releases=releases, storage_provider=STORAGE_PROVIDER,
                  storage_ready=bool(s3_client()) if STORAGE_PROVIDER == "s3" else True)


@app.post("/developer/teams")
def developer_create_team(request: Request, csrf_token: str = Form(...), slug: str = Form(...), name: str = Form(...)):
    user = require_user(request); csrf(request, csrf_token); slug = valid_slug(slug); now = int(time.time())
    try:
        with db() as con:
            upsert_user(con, user)
            cur = con.execute("INSERT INTO teams(slug,name,owner_sub,created_at) VALUES(?,?,?,?)", (slug, name.strip()[:120], user["sub"], now))
            con.execute("INSERT INTO team_members(team_id,user_sub,role,created_at) VALUES(?,?,'owner',?)", (cur.lastrowid, user["sub"], now))
            audit(con, user["sub"], "team.created", team_id=cur.lastrowid, detail=slug)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "团队标识已存在")
    return RedirectResponse("/developer", status_code=303)


@app.post("/developer/teams/{team_id}/members")
def developer_add_member(team_id: int, request: Request, csrf_token: str = Form(...), identity: str = Form(...), role: str = Form("viewer")):
    user = require_user(request); csrf(request, csrf_token)
    if role not in {"owner", "editor", "viewer"}:
        raise HTTPException(400, "invalid role")
    with db() as con:
        if team_role(con, team_id, user) != "owner":
            raise HTTPException(403, "Owner required")
        member = con.execute("SELECT sub FROM users WHERE username=? OR lower(email)=lower(?)", (identity.strip(), identity.strip())).fetchone()
        if not member:
            raise HTTPException(404, "该用户需先登录 Mirrors")
        con.execute("INSERT OR REPLACE INTO team_members(team_id,user_sub,role,created_at) VALUES(?,?,?,?)", (team_id, member["sub"], role, int(time.time())))
        audit(con, user["sub"], "member.updated", team_id=team_id, detail=f"{member['sub']}:{role}")
    return RedirectResponse("/developer", status_code=303)


@app.post("/developer/projects")
def developer_create_project(request: Request, csrf_token: str = Form(...), team_id: int = Form(...), slug: str = Form(...),
                             name: str = Form(...), summary: str = Form(...), visibility: str = Form("public"),
                             description: str = Form(""), homepage: str = Form(""), license_name: str = Form(""), icon: str = Form("📦")):
    user = require_user(request); csrf(request, csrf_token); slug = valid_slug(slug)
    if visibility not in {"public", "private"}:
        raise HTTPException(400, "invalid visibility")
    with db() as con:
        if team_role(con, team_id, user) not in {"owner", "editor"}:
            raise HTTPException(403, "Editor required")
        now = int(time.time())
        try:
            cur = con.execute("""INSERT INTO projects(slug,name,summary,description,homepage,license,icon,public,team_id,visibility,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,1,?,?,?,?)""", (slug,name.strip(),summary.strip(),description.strip(),homepage.strip(),license_name.strip(),icon.strip()[:8] or "📦",team_id,visibility,now,now))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "项目标识已存在")
        audit(con, user["sub"], "project.created", team_id=team_id, project_id=cur.lastrowid, detail=visibility)
    return RedirectResponse("/developer", status_code=303)


@app.post("/developer/tokens")
def developer_create_token(request: Request, csrf_token: str = Form(...), team_id: int = Form(...), label: str = Form("CI release"), days: int = Form(365)):
    user = require_user(request); csrf(request, csrf_token); days=max(1,min(days,3650))
    raw = "mdp_" + secrets.token_urlsafe(32); now=int(time.time())
    with db() as con:
        if team_role(con, team_id, user) != "owner":
            raise HTTPException(403, "Owner required")
        con.execute("INSERT INTO developer_tokens(team_id,token_hash,label,scopes,created_by,expires_at,created_at) VALUES(?,?,?,?,?,?,?)",
                    (team_id,hashlib.sha256(raw.encode()).hexdigest(),label.strip()[:80],"release:write",user["sub"],now+days*86400,now))
        audit(con,user["sub"],"token.created",team_id=team_id,detail=label)
    return render("token_created.html", request, token=raw)


@app.post("/developer/tokens/{token_id}/revoke")
def developer_revoke_token(token_id: int, request: Request, csrf_token: str = Form(...)):
    user=require_user(request); csrf(request,csrf_token)
    with db() as con:
        row=con.execute("SELECT team_id FROM developer_tokens WHERE id=?",(token_id,)).fetchone()
        if not row or team_role(con,row["team_id"],user)!="owner": raise HTTPException(403,"Owner required")
        con.execute("UPDATE developer_tokens SET revoked=1 WHERE id=?",(token_id,)); audit(con,user["sub"],"token.revoked",team_id=row["team_id"])
    return RedirectResponse("/developer",status_code=303)


@app.post("/developer/webhooks")
def developer_create_webhook(request: Request, csrf_token: str = Form(...), project_id: int = Form(...), url: str = Form(...)):
    user=require_user(request); csrf(request,csrf_token); url=validate_webhook_url(url); secret="mwh_"+secrets.token_urlsafe(28)
    with db() as con:
        project=con.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()
        if not project or team_role(con,project["team_id"],user) not in {"owner","editor"}: raise HTTPException(403,"Editor required")
        con.execute("INSERT INTO project_webhooks(project_id,url,secret,created_at) VALUES(?,?,?,?)",(project_id,url,secret,int(time.time())))
        audit(con,user["sub"],"webhook.created",team_id=project["team_id"],project_id=project_id,detail=url)
    return render("webhook_created.html",request,secret=secret,url=url)


@app.post("/developer/releases")
async def developer_release(request: Request, csrf_token: str = Form(...), project_slug: str = Form(...), version: str = Form(...),
                            channel: str = Form("stable"), os_name: str = Form("any"), arch: str = Form("any"),
                            notes: str = Form(""), external_url: str = Form(""), expected_sha256: str = Form(""),
                            rollout_percentage: int = Form(100), upload: UploadFile | None = File(None)):
    user=require_user(request); csrf(request,csrf_token)
    if channel not in CHANNELS or not version.strip(): raise HTTPException(400,"invalid release")
    now=int(time.time()); local_path=""; storage_provider="external"; storage_key=""; filename=""; size=0; sha256=expected_sha256.strip().lower(); rollout_percentage=max(1,min(rollout_percentage,100))
    with db() as con:
        project=con.execute("SELECT * FROM projects WHERE slug=?",(valid_slug(project_slug),)).fetchone()
        if not project or team_role(con,project["team_id"],user) not in {"owner","editor"}: raise HTTPException(403,"Editor required")
    if upload and upload.filename:
        filename=Path(upload.filename).name; target_dir=FILES_DIR/project["slug"]/re.sub(r"[^A-Za-z0-9._-]","_",version); target_dir.mkdir(parents=True,exist_ok=True); target=target_dir/filename; digest=hashlib.sha256()
        with target.open("wb") as out:
            while chunk:=await upload.read(1024*1024):
                size+=len(chunk)
                if size>MAX_UPLOAD: target.unlink(missing_ok=True); raise HTTPException(413,"file too large")
                digest.update(chunk); out.write(chunk)
        sha256=digest.hexdigest(); storage_provider,storage_key,local_path=finalize_hosted_file(target,project["slug"],version,filename); external_url=""
    elif external_url.startswith("https://"):
        if project["visibility"] == "private" or project["access_mode"] == "paid":
            raise HTTPException(400,"私有或付费项目必须上传托管文件，不能使用永久外链")
        filename=Path(external_url.split("?",1)[0]).name or f"{project_slug}-{version}"
    else: raise HTTPException(400,"upload or HTTPS external URL required")
    try:
        with db() as con:
            con.execute("""INSERT INTO releases(project_id,version,channel,notes,published_at,status,rollout_percentage) VALUES(?,?,?,?,?,'draft',?)
              ON CONFLICT(project_id,version,channel) DO UPDATE SET notes=excluded.notes,published_at=excluded.published_at,status='draft',rollout_percentage=excluded.rollout_percentage""",(project["id"],version.strip(),channel,notes.strip(),now,rollout_percentage))
            release=con.execute("SELECT id FROM releases WHERE project_id=? AND version=? AND channel=?",(project["id"],version.strip(),channel)).fetchone()
            con.execute("INSERT INTO artifacts(release_id,os,arch,filename,local_path,external_url,size,sha256,created_at,storage_provider,storage_key) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(release["id"],os_name.lower(),arch.lower(),filename,local_path,external_url,size,sha256,now,storage_provider,storage_key))
            con.execute("UPDATE projects SET updated_at=? WHERE id=?",(now,project["id"])); audit(con,user["sub"],"release.drafted",team_id=project["team_id"],project_id=project["id"],detail=f"{version}:{channel}:{rollout_percentage}")
    except Exception:
        if local_path:(FILES_DIR/local_path).unlink(missing_ok=True)
        raise
    return RedirectResponse("/developer",status_code=303)


@app.post("/api/v1/developer/releases")
async def developer_release_api(request: Request):
    payload=await request.json()
    with db() as con:
        token=developer_identity(request,con)
        if not token: raise HTTPException(401,"invalid developer token")
        project=con.execute("SELECT * FROM projects WHERE slug=? AND team_id=?",(valid_slug(payload.get("project","")),token["team_id"])).fetchone()
        if not project: raise HTTPException(404,"project not found")
        version=str(payload.get("version","")).strip(); channel=payload.get("channel","stable"); url=str(payload.get("url","")).strip()
        if project["visibility"] == "private" or project["access_mode"] == "paid": raise HTTPException(400,"private or paid projects require hosted upload")
        if not version or channel not in CHANNELS or not url.startswith("https://"): raise HTTPException(400,"version, channel and HTTPS url required")
        now=int(time.time()); filename=Path(url.split("?",1)[0]).name or f"{project['slug']}-{version}"
        rollout=max(1,min(int(payload.get("rollout_percentage",100)),100))
        con.execute("""INSERT INTO releases(project_id,version,channel,notes,published_at,status,rollout_percentage) VALUES(?,?,?,?,?,'draft',?)
          ON CONFLICT(project_id,version,channel) DO UPDATE SET notes=excluded.notes,published_at=excluded.published_at,status='draft',rollout_percentage=excluded.rollout_percentage""",(project["id"],version,channel,str(payload.get("notes",""))[:10000],now,rollout))
        release=con.execute("SELECT id FROM releases WHERE project_id=? AND version=? AND channel=?",(project["id"],version,channel)).fetchone()
        con.execute("INSERT INTO artifacts(release_id,os,arch,filename,external_url,size,sha256,created_at) VALUES(?,?,?,?,?,?,?,?)",(release["id"],str(payload.get("os","any")).lower(),str(payload.get("arch","any")).lower(),filename,url,int(payload.get("size",0)),str(payload.get("sha256",""))[:64].lower(),now))
        con.execute("UPDATE projects SET updated_at=? WHERE id=?",(now,project["id"])); audit(con,token["created_by"],"release.api.drafted",team_id=token["team_id"],project_id=project["id"],detail=f"{version}:{channel}:{rollout}")
    return {"code":0,"data":{"project":project["slug"],"version":version,"channel":channel,"status":"draft","rollout_percentage":rollout}}


@app.post("/api/v1/developer/releases/upload")
async def developer_release_upload(request: Request, project_slug: str = Form(...), version: str = Form(...),
                                   channel: str = Form("stable"), os_name: str = Form("any"), arch: str = Form("any"),
                                   notes: str = Form(""), rollout_percentage: int = Form(100), upload: UploadFile = File(...)):
    if channel not in CHANNELS or not version.strip() or not upload.filename:
        raise HTTPException(400, "invalid release")
    with db() as con:
        token=developer_identity(request,con)
        if not token: raise HTTPException(401,"invalid developer token")
        project=con.execute("SELECT * FROM projects WHERE slug=? AND team_id=?",(valid_slug(project_slug),token["team_id"])).fetchone()
        if not project: raise HTTPException(404,"project not found")
    filename=Path(upload.filename).name; target_dir=FILES_DIR/project["slug"]/re.sub(r"[^A-Za-z0-9._-]","_",version); target_dir.mkdir(parents=True,exist_ok=True)
    target=target_dir/(secrets.token_hex(6)+"-"+filename); digest=hashlib.sha256(); size=0
    with target.open("wb") as out:
        while chunk:=await upload.read(1024*1024):
            size+=len(chunk)
            if size>MAX_UPLOAD: target.unlink(missing_ok=True); raise HTTPException(413,"file too large")
            digest.update(chunk); out.write(chunk)
    provider,key,local_path=finalize_hosted_file(target,project["slug"],version,filename); now=int(time.time()); rollout=max(1,min(rollout_percentage,100))
    with db() as con:
        con.execute("""INSERT INTO releases(project_id,version,channel,notes,published_at,status,rollout_percentage) VALUES(?,?,?,?,?,'draft',?)
          ON CONFLICT(project_id,version,channel) DO UPDATE SET notes=excluded.notes,published_at=excluded.published_at,status='draft',rollout_percentage=excluded.rollout_percentage""",
          (project["id"],version.strip(),channel,notes[:10000],now,rollout))
        release=con.execute("SELECT id FROM releases WHERE project_id=? AND version=? AND channel=?",(project["id"],version.strip(),channel)).fetchone()
        con.execute("INSERT INTO artifacts(release_id,os,arch,filename,local_path,size,sha256,created_at,storage_provider,storage_key) VALUES(?,?,?,?,?,?,?,?,?,?)",
          (release["id"],os_name.lower(),arch.lower(),filename,local_path,size,digest.hexdigest(),now,provider,key))
        audit(con,token["created_by"],"release.upload.drafted",team_id=token["team_id"],project_id=project["id"],detail=f"{version}:{channel}:{rollout}")
    return {"code":0,"data":{"project":project["slug"],"version":version,"channel":channel,"status":"draft","sha256":digest.hexdigest(),"size":size,"storage":provider}}


@app.post("/developer/releases/{release_id}/approve")
async def developer_approve_release(release_id: int, request: Request, csrf_token: str = Form(...)):
    user=require_user(request); csrf(request,csrf_token); now=int(time.time())
    with db() as con:
        row=con.execute("SELECT r.*,p.slug,p.name,p.team_id FROM releases r JOIN projects p ON p.id=r.project_id WHERE r.id=?",(release_id,)).fetchone()
        if not row or team_role(con,row["team_id"],user)!="owner": raise HTTPException(403,"Owner required")
        if row["status"]!="draft": raise HTTPException(409,"release is not a draft")
        con.execute("UPDATE releases SET status='published',approved_by=?,approved_at=?,published_at=? WHERE id=?",(user["sub"],now,now,release_id))
        audit(con,user["sub"],"release.approved",team_id=row["team_id"],project_id=row["project_id"],detail=f"{row['version']}:{row['channel']}")
        project={"id":row["project_id"],"slug":row["slug"],"name":row["name"]}
    await dispatch_release_event(project,row["version"],row["channel"])
    return RedirectResponse("/developer",status_code=303)


@app.post("/developer/releases/{release_id}/rollback")
def developer_rollback_release(release_id: int, request: Request, csrf_token: str = Form(...)):
    user=require_user(request); csrf(request,csrf_token); now=int(time.time())
    with db() as con:
        row=con.execute("SELECT r.*,p.team_id FROM releases r JOIN projects p ON p.id=r.project_id WHERE r.id=?",(release_id,)).fetchone()
        if not row or team_role(con,row["team_id"],user)!="owner": raise HTTPException(403,"Owner required")
        if row["status"]!="published": raise HTTPException(409,"release is not published")
        con.execute("UPDATE releases SET status='rolled_back',rolled_back_at=? WHERE id=?",(now,release_id))
        audit(con,user["sub"],"release.rolled_back",team_id=row["team_id"],project_id=row["project_id"],detail=f"{row['version']}:{row['channel']}")
    return RedirectResponse("/developer",status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    require_admin(request)
    with db() as con:
        projects = [dict(x) for x in con.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()]
        products = [dict(x) for x in con.execute("SELECT * FROM products ORDER BY active DESC,id DESC").fetchall()]
        for product in products:
            product["price_display"] = money(product)
        orders = [dict(x) for x in con.execute("""SELECT o.*,p.name product_name,u.username FROM orders o
          JOIN products p ON p.id=o.product_id LEFT JOIN users u ON u.sub=o.user_sub ORDER BY o.created_at DESC LIMIT 100""").fetchall()]
        codes = [dict(x) for x in con.execute("""SELECT c.*,p.name product_name FROM redemption_codes c
          JOIN products p ON p.id=c.product_id ORDER BY c.created_at DESC LIMIT 100""").fetchall()]
    return render("admin.html", request, projects=projects, products=products, orders=orders, codes=codes)


@app.post("/admin/products")
def create_product(request: Request, csrf_token: str = Form(...), code: str = Form(...), name: str = Form(...),
                   description: str = Form(""), price_minor: int = Form(...), currency: str = Form("HKD"),
                   duration_days: int = Form(30), all_projects: bool = Form(False), stripe_price_id: str = Form("")):
    require_admin(request); csrf(request, csrf_token)
    code = valid_slug(code)
    currency = currency.upper()
    if currency not in CURRENCIES or price_minor < 0 or duration_days < 0:
        raise HTTPException(400, "商品价格、币种或有效期无效")
    now = int(time.time())
    try:
        with db() as con:
            con.execute("""INSERT INTO products(code,name,description,price_minor,currency,duration_days,all_projects,stripe_price_id,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?)""", (code, name.strip(), description.strip(), price_minor, currency, duration_days,
              int(all_projects), stripe_price_id.strip(), now, now))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "商品代码已存在")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/projects/{project_id}/access")
def set_project_access(project_id: int, request: Request, csrf_token: str = Form(...), access_mode: str = Form(...), product_id: int = Form(0)):
    require_admin(request); csrf(request, csrf_token)
    if access_mode not in {"free", "paid"}:
        raise HTTPException(400, "invalid access mode")
    with db() as con:
        if access_mode == "paid" and not con.execute("SELECT 1 FROM products WHERE id=? AND active=1", (product_id,)).fetchone():
            raise HTTPException(400, "付费项目必须选择有效商品")
        con.execute("UPDATE projects SET access_mode=?,product_id=?,updated_at=? WHERE id=?",
                    (access_mode, product_id if access_mode == "paid" else None, int(time.time()), project_id))
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/orders/{order_no}/approve")
def approve_order(order_no: str, request: Request, csrf_token: str = Form(...)):
    require_admin(request); csrf(request, csrf_token)
    with db() as con:
        mark_order_paid(con, order_no, "manual-approval")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/orders/{order_no}/refund")
def refund_order(order_no: str, request: Request, csrf_token: str = Form(...)):
    require_admin(request); csrf(request, csrf_token)
    with db() as con:
        revoke_order(con, order_no)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/codes")
def create_code(request: Request, csrf_token: str = Form(...), product_id: int = Form(...), label: str = Form(""),
                max_uses: int = Form(1), expires_days: int = Form(30)):
    user = require_admin(request); csrf(request, csrf_token)
    max_uses = max(1, min(max_uses, 10000)); expires_days = max(1, min(expires_days, 3650))
    raw = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
    normalized = raw.replace("-", "")
    now = int(time.time())
    with db() as con:
        if not con.execute("SELECT 1 FROM products WHERE id=?", (product_id,)).fetchone():
            raise HTTPException(404, "商品不存在")
        con.execute("""INSERT INTO redemption_codes(code_hash,label,product_id,max_uses,expires_at,created_by,created_at)
          VALUES(?,?,?,?,?,?,?)""", (hashlib.sha256(normalized.encode()).hexdigest(), label.strip()[:100], product_id,
          max_uses, now + expires_days * 86400, user.get("preferred_username", "admin"), now))
    return render("code_created.html", request, code=raw)


@app.post("/admin/projects")
def create_project(request: Request, csrf_token: str = Form(...), slug: str = Form(...), name: str = Form(...), summary: str = Form(...), description: str = Form(""), homepage: str = Form(""), license_name: str = Form(""), icon: str = Form("📦")):
    require_admin(request); csrf(request, csrf_token)
    slug = valid_slug(slug)
    now = int(time.time())
    try:
        with db() as con:
            con.execute("INSERT INTO projects(slug,name,summary,description,homepage,license,icon,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (slug, name.strip(), summary.strip(), description.strip(), homepage.strip(), license_name.strip(), icon.strip()[:8] or "📦", now, now))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "项目标识已存在")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/releases")
async def create_release(request: Request, csrf_token: str = Form(...), project_slug: str = Form(...), version: str = Form(...), channel: str = Form("stable"), os_name: str = Form("any"), arch: str = Form("any"), notes: str = Form(""), external_url: str = Form(""), expected_sha256: str = Form(""), upload: UploadFile | None = File(None)):
    require_admin(request); csrf(request, csrf_token)
    if channel not in CHANNELS: raise HTTPException(400, "invalid channel")
    if not version.strip(): raise HTTPException(400, "version required")
    now = int(time.time())
    local_path = ""; filename = ""; size = 0; sha256 = expected_sha256.strip().lower()
    if upload and upload.filename:
        filename = Path(upload.filename).name
        safe_dir = FILES_DIR / valid_slug(project_slug) / re.sub(r"[^A-Za-z0-9._-]", "_", version)
        safe_dir.mkdir(parents=True, exist_ok=True)
        target = safe_dir / filename
        digest = hashlib.sha256()
        with target.open("wb") as out:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    target.unlink(missing_ok=True); raise HTTPException(413, "file too large")
                digest.update(chunk); out.write(chunk)
        sha256 = digest.hexdigest(); local_path = str(target.relative_to(FILES_DIR)); external_url = ""
    elif external_url:
        if not external_url.startswith("https://"): raise HTTPException(400, "external URL must use https")
        filename = Path(external_url.split("?", 1)[0]).name or f"{project_slug}-{version}"
    else:
        raise HTTPException(400, "upload or external URL required")
    try:
        with db() as con:
            project = con.execute("SELECT id FROM projects WHERE slug=?", (valid_slug(project_slug),)).fetchone()
            if not project: raise HTTPException(404, "project not found")
            policy = con.execute("SELECT access_mode FROM projects WHERE id=?", (project["id"],)).fetchone()
            if external_url and policy["access_mode"] == "paid":
                raise HTTPException(400, "付费项目暂不允许永久外链；请上传本地文件或配置私有对象存储签名器")
            con.execute("INSERT INTO releases(project_id,version,channel,notes,published_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id,version,channel) DO UPDATE SET notes=excluded.notes,published_at=excluded.published_at", (project["id"], version.strip(), channel, notes.strip(), now))
            release = con.execute("SELECT id FROM releases WHERE project_id=? AND version=? AND channel=?", (project["id"], version.strip(), channel)).fetchone()
            con.execute("INSERT INTO artifacts(release_id,os,arch,filename,local_path,external_url,size,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (release["id"], os_name.strip().lower(), arch.strip().lower(), filename, local_path, external_url.strip(), size, sha256, now))
            con.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, project["id"]))
    except Exception:
        if local_path: (FILES_DIR / local_path).unlink(missing_ok=True)
        raise
    return RedirectResponse(f"/project/{project_slug}", status_code=303)


@app.exception_handler(HTTPException)
def http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"code": exc.status_code, "message": exc.detail}, status_code=exc.status_code)
    return render("error.html", request, status_code=exc.status_code, status=exc.status_code, message=exc.detail)
