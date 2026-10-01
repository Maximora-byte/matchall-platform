import base64
import plistlib
import time
import uuid

import dns.message
import dns.rcode
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import app as m

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(m,'DATA',tmp_path)
    key=tmp_path/'key';key.write_bytes(Fernet.generate_key())
    monkeypatch.setenv('TOKEN_KEY_FILE',str(key))
    m.buckets.clear()
    with TestClient(m.app,base_url=m.BASE) as c:yield c

def signin(client,who='user-a'):
    raw=uuid.uuid4().hex
    with m.db() as c:
        c.execute('INSERT OR IGNORE INTO users VALUES(?,?,?)',(who,who,int(time.time())))
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(m.digest(raw),who,'csrf',int(time.time())+3600))
    client.cookies.set('__Host-dns_session',raw)

def create(client):
    r=client.post('/devices',data={'label':'My Phone','csrf_token':'csrf'},follow_redirects=False)
    assert r.status_code==303
    ident=r.headers['location'].split('/')[-1]
    with m.db() as c:d=dict(c.execute('SELECT * FROM devices WHERE id=?',(ident,)).fetchone())
    return ident,m.cipher().decrypt(d['token_enc'].encode()).decode()

def query():
    return dns.message.make_query('example.com','A').to_wire()

def test_anonymous_and_unknown_token(client):
    assert client.post('/devices',data={'label':'a','csrf_token':'a'}).status_code==401
    assert client.get('/devices/nope').status_code==401
    assert client.get('/dns-query/'+'a'*64).status_code==404
    assert client.get('/dns-query').status_code==404

def test_csrf_and_owner_isolation(client):
    signin(client)
    assert client.post('/devices',data={'label':'a','csrf_token':'bad'}).status_code==403
    assert client.post('/devices',data={'label':'a','csrf_token':'csrf'},headers={'Origin':'https://evil.example'}).status_code==403
    ident,token=create(client)
    assert token in client.get('/').text
    signin(client,'user-b')
    assert client.get('/devices/'+ident).status_code==404
    assert client.get('/devices/'+ident+'/profile.mobileconfig').status_code==404
    assert client.post('/devices/'+ident+'/revoke',data={'csrf_token':'csrf'}).status_code==404

def test_profile_and_revocation(client):
    signin(client);ident,token=create(client)
    r=client.get('/devices/'+ident+'/profile.mobileconfig')
    profile=plistlib.loads(r.content)
    assert profile['PayloadContent'][0]['DNSSettings']['ServerURL'].endswith('/'+token)
    assert profile['PayloadContent'][0]['DNSSettings']['ServerAddresses']==[m.DNS_IPV4,m.DNS_IPV6]
    assert len(profile['PayloadContent'])==1
    assert r.headers['cache-control']=='no-store'
    client.post('/devices/'+ident+'/revoke',data={'csrf_token':'csrf'})
    assert client.get('/dns-query/'+token).status_code==404
    assert client.get('/devices/'+ident+'/profile.mobileconfig').status_code==404

def test_account_and_guide_show_dual_stack_instructions(client):
    signin(client);create(client)
    account=client.get('/')
    assert account.status_code==200
    assert m.DNS_IPV4 in account.text and m.DNS_IPV6 in account.text
    assert 'IPv4 / IPv6 双栈服务器' in account.text
    assert 'IPv4 和 IPv6 的 DNS over HTTPS' in account.text
    guide=client.get('/guide')
    assert guide.status_code==200
    assert m.DNS_IPV4 in guide.text and m.DNS_IPV6 in guide.text
    assert 'IPv4 / IPv6 双栈怎么配置' in guide.text

def test_forwarding_failover_and_validation(client):
    signin(client);ident,token=create(client);seen=[]
    def upstream(req):
        seen.append(req.url.host)
        if 'dns-hk' in req.url.host:return httpx.Response(503)
        answer=dns.message.make_response(dns.message.from_wire(req.content))
        return httpx.Response(200,content=answer.to_wire())
    old=m.app.state.http
    m.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    try:
        wire=query();path='/dns-query/'+token
        r=client.post(path,content=wire,headers={'Content-Type':'application/dns-message'})
        assert r.status_code==200 and dns.message.from_wire(r.content).rcode()==0
        assert seen==['dns-hk.maximoraverse.org','dns-backup.maximoraverse.org']
        assert client.get(path,params={'dns':base64.urlsafe_b64encode(wire).decode().rstrip('=')}).status_code==200
        assert client.post(path,content=wire).status_code==415
        assert client.get(path,params={'dns':'!!!'}).status_code==400
        assert client.post(path,content=b'x'*65536,headers={'Content-Type':'application/dns-message'}).status_code==400
    finally:m.app.state.http=old

