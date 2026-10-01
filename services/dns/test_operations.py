import datetime,json,time,sqlite3
import pytest
import app as m
import moddns_adapter as a
import operations as ops
from test_app import client,signin,create
from test_management import make_admin

def setup(client,state='error',routing=1,age=120):
    signin(client);make_admin()
    with m.db() as c:
        c.execute("INSERT INTO users VALUES('target','Target',?)",(int(time.time()),))
        c.execute("UPDATE account_settings SET enabled=0 WHERE sub='target'")
        c.execute("INSERT INTO moddns_mapping(sub,account_id,profile_id,state,routing,revision,personalized,updated) VALUES('target',?,'profileA',?,?,7,1,?)",('a'*24,state,routing,int(time.time())-age))

def recover(client,csrf='csrf'):
    return client.post('/admin/filters/target/recover',data={'csrf_token':csrf},follow_redirects=False)

def remote(monkeypatch,alter=None):
    monkeypatch.setattr(a,'API','http://internal');monkeypatch.setattr(a,'DOH','https://proxy')
    async def call(h,sub,method,path,data=None):
        if alter:alter(path)
        if path=='/account':return {'account_id':'a'*24,'profile_id':'profileA'}
        assert method=='GET' # never silently enable defaults on an existing policy
        return {'account_id':'a'*24,'settings':{'privacy':{'blocklists':[]}}}
    monkeypatch.setattr(a,'call',call)

def test_admin_visibility_and_csrf(client):
    assert client.get('/admin/operations').status_code==401
    assert client.get('/api/admin/operations').status_code==401
    assert recover(client).status_code==401
    signin(client)
    assert client.get('/api/admin/operations').status_code==403
    assert recover(client).status_code==403
    make_admin()
    assert recover(client,'wrong').status_code==403
    assert recover(client).status_code==404
    assert client.get('/admin/operations').status_code==200

@pytest.mark.parametrize('routing',[0,1])
def test_recovery_preserves_routing_disabled_state_and_revision(client,monkeypatch,routing):
    setup(client,routing=routing);remote(monkeypatch)
    assert recover(client).status_code==303
    row=a.mapping(m.db,'target');assert row['state']=='ready' and row['routing']==routing and row['revision']==7
    with m.db() as c:
        assert c.execute("SELECT enabled FROM account_settings WHERE sub='target'").fetchone()[0]==0
        assert c.execute("SELECT count(*) FROM audit WHERE action='filter.recover.complete'").fetchone()[0]==1
    assert recover(client).status_code==303
    with m.db() as c:assert c.execute("SELECT count(*) FROM audit WHERE action='filter.recover.complete'").fetchone()[0]==1

@pytest.mark.parametrize('state,age,status',[('deleted',120,410),('deleting',120,410),('pending',0,409),('updating',0,409)])
def test_forbidden_recoveries(client,monkeypatch,state,age,status):
    setup(client,state=state,age=age)
    assert recover(client).status_code==status
    assert a.mapping(m.db,'target')['state']==state

def test_inflight_conflict(client,monkeypatch):
    setup(client)
    class Busy:
        def locked(self):return True
    monkeypatch.setattr(a,'account_lock',lambda _:Busy())
    assert recover(client).status_code==409
    assert a.mapping(m.db,'target')['state']=='error'

def test_revoked_admin_cannot_commit_recovery(client,monkeypatch):
    setup(client)
    def revoke(path):
        if path=='/account':
            with m.db() as c:c.execute("UPDATE account_settings SET is_admin=0 WHERE sub='user-a'")
    remote(monkeypatch,revoke)
    assert recover(client).status_code==403
    assert a.mapping(m.db,'target')['state']=='error'

def test_audit_failure_keeps_recovery_closed(client,monkeypatch):
    setup(client);remote(monkeypatch)
    with m.db() as c:c.execute("CREATE TRIGGER reject_complete BEFORE INSERT ON audit WHEN NEW.action='filter.recover.complete' BEGIN SELECT RAISE(ABORT,'test'); END")
    assert recover(client).status_code==503
    assert a.mapping(m.db,'target')['state']=='error'

def test_identity_mismatch_not_rebound(client,monkeypatch):
    setup(client);remote(monkeypatch)
    original=a.call
    async def different(*args,**kwargs):
        result=await original(*args,**kwargs);result['account_id']='b'*24;return result
    monkeypatch.setattr(a,'call',different)
    assert recover(client).status_code==503
    row=a.mapping(m.db,'target');assert row['account_id']=='a'*24 and row['state']=='error'

def test_health_report_freshness_and_allowlist(tmp_path,monkeypatch):
    p=tmp_path/'health.json';monkeypatch.setenv('DNS_HOST_HEALTH_FILE',str(p))
    assert ops.host_status()['status']=='unavailable'
    now=datetime.datetime.now(datetime.timezone.utc)
    p.write_text(json.dumps({'checked':now.isoformat(),'ok':True,'errors':[],'secret':'never return'}))
    result=ops.host_status();assert result['ok'] and 'secret' not in result
    p.write_text(json.dumps({'checked':(now-datetime.timedelta(minutes=16)).isoformat(),'ok':True}))
    assert ops.host_status()['status']=='stale' and not ops.host_status()['ok']
    p.write_text('[]');assert ops.host_status()['status']=='unavailable'
