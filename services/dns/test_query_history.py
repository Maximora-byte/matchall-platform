import time
import dns.message,dns.rcode
import httpx,pytest
import app as m
import query_history as qh
import moddns_adapter as a
from test_app import client,signin,create,query

def setting(client,action='enable',**kw):return client.post('/queries/settings',data={'csrf_token':'csrf','action':action,'consent':'record_domains',**kw},follow_redirects=False)
def add(sub='user-a',name='private-test.invalid',outcome='response',rcode=0):qh.record(qh.begin(sub),dns.message.make_query(name,'A'),outcome,rcode,'原解析')

def test_default_off_and_opt_in_persists_without_sensitive_fields(client):
    signin(client);add();assert client.get('/api/queries').json()['count']==0
    assert setting(client).status_code==303
    add();data=client.get('/api/queries?sub=other').json();assert data['enabled'] and data['count']==1
    assert data['rows'][0]['domain']=='private-test.invalid'
    assert set(data['rows'][0])=={'id','timestamp','time','domain','type','outcome','label','rcode','latency_ms','route'}
    with m.db() as c:
        dump='\n'.join(c.iterdump())
        assert 'private-test.invalid' in dump
        assert 'token_hash' in dump and 'client_ip' not in c.execute("SELECT sql FROM sqlite_master WHERE name='query_history'").fetchone()[0]
    qh.initialize(m.db)
    assert client.get('/api/queries').json()['enabled'] and client.get('/api/queries').json()['count']==1

def test_permissions_csrf_consent_and_owner(client):
    assert client.get('/queries').status_code==401 and client.get('/api/queries').status_code==401
    signin(client)
    assert client.post('/queries/settings',data={'csrf_token':'bad','action':'enable','consent':'record_domains'}).status_code==403
    assert client.post('/queries/settings',data={'csrf_token':'csrf','action':'enable'}).status_code==422
    setting(client);add();ident=client.get('/api/queries').json()['rows'][0]['id']
    signin(client,'user-b');assert client.get('/api/queries?sub=user-a').json()['count']==0
    assert client.post('/queries/rule',data={'csrf_token':'csrf','record_id':ident,'action':'block'}).status_code==404
    assert client.get('/api/queries?outcome=bogus').status_code==422

def test_clear_disable_and_reenable_reject_inflight(client):
    signin(client);setting(client);old=qh.begin('user-a');add()
    setting(client,'clear');qh.record(old,dns.message.make_query('late.invalid','A'),'response',0,'原解析')
    assert qh.report('user-a')['count']==0 and qh.report('user-a')['enabled']
    old=qh.begin('user-a');setting(client,'disable');setting(client)
    qh.record(old,dns.message.make_query('late2.invalid','A'),'response',0,'原解析');assert qh.report('user-a')['count']==0
    add();setting(client,'disable');assert qh.report('user-a')['count']==0 and not qh.report('user-a')['enabled']

def test_permanent_retention_has_no_time_or_count_cap(client,monkeypatch):
    signin(client);setting(client,retention=0)
    for i in range(2100):add(name=f'{i}.invalid')
    assert qh.report('user-a')['count']==2100
    now=time.time();monkeypatch.setattr(qh.time,'time',lambda:now+3650*86400)
    assert qh.report('user-a')['count']==2100

def test_retention_reduction_prunes_immediately(client,monkeypatch):
    signin(client);setting(client,retention=86400);add()
    with m.db() as c:c.execute('UPDATE sessions SET expires=expires+86400')
    now=time.time();monkeypatch.setattr(qh.time,'time',lambda:now+4000)
    assert qh.report('user-a')['count']==1
    assert setting(client,retention=3600).status_code==303
    assert qh.report('user-a')['count']==0

def test_page_pagination_filter_ranking(client):
    signin(client);setting(client)
    for i in range(55):add(name='top.invalid' if i<50 else 'other.invalid',outcome='blocked' if i<3 else 'response')
    data=client.get('/api/queries').json();assert len(data['rows'])==50 and data['next_before']
    assert len(client.get('/api/queries',params={'before':data['next_before']}).json()['rows'])==5
    assert len(client.get('/api/queries?outcome=blocked').json()['rows'])==3
    assert len(client.get('/api/queries?domain=other').json()['rows'])==5
    assert data['top_domains'][0]=={'domain':'top.invalid','count':50} and data['top_blocked'][0]['count']==3
    assert client.get('/queries').status_code==200

