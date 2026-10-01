import copy,json,re,time
import pytest
from fastapi import HTTPException
import app as m
import moddns_adapter as a
import filter_config as f
from test_app import client,signin

@pytest.fixture
def config_backend(client,monkeypatch):
    signin(client)
    with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,account_id,profile_id,state,routing,updated) VALUES('user-a',?,'profileA','ready',0,?)",('a'*24,int(time.time())))
    p={'account_id':'a'*24,'settings':{'custom_rules':[{'id':'1'*24,'action':'block','value':'*.old.example','group':'old','note':'before'}],'custom_rule_groups':{'allow':[],'block':[{'name':'old','comment':'group note'}]},'privacy':{'blocklists':['oisd_small'],'services':[]},'security':{'rebinding_protection':{'enabled':False}}}}
    calls=[]
    async def call(h,sub,method,path,data=None):
        assert sub=='user-a';calls.append((method,path,data));s=p['settings']
        if method=='GET':
            if path=='/services':return {'services':[{'id':'reddit'}]}
            if path=='/blocklists':return [{'blocklist_id':x,'entries':100} for x in ('oisd_small','hagezi_multi_light')]
            return copy.deepcopy(p)
        assert path.startswith('/profiles/profileA/')
        if path.endswith('/custom_rules/batch'):
            created=[]
            for v in data['values']:
                r={'id':format(len(s['custom_rules'])+10,'024x'),'value':v,'action':data['action'],'group':'','note':''};s['custom_rules'].append(r);created.append(copy.deepcopy(r))
            return {'created':created,'skipped':[]}
        if '/custom_rules/' in path:
            ident=path.split('/')[-1]
            if method=='DELETE':s['custom_rules']=[r for r in s['custom_rules'] if r['id']!=ident]
            else:next(r for r in s['custom_rules'] if r['id']==ident).update(data)
        elif path.endswith('/custom_rule_groups'):
            op=data['updates'][0];name=op['path'][1:].replace('~1','/').replace('~0','~');mode=op['action']
            s['custom_rule_groups'][mode]=[g for g in s['custom_rule_groups'][mode] if g['name']!=name]
            if op['operation']=='remove':
                for r in s['custom_rules']:
                    if r['action']==mode and r['group']==name:r['group']=''
            else:s['custom_rule_groups'][mode].append({'name':name,'comment':op['value']})
        elif path.endswith('/rebinding'):s['security']['rebinding_protection']['enabled']=data['enabled']
        else:
            field='blocklists' if path.endswith('/blocklists') else 'services';values=data['blocklist_ids' if field=='blocklists' else 'service_ids']
            s['privacy'][field]=sorted(set(s['privacy'][field])|set(values) if method=='POST' else set(s['privacy'][field])-set(values))
    async def sleep(_):pass
    monkeypatch.setattr(a,'call',call);monkeypatch.setattr(f.asyncio,'sleep',sleep)
    return p,calls

def target(p):
    doc=f.snapshot(p);doc.update({'blocklists':['hagezi_multi_light'],'services':['reddit'],'rebinding':True,'groups':{'allow':[{'name':'new/~','note':'new note'}],'block':[]},'rules':[{'action':'allow','value':'*.new.example','group':'new/~','note':'restored'}]});return doc

def preview(client,doc):return client.post('/filters/config/preview',data={'csrf_token':'csrf','raw':json.dumps(doc)})
def token(r):return re.search(r'name="token" value="([^"]+)"',r.text)[1]
def apply(client,t):return client.post('/filters/config/apply',data={'csrf_token':'csrf','token':t,'confirm':'replace'},follow_redirects=False)

def test_preview_no_writes_apply_exact_restore_no_routing_change(client,config_backend):
    p,calls=config_backend;doc=target(p);original=copy.deepcopy(p)
    r=preview(client,doc);assert r.status_code==200 and p==original and all(x[0]=='GET' for x in calls)
    t=token(r);assert apply(client,t).status_code==303
    assert f.snapshot(p)==doc
    row=a.mapping(m.db,'user-a');assert row['routing']==0 and row['revision']==1 and row['state']=='ready'
    assert apply(client,t).status_code==409
    exported=client.get('/filters/config.json?profile=other');assert exported.status_code==200 and exported.json()==doc
    assert 'profileA' not in exported.text and exported.headers['cache-control']=='no-store'

