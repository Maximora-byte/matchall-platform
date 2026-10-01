import copy,json,time
import pytest
from fastapi import HTTPException
import app as m
import moddns_adapter as a
import advanced_filters as f
from test_app import client,signin

@pytest.fixture
def backend(client,monkeypatch):
    signin(client)
    with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,account_id,profile_id,state,routing,updated) VALUES('user-a',?,'profileA','ready',0,?)",('a'*24,int(time.time())))
    p={'account_id':'a'*24,'settings':{'custom_rules':[],'custom_rule_groups':{'allow':[],'block':[]},'privacy':{'blocklists':[],'services':[]},'security':{'rebinding_protection':{'enabled':False}}}}
    calls=[]
    async def call(h,sub,method,path,data=None):
        assert sub=='user-a';assert path in ('/services','/blocklists') or path.startswith('/profiles/profileA')
        calls.append((method,path,data))
        if method=='GET':
            if path=='/services':return {'services':[{'id':'reddit','name':'Reddit','asns':[],'domains':['reddit.com']}]}
            if path=='/blocklists':return []
            return copy.deepcopy(p)
        if path.endswith('/custom_rules/batch'):
            rows=[]
            for value in data['values']:
                r={'id':format(len(p['settings']['custom_rules'])+1,'024x'),'action':data['action'],'value':value,'group':'','note':''};p['settings']['custom_rules'].append(r);rows.append(r)
            return {'created':copy.deepcopy(rows),'skipped':[]}
        if '/custom_rules/' in path:
            r=next(x for x in p['settings']['custom_rules'] if x['id']==path.split('/')[-1]);r.update(data)
        if path.endswith('/rebinding'):p['settings']['security']['rebinding_protection']['enabled']=data['enabled']
        return None
    async def sleep(_):pass
    monkeypatch.setattr(a,'call',call);monkeypatch.setattr(f.asyncio,'sleep',sleep)
    return p,calls

def post(client,**data):return client.post('/filters/advanced',data={'csrf_token':'csrf',**data},follow_redirects=False)

def test_permissions_and_csrf(client):
    assert client.get('/filters/rules.json').status_code==401
    assert post(client,operation='rebinding_on').status_code==401
    signin(client)
    assert client.post('/filters/advanced',data={'csrf_token':'bad','operation':'rebinding_on'}).status_code==403
    assert client.post('/filters/prepare',data={'csrf_token':'bad'}).status_code==403

@pytest.mark.parametrize('value',['https://example.com','||example.com^','bad name.com','a/b.com','localhost','a..com'])
def test_invalid_syntax(value):
    with pytest.raises(HTTPException):f.parse_rules(value,'block','')

def test_import_append_export_and_dormant_route(client,backend):
    p,calls=backend
    r=post(client,operation='import',raw='Example.com\nexample.com\n*.example.net',group='工作/~')
    assert r.status_code==303 and 'imported=2' in r.headers['location']
    assert p['settings']['custom_rules'][0]['value']=='*.example.com'
    assert all(x['group']=='工作/~' for x in p['settings']['custom_rules'])
    before=copy.deepcopy(p)
    assert 'imported=0' in post(client,operation='import',raw='example.com',group='different').headers['location']
    assert p==before
    r=client.get('/filters/rules.json?profile_id=other')
    assert r.status_code==200 and 'account_id' not in r.text and 'profileA' not in r.text and 'id' not in r.json()['rules'][0]
    assert r.headers['cache-control']=='no-store'
    assert f.parse_rules(r.text,'allow','ignored')==r.json()['rules']
    row=a.mapping(m.db,'user-a');assert row['routing']==0 and row['personalized']==1 and row['state']=='ready'
    page=client.get('/filters');assert page.status_code==200 and '尚未切换解析' in page.text

def test_bounds_invalid_payload_before_mutation(client,backend):
    p,calls=backend
    for raw in ['\n'.join(f'{i}.example.com' for i in range(201)),json.dumps({'format':'evil','rules':[]}),json.dumps({'format':'matchall-rules-v1','rules':[{'action':'block','value':'ok.com','group':'x'*65}]})]:
        assert post(client,operation='import',raw=raw).status_code==422
    assert not calls and a.mapping(m.db,'user-a')['state']=='ready'

def test_wrong_profile_and_disabled_guard(client,backend):
    p,calls=backend;p['account_id']='b'*24
    assert post(client,operation='rebinding_on').status_code==403
    with m.db() as c:c.execute("UPDATE account_settings SET enabled=0 WHERE sub='user-a'")
    assert post(client,operation='rebinding_on').status_code==403
    assert all(method=='GET' for method,_,_ in calls)

def test_scoped_groups_service_security(client,backend):
    p,calls=backend
    assert post(client,operation='group_rename',group='a/~',value='b/~',profile_id='foreign').status_code==303
    assert calls[-2][2]['updates'][0]['from']=='/a~1~0'
    assert post(client,operation='service_on',value='reddit').status_code==303
    assert post(client,operation='service_on',value='unknown').status_code==422
    assert post(client,operation='rebinding_on').status_code==303
    assert p['settings']['security']['rebinding_protection']['enabled'] is True
    assert a.mapping(m.db,'user-a')['routing']==0

def test_service_catalog_grouped_on_page(client,backend):
    page=client.get('/filters')
    assert page.status_code==200 and '按服务屏蔽' in page.text and '其他 · 1 个服务' in page.text

def test_ambiguous_partial_import_closed(client,backend,monkeypatch):
    p,calls=backend;original=a.call
    async def failed(h,sub,method,path,data=None):
        if method=='PATCH':raise HTTPException(503,'fail')
        return await original(h,sub,method,path,data)
    monkeypatch.setattr(a,'call',failed)
    r=post(client,operation='import',raw='example.com',group='group')
    assert r.status_code==503 and len(p['settings']['custom_rules'])==1
    row=a.mapping(m.db,'user-a');assert row['state']=='error' and row['routing']==0

def test_export_other_account_rejected(client,backend):
    signin(client,'user-b');assert client.get('/filters/rules.json?sub=user-a').status_code==404

def test_pending_update_no_remote_write(client,backend):
    with m.db() as c:c.execute("UPDATE moddns_mapping SET state='updating'")
    assert post(client,operation='rebinding_on').status_code==409
    assert backend[1]==[]