def test_visual_ranges_and_invalid_period(client):
    signin(client);setting(client);add(name='visible.invalid',outcome='blocked')
    data=client.get('/api/queries?period=24h').json()
    assert data['count']==1 and data['blocked_count']==1 and data['blocked_rate']==100
    assert data['trend'] and data['top_domains'][0]['domain']=='visible.invalid'
    assert '查询趋势' in client.get('/queries?period=7d').text
    assert client.get('/api/queries?period=invalid').status_code==422

def test_service_and_category_statistics(client):
    signin(client);setting(client)
    add(name='www.youtube.com');add(name='unknown-private.invalid')
    data=client.get('/api/queries?period=all').json()['classification']
    assert data['services'][0]['name']=='Google'
    assert data['services'][0]['count']==1 and data['unclassified']==1
    assert '服务与类别统计' in client.get('/queries?period=all').text

def test_rule_prefill_does_not_write_or_switch(client):
    signin(client);setting(client)
    with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,account_id,profile_id,state,routing,updated) VALUES('user-a',?,'profileA','ready',0,?)",('a'*24,int(time.time())))
    add();ident=qh.report('user-a')['rows'][0]['id'];before=a.mapping(m.db,'user-a')
    r=client.post('/queries/rule',data={'csrf_token':'csrf','record_id':ident,'action':'block'})
    assert r.status_code==200 and 'private-test.invalid' in r.text and '不会启用 modDNS' in r.text
    assert a.mapping(m.db,'user-a')==before
    setting(client,'clear');assert client.post('/queries/rule',data={'csrf_token':'csrf','record_id':ident,'action':'block'}).status_code==404

def test_disabled_account_can_clear_not_enable(client):
    signin(client);setting(client);add()
    with m.db() as c:c.execute('UPDATE account_settings SET enabled=0')
    assert setting(client).status_code==403
    assert setting(client,'disable').status_code==303 and qh.report('user-a')['count']==0

@pytest.mark.parametrize('routed,rcode,marker,expected',[(False,3,False,'nxdomain'),(False,0,True,'response'),(True,0,True,'blocked'),(True,0,False,'response'),(True,2,False,'failed')])
def test_doh_outcomes_and_marker_trust(client,monkeypatch,routed,rcode,marker,expected):
    signin(client);_,token=create(client);setting(client)
    if routed:
        monkeypatch.setattr(a,'DOH','https://private.test')
        with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,account_id,profile_id,state,routing,updated) VALUES('user-a',?,'profileA','ready',1,?)",('a'*24,int(time.time())))
    def upstream(req):
        answer=dns.message.make_response(dns.message.from_wire(req.content));answer.set_rcode(rcode)
        return httpx.Response(200,content=answer.to_wire(),headers={'Content-Type':'application/dns-message','X-MatchAll-Blocked':'1' if marker else '0'})
    attr='moddns_http' if routed else 'http';old=getattr(m.app.state,attr);setattr(m.app.state,attr,httpx.AsyncClient(transport=httpx.MockTransport(upstream)))
    try:
        r=client.post('/dns-query/'+token,content=query(),headers={'Content-Type':'application/dns-message'});assert r.status_code==200
        data=client.get('/api/queries').json();assert data['count']==1 and data['rows'][0]['outcome']==expected
        assert token not in str(data)
    finally:setattr(m.app.state,attr,old)

def test_policy_unavailable_and_invalid_requests(client,monkeypatch):
    signin(client);_,token=create(client);setting(client)
    with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,state,routing,updated) VALUES('user-a','error',1,?)",(int(time.time()),))
    assert client.post('/dns-query/'+token,content=query(),headers={'Content-Type':'application/dns-message'}).status_code==503
    assert qh.report('user-a')['rows'][0]['outcome']=='policy_unavailable'
    assert client.post('/dns-query/'+token,content=b'invalid',headers={'Content-Type':'application/dns-message'}).status_code==400
    assert qh.report('user-a')['count']==1