def test_fail_closed_when_both_upstreams_fail(client):
    signin(client);_,token=create(client)
    old=m.app.state.http;m.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(503)))
    try:
        r=client.post('/dns-query/'+token,content=query(),headers={'Content-Type':'application/dns-message'})
        assert dns.message.from_wire(r.content).rcode()==dns.rcode.SERVFAIL
    finally:m.app.state.http=old

def test_oidc_state_pkce_and_invalid_callback(client):
    r=client.get('/login',follow_redirects=False)
    assert r.status_code==302
    assert 'code_challenge_method=S256' in r.headers['location']
    assert 'nonce=' in r.headers['location']
    assert 'Secure' in r.headers['set-cookie'] and 'HttpOnly' in r.headers['set-cookie']
    assert client.get('/auth/callback?code=bad&state=bad').status_code==400

def test_limits(client):
    signin(client)
    first=create(client)
    for _ in range(3):assert create(client)==first
    assert client.post('/account/rotate',data={'csrf_token':'bad'}).status_code==403
    assert client.post('/account/rotate',data={'csrf_token':'csrf'},follow_redirects=False).status_code==303
    assert client.get('/dns-query/'+first[1]).status_code==404
    assert create(client)!=first
    with m.db() as c:
        assert c.execute('SELECT COUNT(*) FROM devices WHERE revoked IS NULL').fetchone()[0]==1
    assert all(m.allow('test',60,60) for _ in range(60))
    assert not m.allow('test',60,60)

def test_oidc_signed_callback_and_replay(client,tmp_path,monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from urllib.parse import parse_qs,urlparse
    import json,jwt
    secret=tmp_path/'oidc';secret.write_text('test-secret');monkeypatch.setenv('OIDC_SECRET_FILE',str(secret))
    start=client.get('/login',follow_redirects=False)
    params=parse_qs(urlparse(start.headers['location']).query)
    state=params['state'][0];nonce=params['nonce'][0]
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pub=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));pub['kid']='test'
    token=jwt.encode({'sub':'oidc-user','iss':m.ISSUER,'aud':m.CLIENT_ID,'exp':int(time.time())+300,'iat':int(time.time()),'nonce':nonce},key,algorithm='RS256',headers={'kid':'test'})
    def endpoint(req):
        if req.url.path.endswith('/token/'):return httpx.Response(200,json={'id_token':token,'access_token':'test-access'})
        if req.url.path.endswith('openid-configuration'):return httpx.Response(200,json={'issuer':m.ISSUER,'jwks_uri':m.ISSUER+'jwks/'})
        if req.url.path.endswith('jwks/'):return httpx.Response(200,json={'keys':[pub]})
        if req.url.path.endswith('userinfo/'):return httpx.Response(200,json={'sub':'oidc-user','preferred_username':'test-user'})
        return httpx.Response(404)
    old=m.app.state.http;m.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(endpoint))
    try:
        response=client.get('/auth/callback',params={'code':'test-code','state':state},follow_redirects=False)
        assert response.status_code==303
        assert 'test-user' in client.get('/').text
        assert client.get('/auth/callback',params={'code':'test-code','state':state}).status_code==400
    finally:m.app.state.http=old


def test_form_origin_and_referrer_policy(client):
    signin(client)
    r=client.get('/')
    assert r.headers['referrer-policy']=='same-origin'
    assert 'name="referrer" content="same-origin"' in r.text
    for origin in ['null','https://evil.example',m.BASE+'.evil.example']:
        assert client.post('/logout',data={'csrf_token':'csrf'},headers={'Origin':origin}).status_code==403
    assert client.post('/logout',data={'csrf_token':'wrong'},headers={'Origin':m.BASE}).status_code==403
    assert client.post('/logout',data={'csrf_token':'csrf'},headers={'Origin':m.BASE},follow_redirects=False).status_code==303
