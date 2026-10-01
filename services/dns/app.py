import asyncio
import contextlib
import management as mg
import moddns_adapter as moddns
import operations
import statistics_panel
import query_history as qh
import base64
import hashlib
import json
import os
import plistlib
import re
import secrets
import sqlite3
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlencode

import dns.flags
import dns.message
import httpx
import jwt
from cryptography.fernet import Fernet
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = os.getenv('BASE_URL', 'https://dns.maximoraverse.org').rstrip('/')
DNS_IPV4 = os.getenv('DNS_IPV4', '64.110.101.75')
DNS_IPV6 = os.getenv('DNS_IPV6', '2603:c023:16:c400:0:249e:4aa8:be5a')
ISSUER = 'https://auth.maximoraverse.org/application/o/matchall-dns/'
OIDC = 'https://auth.maximoraverse.org/application/o'
CLIENT_ID = 'matchall-dns'
DATA = Path(os.getenv('DATA_DIR', '/data'))
UPSTREAMS = ['https://dns-hk.maximoraverse.org/dns-query', 'https://dns-backup.maximoraverse.org/dns-query']
ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=ROOT / 'templates')

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def secret(name):
    return Path(os.environ[name + '_FILE']).read_text().strip()

def cipher():
    return Fernet(secret('TOKEN_KEY').encode())

