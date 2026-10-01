"""Local synthetic account test; not a substitute for owner-controlled OIDC login."""
import base64,json,secrets,time,uuid,plistlib,os
import httpx,dns.message
import app as m
sub='deployment-test-'+uuid.uuid4().hex
raw=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
with m.db() as c:
    c.execute('INSERT INTO users VALUES(?,?,?)',(sub,'临时部署验收',int(time.time())))
    c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(m.digest(raw),sub,csrf,int(time.time())+600))
try:
    with httpx.Client(base_url=os.getenv('SMOKE_URL','http://127.0.0.1:8000'),headers={'Cookie':'__Host-dns_session='+raw,'Origin':m.BASE},timeout=20) as h:
        assert h.get('/').status_code==200
        with m.db() as c:
            assert c.execute('SELECT COUNT(*) FROM devices WHERE sub=? AND revoked IS NULL',(sub,)).fetchone()[0]==1
        r=h.post('/devices',data={'label':'临时验收设备','csrf_token':csrf});assert r.status_code==303
        path=r.headers['location']
        assert h.get(path).status_code==200
        p=plistlib.loads(h.get(path+'/profile.mobileconfig').content)
        endpoint=p['PayloadContent'][0]['DNSSettings']['ServerURL'].removeprefix(m.BASE)
        results={}
        for name,expected in [('example.com',0),('pagead2.googlesyndication.com',3),('dnssec-failed.org',2)]:
            wire=dns.message.make_query(name,'A').to_wire()
            started=time.monotonic()
            r=h.post(endpoint,content=wire,headers={'Content-Type':'application/dns-message'})
            assert r.status_code==200
            answer=dns.message.from_wire(r.content);assert answer.rcode()==expected,(name,answer.rcode())
            results[name]={'rcode':answer.rcode(),'seconds':round(time.monotonic()-started,2)}
        assert h.post('/account/rotate',data={'csrf_token':csrf}).status_code==303
        assert h.get(endpoint).status_code==404
        assert h.get('/').status_code==200
        with m.db() as c:
            assert c.execute('SELECT COUNT(*) FROM devices WHERE sub=? AND revoked IS NULL',(sub,)).fetchone()[0]==1
        print(json.dumps({'live_upstream_tests':results,'account_rotation':'passed','one_token_per_account':'passed','profile':'passed','synthetic_only':True}))
finally:
    with m.db() as c:
        c.execute('DELETE FROM devices WHERE sub=?',(sub,));c.execute('DELETE FROM sessions WHERE sub=?',(sub,));c.execute('DELETE FROM users WHERE sub=?',(sub,))
