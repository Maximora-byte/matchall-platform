import sqlite3
import time
import base64
import httpx
import pytest
import dns.message
import app as m
import management as mg
from test_app import client,signin,create,query

@pytest.fixture(autouse=True)
def clean_state():
    mg.pending.clear();mg.account_buckets.clear();mg.health.clear()
    yield
    mg.pending.clear();mg.account_buckets.clear()

def make_admin():
    with m.db() as c:c.execute("UPDATE account_settings SET is_admin=1 WHERE sub='user-a'")

def change(client,**kw):
    return client.post('/admin/accounts/user-a',data={'csrf_token':'csrf','enabled':1,'qps':60,'burst':60,**kw},follow_redirects=False)

def test_management_permissions_and_audit(client):
    assert client.get('/admin').status_code==401
    signin(client)
    assert client.get('/admin').status_code==403
    assert change(client).status_code==403
    make_admin()
    assert client.get('/admin').status_code==200
    assert change(client,csrf_token='invalid').status_code==403
    assert change(client,qps=0).status_code==422
    assert change(client,qps=20,burst=30).status_code==303
    with m.db() as c:
        assert c.execute('SELECT qps FROM account_settings').fetchone()[0]==20
        assert c.execute("SELECT count(*) FROM audit WHERE result='ok'").fetchone()[0]==1
        c.execute('UPDATE account_settings SET is_admin=0')
    assert change(client).status_code==403

def test_atomic_audit_failure(client):
    signin(client);make_admin()
    with m.db() as c:c.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(sqlite3.IntegrityError):change(client,qps=10)
    with m.db() as c:assert c.execute('SELECT qps FROM account_settings').fetchone()[0]==60

def test_disable_restore_get_post_and_rotation(client):
    signin(client);make_admin();_,token=create(client)
    path='/dns-query/'+token
    before=None
    with m.db() as c:before=tuple(c.execute('SELECT token_hash,token_enc FROM devices').fetchone())
    assert change(client,enabled=0).status_code==303
    assert client.get(path).status_code==403
    assert client.post(path,content=query(),headers={'Content-Type':'application/dns-message'}).status_code==403
    client.get('/')
    with m.db() as c:
        assert c.execute('SELECT enabled FROM account_settings').fetchone()[0]==0
        assert tuple(c.execute('SELECT token_hash,token_enc FROM devices').fetchone())==before
    assert change(client).status_code==303
    assert client.get(path).status_code==400
    client.post('/account/rotate',data={'csrf_token':'csrf'})
    assert client.get(path).status_code==404

def test_bucket_update_no_refill(client,monkeypatch):
    signin(client);make_admin()
    monkeypatch.setattr(mg.time,'monotonic',lambda:100.0)
    assert all(mg.allow('user-a',60,60) for _ in range(60))
    assert not mg.allow('user-a',60,60)
    change(client,qps=1,burst=2)
    assert not mg.allow('user-a',1,2)
    client.post('/account/rotate',data={'csrf_token':'csrf'})
    assert not mg.allow('user-a',1,2)

def test_usage_no_retry_double_count(client):
    signin(client);_,token=create(client);seen=[]
    def upstream(req):
        seen.append(req.url.host)
        if 'dns-hk' in req.url.host:return httpx.Response(503)
        answer=dns.message.make_response(dns.message.from_wire(req.content));answer.set_rcode(3)
        return httpx.Response(200,content=answer.to_wire(),headers={'Content-Type':'application/dns-message'})
    old=m.app.state.http;m.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    try:
        assert client.post('/dns-query/'+token,content=query(),headers={'Content-Type':'application/dns-message'}).status_code==200
        counts=client.get('/api/usage').json()['last_24h']
        assert counts=={'received':1,'admitted':1,'forwarded':1,'success':1}
        assert len(seen)==2
    finally:m.app.state.http=old

def test_migration_preserves_legacy_and_restore(client,tmp_path):
    signin(client);create(client)
    with m.db() as c:
        before=[tuple(r) for r in c.execute('SELECT * FROM devices')]
        ids=[tuple(r) for r in c.execute('SELECT * FROM users')]
        out=sqlite3.connect(tmp_path/'restore.sqlite3');c.backup(out);out.close()
    mg.migrate(m.db);mg.migrate(m.db)
    with m.db() as c:
        assert [tuple(r) for r in c.execute('SELECT * FROM devices')]==before
        assert [tuple(r) for r in c.execute('SELECT * FROM users')]==ids
    with sqlite3.connect(tmp_path/'restore.sqlite3') as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert c.execute('SELECT * FROM devices').fetchall()==before