@contextmanager
def db():
    conn = sqlite3.connect(DATA / 'dns.sqlite3', timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(sub TEXT PRIMARY KEY, name TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, sub TEXT NOT NULL, csrf TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS oauth(hash TEXT PRIMARY KEY, verifier TEXT NOT NULL, nonce TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, sub TEXT NOT NULL, label TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
          token_enc TEXT NOT NULL, created INTEGER NOT NULL, revoked INTEGER, requests INTEGER NOT NULL DEFAULT 0,
          errors INTEGER NOT NULL DEFAULT 0, last_seen INTEGER);
        CREATE INDEX IF NOT EXISTS devices_owner ON devices(sub);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_account_token ON devices(sub) WHERE revoked IS NULL;
        ''')

@asynccontextmanager
async def lifespan(app):
    init_db()
    mg.migrate(db)
    moddns.migrate(db)
    qh.initialize(db)
    app.state.stats_error=False
    app.state.last_flush=time.monotonic()
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(5, connect=2), follow_redirects=False,
                                     limits=httpx.Limits(max_connections=100, max_keepalive_connections=20))
    app.state.moddns_http = httpx.AsyncClient(verify=os.getenv('MODDNS_CA_FILE',True),timeout=5)
    app.state.slots = asyncio.Semaphore(100)
    task=asyncio.create_task(mg.monitor(app,db,UPSTREAMS))
    flush_task=asyncio.create_task(mg.flush_loop(app,db))
    query_cleanup_task=asyncio.create_task(qh.cleanup(db))
    try:
        yield
    finally:
        query_cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):await query_cleanup_task
        task.cancel()
        flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):await flush_task
        with contextlib.suppress(asyncio.CancelledError):await task
        mg.flush(db)
        qh.flush(db)
        await app.state.moddns_http.aclose()
        await app.state.http.aclose()

app = FastAPI(title='MatchAll DNS', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
buckets = OrderedDict()

def allow(key, rate, burst):
    now = time.monotonic()
    old, ts = buckets.pop(key, (float(burst), now))
    value = min(burst, old + (now-ts)*rate)
    passed = value >= 1
    buckets[key] = (value-1 if passed else value, now)
    while len(buckets)>10000:
        buckets.popitem(last=False)
    return passed

@app.middleware('http')
async def security(request, call_next):
    if request.url.path.startswith(('/login', '/auth/', '/dns-query')):
        ip = request.client.host if request.client else 'unknown'
        if not allow('ip:'+ip, 180, 360):
            return Response(status_code=429, headers={'Retry-After':'1'})
    response = await call_next(request)
    if request.url.path.startswith(('/admin','/api/admin')) and response.status_code>=400:
        actor=user(request)
        if actor:
            try:
                with db() as c:
                    if not c.execute('SELECT 1 FROM audit WHERE actor=? AND result=? AND timestamp>=?',(actor['sub'],'denied',int(time.time())//60*60)).fetchone():
                        mg.audit(c,actor['sub'],'','admin.rejected',{}, {'http_status':response.status_code},'denied')
            except sqlite3.Error:
                request.app.state.stats_error=True
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; object-src 'none'"
    return response

def user(request):
    raw = request.cookies.get('__Host-dns_session', '')
    if not raw:
        return None
    with db() as c:
        row = c.execute('SELECT s.*,u.name,a.enabled,a.qps,a.burst,a.is_admin FROM sessions s JOIN users u ON u.sub=s.sub JOIN account_settings a ON a.sub=u.sub WHERE s.hash=? AND s.expires>?', (digest(raw),time.time())).fetchone()
    return dict(row) if row else None

def require_user(request):
    u=user(request)
    if not u:
        raise HTTPException(401, '请先使用 MatchAll 账号登录')
    return u

def csrf(request, u, value):
    origin=request.headers.get('origin')
    if origin and origin != BASE:
        raise HTTPException(403,'请求来源不匹配')
    if not secrets.compare_digest(u['csrf'],value):
        raise HTTPException(403,'请求校验失败，请刷新页面')

def owner_device(u, device_id):
    with db() as c:
        row=c.execute('SELECT * FROM devices WHERE id=? AND sub=? AND revoked IS NULL',(device_id,u['sub'])).fetchone()
    if not row:
        raise HTTPException(404,'设备不存在或已撤销')
    return dict(row)

def device_url(d):
    return BASE+'/dns-query/'+cipher().decrypt(d['token_enc'].encode()).decode()

def transport_host(d):
    suffix=os.environ.get('DNS_TLS_SUFFIX','')
    if not suffix:return ''
    raw=bytes.fromhex(cipher().decrypt(d['token_enc'].encode()).decode())
    return base64.b32encode(raw).decode().rstrip('=').lower()+'.'+suffix

def account_token(sub, rotate=False):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM devices WHERE sub=? AND revoked IS NULL ORDER BY created LIMIT 1',(sub,)).fetchone()
        if row and not rotate:
            return dict(row)
        if rotate:
            c.execute("UPDATE devices SET revoked=?,token_enc='' WHERE sub=? AND revoked IS NULL",(int(time.time()),sub))
        token=secrets.token_hex(32); ident=uuid.uuid4().hex
        c.execute('INSERT INTO devices(id,sub,label,token_hash,token_enc,created) VALUES(?,?,?,?,?,?)',
                  (ident,sub,'账号共用令牌',digest(token),cipher().encrypt(token.encode()).decode(),int(time.time())))
        return dict(c.execute('SELECT * FROM devices WHERE id=?',(ident,)).fetchone())

@app.post('/account/rotate')
def rotate_account(request:Request,csrf_token:str=Form(...)):
    u=require_user(request);csrf(request,u,csrf_token)
    account_token(u['sub'],rotate=True)
    return RedirectResponse('/',303)

@app.get('/', response_class=HTMLResponse)
def home(request:Request):
    u=user(request)
    if u:
        d=account_token(u['sub'])
        return templates.TemplateResponse(request=request,name='account.html',context={'user':u,'device':d,'url':device_url(d),'tls_host':transport_host(d),'dns_ipv4':DNS_IPV4,'dns_ipv6':DNS_IPV6,'usage':mg.totals(db,u['sub']),'filtering':moddns.mapping(db,u['sub']),'moddns_available':bool(moddns.API)})
    devices=[]
    if u:
        with db() as c:
            devices=[dict(r) for r in c.execute('SELECT id,label,created,requests,errors,last_seen FROM devices WHERE sub=? AND revoked IS NULL ORDER BY created DESC',(u['sub'],))]
    return templates.TemplateResponse(request=request,name='landing.html',context={'user':u})

@app.get('/guide', response_class=HTMLResponse)
def guide(request:Request):
    return templates.TemplateResponse(request=request,name='guide.html',context={'user':user(request),'dns_ipv4':DNS_IPV4,'dns_ipv6':DNS_IPV6})

@app.get('/healthz')
def health():
    with db() as c:c.execute('SELECT 1').fetchone()
    return {'status':'ok'}

@app.get('/login')
def login():
    state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(64); nonce=secrets.token_urlsafe(32)
    with db() as c:
        c.execute('DELETE FROM oauth WHERE expires<?',(time.time(),))
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO oauth VALUES(?,?,?,?)',(digest(state),verifier,nonce,int(time.time())+600))
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params={'client_id':CLIENT_ID,'response_type':'code','redirect_uri':BASE+'/auth/callback','scope':'openid profile email','state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256'}
    r=RedirectResponse(OIDC+'/authorize/?'+urlencode(params),302)
    r.set_cookie('__Host-dns_oauth',state,secure=True,httponly=True,samesite='lax',max_age=600)
    return r

@app.get('/auth/callback')
async def callback(request:Request, code:str='',state:str=''):
    cookie=request.cookies.get('__Host-dns_oauth','')
    if not code or not state or not cookie or not secrets.compare_digest(state,cookie):
        raise HTTPException(400,'登录校验失败，请重新登录')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        flow=c.execute('SELECT * FROM oauth WHERE hash=? AND expires>?',(digest(state),time.time())).fetchone()
        c.execute('DELETE FROM oauth WHERE hash=?',(digest(state),))
    if not flow:raise HTTPException(400,'登录已过期或已使用')
    h=request.app.state.http
    try:
        resp=await h.post(OIDC+'/token/',data={'grant_type':'authorization_code','code':code,'redirect_uri':BASE+'/auth/callback','client_id':CLIENT_ID,'client_secret':secret('OIDC_SECRET'),'code_verifier':flow['verifier']},timeout=15)
        resp.raise_for_status(); tokens=resp.json()
        discovery=await h.get(ISSUER+'.well-known/openid-configuration',timeout=15)
        discovery.raise_for_status(); metadata=discovery.json()
        if metadata['issuer']!=ISSUER:raise ValueError('issuer')
        jwks=await h.get(metadata['jwks_uri'],timeout=15); jwks.raise_for_status()
        hdr=jwt.get_unverified_header(tokens['id_token'])
        key=next(k for k in jwks.json()['keys'] if k['kid']==hdr.get('kid'))
        claims=jwt.decode(tokens['id_token'],jwt.PyJWK.from_dict(key).key,algorithms=['RS256'],audience=CLIENT_ID,issuer=ISSUER,options={'require':['exp','iat','sub','nonce']})
        if not secrets.compare_digest(claims['nonce'],flow['nonce']):raise ValueError('nonce')
        info=await h.get(OIDC+'/userinfo/',headers={'Authorization':'Bearer '+tokens['access_token']},timeout=15)
        info.raise_for_status(); profile=info.json()
        if profile['sub']!=claims['sub']:raise ValueError('subject')
    except Exception:
        raise HTTPException(502,'MatchAll 登录验证暂时失败，请重试') from None
    now=int(time.time()); raw=secrets.token_urlsafe(32)
    with db() as c:
        c.execute('INSERT INTO users VALUES(?,?,?) ON CONFLICT(sub) DO UPDATE SET name=excluded.name',(claims['sub'],str(profile.get('preferred_username') or profile.get('name') or 'MatchAll 用户')[:100],now))
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(digest(raw),claims['sub'],secrets.token_urlsafe(32),now+86400))
    r=RedirectResponse('/',303)
    r.delete_cookie('__Host-dns_oauth',secure=True,httponly=True,samesite='lax')
    r.set_cookie('__Host-dns_session',raw,secure=True,httponly=True,samesite='lax',max_age=86400)
    return r

@app.post('/logout')
def logout(request:Request,csrf_token:str=Form(...)):
    u=require_user(request);csrf(request,u,csrf_token)
    with db() as c:c.execute('DELETE FROM sessions WHERE hash=?',(u['hash'],))
    r=RedirectResponse('/',303);r.delete_cookie('__Host-dns_session',secure=True,httponly=True,samesite='lax');return r

@app.post('/devices')
def create_device(request:Request,label:str=Form(''),csrf_token:str=Form(...)):
    u=require_user(request);csrf(request,u,csrf_token)
    device_id=account_token(u['sub'])['id']
    return RedirectResponse('/devices/'+device_id,303)

@app.get('/devices/{device_id}',response_class=HTMLResponse)
def device(request:Request,device_id:str):
    u=require_user(request);d=owner_device(u,device_id)
    return templates.TemplateResponse(request=request,name='account.html',context={'user':u,'device':d,'url':device_url(d),'tls_host':transport_host(d),'dns_ipv4':DNS_IPV4,'dns_ipv6':DNS_IPV6,'usage':mg.totals(db,u['sub']),'filtering':moddns.mapping(db,u['sub']),'moddns_available':bool(moddns.API)})

@app.post('/devices/{device_id}/revoke')
def revoke(request:Request,device_id:str,csrf_token:str=Form(...)):
    u=require_user(request);csrf(request,u,csrf_token);owner_device(u,device_id)
    with db() as c:c.execute("UPDATE devices SET revoked=?,token_enc='' WHERE id=? AND sub=?",(int(time.time()),device_id,u['sub']))
    return RedirectResponse('/',303)

@app.get('/devices/{device_id}/profile.mobileconfig')
def mobileconfig(request:Request,device_id:str):
    u=require_user(request);d=owner_device(u,device_id)
    ident='org.maximoraverse.dns.'+device_id
    payload={'PayloadType':'Configuration','PayloadVersion':1,'PayloadIdentifier':ident,'PayloadUUID':str(uuid.uuid5(uuid.NAMESPACE_URL,ident)),
      'PayloadDisplayName':'MatchAll DNS · '+d['label'],'PayloadDescription':'仅配置加密 DNS。无 VPN、证书或设备管理权限。撤销设备令牌后此配置不再可用。',
      'PayloadRemovalDisallowed':False,'PayloadContent':[{'PayloadType':'com.apple.dnsSettings.managed','PayloadVersion':1,'PayloadIdentifier':ident+'.settings',
      'PayloadUUID':str(uuid.uuid5(uuid.NAMESPACE_URL,ident+'.settings')),'PayloadDisplayName':'MatchAll 加密 DNS',
      'DNSSettings':{'DNSProtocol':'HTTPS','ServerURL':device_url(d),'ServerAddresses':[DNS_IPV4,DNS_IPV6]},
      'OnDemandRules':[{'Action':'Connect'}]}]}
    return Response(plistlib.dumps(payload),media_type='application/x-apple-aspen-config',headers={'Content-Disposition':'attachment; filename="MatchAll-DNS.mobileconfig"'})

@app.api_route('/dns-query/{token}',methods=['GET','POST'])
async def doh(request:Request,token:str):
    if not re.fullmatch('[a-f0-9]{64}',token):raise HTTPException(404,'Not found')
    with mg.LOCK:
        with db() as c:
            d=c.execute('SELECT d.id,d.sub,a.enabled,a.qps,a.burst FROM devices d JOIN account_settings a ON a.sub=d.sub WHERE token_hash=? AND revoked IS NULL',(digest(token),)).fetchone()
        if not d:raise HTTPException(404,'Not found')
        if request.app.state.stats_error or time.monotonic()-request.app.state.last_flush>20:
            return Response(status_code=503,headers={'Retry-After':'5'})
        mg.count(d['sub'],'received')
        if not d['enabled']:
            mg.count(d['sub'],'disabled');return Response(status_code=403)
        if not mg.allow(d['sub'],d['qps'],d['burst']):
            mg.count(d['sub'],'limited');return Response(status_code=429,headers={'Retry-After':'1'})
        mg.count(d['sub'],'admitted')

    try:
        if request.method=='GET':
            b64=request.query_params.get('dns','')
            if not b64 or len(b64)>87384:raise ValueError()
            wire=base64.b64decode(b64+'='*((-len(b64))%4),altchars=b'-_',validate=True)
        else:
            if request.headers.get('content-type','').split(';')[0]!='application/dns-message':
                mg.count(d['sub'],'invalid')
                return Response(status_code=415)
            wire=b''
            async for chunk in request.stream():
                wire+=chunk
                if len(wire)>65535:raise ValueError()
        q=dns.message.from_wire(wire)
        if len(wire)>65535 or q.flags & dns.flags.QR or len(q.question)!=1 or q.opcode()!=0:raise ValueError()
        if q.question[0].rdtype in (251,252,255):raise ValueError()
    except Exception:
        mg.count(d['sub'],'invalid')
        return Response(status_code=400)
    ticket=qh.begin(d['sub'])
    routed=moddns.mapping(db,d['sub'])
    if routed and routed['routing'] and (routed['state']!='ready' or not moddns.DOH):
        qh.record(ticket,q,'policy_unavailable',None,'modDNS')
        return Response(status_code=503)
    endpoints=[moddns.DOH+'/dns-query/'+routed['profile_id']] if routed and routed['routing'] else UPSTREAMS
    upstream_client=request.app.state.moddns_http if routed and routed['routing'] else request.app.state.http
    answer=None;blocked=False;answer_rcode=None
    mg.count(d['sub'],'forwarded')
    try:
        async with asyncio.timeout(12):
            async with request.app.state.slots:
                for endpoint in endpoints:
                    try:
                        r=await upstream_client.post(endpoint,content=wire,headers={'Content-Type':'application/dns-message','Accept':'application/dns-message'})
                        if r.status_code!=200 or len(r.content)>65535:continue
                        if r.headers.get('content-type','application/dns-message').split(';')[0]!='application/dns-message':continue
                        parsed=dns.message.from_wire(r.content)
                        if not q.is_response(parsed) or parsed.rcode()==2:continue
                        blocked=bool(routed and routed['routing'] and r.headers.get('X-MatchAll-Blocked')=='1')
                        blocklists=tuple(x.strip() for x in r.headers.get('X-MatchAll-Blocklists','').split(',') if x.strip()) if blocked else ()
                        answer_rcode=parsed.rcode()
                        if routed and routed['routing']:mg.count_filtered(d['sub'],blocked,blocklists)
                        answer=r.content
                        if not (routed and routed["routing"]) and endpoint!=UPSTREAMS[0]:
                            with db() as c:c.execute('INSERT INTO node_events(timestamp,node,event) SELECT ?,?,? WHERE NOT EXISTS (SELECT 1 FROM node_events WHERE node=? AND timestamp>=?)',(int(time.time()),endpoint,'fallback_success',endpoint,int(time.time())//60*60))
                        break
                    except (httpx.HTTPError,ValueError,dns.exception.DNSException):continue
    except TimeoutError:pass
    mg.count(d['sub'],'failed' if answer is None else 'success')
    outcome='failed' if answer is None else 'blocked' if blocked else 'nxdomain' if answer_rcode==3 else 'response' if answer_rcode==0 else 'dns_error'
    qh.record(ticket,q,outcome,answer_rcode if answer is not None else 2,'modDNS' if routed and routed['routing'] else '原解析')
    if answer is None:
        failed=dns.message.make_response(q);failed.set_rcode(2);answer=failed.to_wire()
    return Response(answer,media_type='application/dns-message')


def require_admin(request):
    u=require_user(request)
    if not u['is_admin']:
        raise HTTPException(403,'需要 DNS 管理员权限')
    return u

@app.get('/api/usage')
def api_usage(request:Request):
    u=require_user(request)
    return {'last_24h':mg.totals(db,u['sub']),'enabled':bool(u['enabled']),'qps':u['qps'],'burst':u['burst']}

@app.get('/admin',response_class=HTMLResponse)
def admin_page(request:Request):
    u=require_admin(request)
    with db() as c:
        users=[dict(r) for r in c.execute("SELECT u.sub,u.name,a.*,COALESCE(m.state,'legacy') filter_state,COALESCE(m.routing,0) filter_routing,m.revision filter_revision,m.updated filter_updated FROM users u JOIN account_settings a ON a.sub=u.sub LEFT JOIN moddns_mapping m ON m.sub=u.sub ORDER BY u.created DESC LIMIT 200")]
        audit=[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]
        events=[dict(r) for r in c.execute('SELECT * FROM node_events ORDER BY id DESC LIMIT 30')]
    return templates.TemplateResponse(request=request,name='admin.html',context={'user':u,'accounts':users,'audit':audit,'nodes':mg.health,'events':events,'usage':mg.totals(db),'state_labels':operations.STATE_LABELS})

@app.get('/api/admin/accounts')
def admin_accounts(request:Request,offset:int=0):
    require_admin(request)
    with db() as c:return [dict(r) for r in c.execute('SELECT u.sub,u.name,a.enabled,a.qps,a.burst,a.is_admin FROM users u JOIN account_settings a ON a.sub=u.sub ORDER BY u.sub LIMIT 100 OFFSET ?',(max(0,offset),))]

@app.post('/admin/accounts/{sub}')
def admin_update(request:Request,sub:str,csrf_token:str=Form(...),enabled:int=Form(...),qps:int=Form(...),burst:int=Form(...)):
    u=require_admin(request);csrf(request,u,csrf_token)
    if enabled not in (0,1) or not 1<=qps<=1000 or not 1<=burst<=2000:raise HTTPException(422,'配额超出范围')
    with mg.LOCK:
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            # Recheck role in same write transaction, including revocation races.
            role=c.execute('SELECT is_admin FROM account_settings WHERE sub=?',(u['sub'],)).fetchone()
            if not role or not role[0]:raise HTTPException(403,'管理员权限已撤销')
            row=c.execute('SELECT enabled,qps,burst FROM account_settings WHERE sub=?',(sub,)).fetchone()
            if not row:raise HTTPException(404,'账号不存在')
            before=dict(row);after={'enabled':enabled,'qps':qps,'burst':burst}
            c.execute('UPDATE account_settings SET enabled=?,qps=?,burst=? WHERE sub=?',(enabled,qps,burst,sub))
            mg.audit(c,u['sub'],sub,'account.update',before,after)
        mg.resize(sub,qps,burst)
    return RedirectResponse('/admin',303)

moddns.install(app,db,require_user,csrf,templates,mg)
operations.install(app,db,require_admin,csrf,templates,mg)
statistics_panel.install(app,db,require_user,require_admin,templates,mg)

qh.install(app,db,require_user,csrf,templates,mg)