def test_stale_preview_checks_content_revision_and_route(client,config_backend):
    p,calls=config_backend
    for kind in ('content','revision','route'):
        t=token(preview(client,target(p)))
        if kind=='content':p['settings']['custom_rules'][0]['note']='concurrent'
        elif kind=='revision':
            with m.db() as c:c.execute('UPDATE moddns_mapping SET revision=revision+1')
        else:
            with m.db() as c:c.execute('UPDATE moddns_mapping SET routing=1')
        assert apply(client,t).status_code==409
    assert all(x[0]=='GET' for x in calls)

def test_tamper_expiry_session_and_owner(client,config_backend):
    p,calls=config_backend;t=token(preview(client,target(p)));cipher=f.signer()
    assert apply(client,t[:-3]+'xyz').status_code==409
    expired=cipher.encrypt_at_time(cipher.decrypt(t.encode()),int(time.time())-601).decode()
    assert apply(client,expired).status_code==409
    signin(client) # New session for same owner
    assert apply(client,t).status_code==409
    signin(client,'user-b');assert apply(client,t).status_code==409
    assert client.get('/filters/config.json').status_code==404

def test_disabled_and_csrf_no_write(client,config_backend):
    p,calls=config_backend;t=token(preview(client,target(p)))
    assert client.post('/filters/config/apply',data={'csrf_token':'bad','token':t,'confirm':'replace'}).status_code==403
    with m.db() as c:c.execute("UPDATE account_settings SET enabled=0 WHERE sub='user-a'")
    assert apply(client,t).status_code==403
    assert all(x[0]=='GET' for x in calls)

@pytest.mark.parametrize('mutation',['unknown','logs','list','conflict','oversize','semantics','bool'])
def test_import_validation_no_changes(client,config_backend,mutation):
    p,calls=config_backend;doc=target(p)
    if mutation=='unknown':doc['profile_id']='evil'
    if mutation=='logs':doc['logs']={'enabled':True}
    if mutation=='list':doc['blocklists']=['unknown']
    if mutation=='conflict':doc['rules'].append({**doc['rules'][0],'action':'block'})
    if mutation=='oversize':doc['rules']*=1001
    if mutation=='semantics':doc['semantics']['default_rule']='block'
    if mutation=='bool':doc['rebinding']='false'
    assert preview(client,doc).status_code==422
    assert all(x[0]=='GET' for x in calls)

def test_partial_failure_stays_closed_and_preserves_route(client,config_backend,monkeypatch):
    p,calls=config_backend;t=token(preview(client,target(p)));original=a.call
    async def failed(h,sub,method,path,data=None):
        if method=='PATCH':raise HTTPException(503,'failure')
        return await original(h,sub,method,path,data)
    monkeypatch.setattr(a,'call',failed)
    assert apply(client,t).status_code==503
    row=a.mapping(m.db,'user-a');assert row['state']=='error' and row['routing']==0
    assert apply(client,t).status_code==409

def test_noop_export_and_duplicate_keys(client,config_backend):
    p,calls=config_backend;r=preview(client,f.snapshot(p));assert r.status_code==200 and 'name="token"' not in r.text
    raw=json.dumps(target(p)).replace('"format":','"format":"duplicate","format":',1)
    assert client.post('/filters/config/preview',data={'csrf_token':'csrf','raw':raw}).status_code==422
    assert a.mapping(m.db,'user-a')['revision']==0


def test_group_name_byte_limit_before_writes(client,config_backend):
    p,calls=config_backend;doc=target(p);doc['groups']['allow'][0]['name']='名'*22
    assert preview(client,doc).status_code==422
    assert all(x[0]=='GET' for x in calls)
