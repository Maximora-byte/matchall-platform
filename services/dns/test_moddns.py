import asyncio,time
import httpx,dns.message
import app as m
import moddns_adapter as a
from test_app import client,signin,create,query

def test_mapped_queries_do_not_fallback(client,monkeypatch):
 signin(client);_,token=create(client)
 monkeypatch.setattr(a,'DOH','https://proxy.test')
 with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,account_id,profile_id,state,routing,updated) VALUES('user-a','account-a','profile-a','ready',1,?)",(int(time.time()),))
 seen=[]
 def upstream(req):seen.append(str(req.url));return httpx.Response(503)
 old=m.app.state.moddns_http
 m.app.state.moddns_http=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
 try:
  r=client.post('/dns-query/'+token,content=query(),headers={'Content-Type':'application/dns-message'})
  assert dns.message.from_wire(r.content).rcode()==2
  assert seen==['https://proxy.test/dns-query/profile-a']
  with m.db() as c:c.execute("UPDATE moddns_mapping SET state='error'")
  assert client.post('/dns-query/'+token,content=query(),headers={'Content-Type':'application/dns-message'}).status_code==503
  assert len(seen)==1
 finally:m.app.state.moddns_http=old

def test_block_marker_not_rcode_and_private_header_not_forwarded(client,monkeypatch):
 signin(client);_,token=create(client);monkeypatch.setattr(a,'DOH','https://proxy.test')
 with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,account_id,profile_id,state,routing,updated) VALUES('user-a','account-a','profile-a','ready',1,?)",(int(time.time()),))
 def upstream(req):
  response=dns.message.make_response(dns.message.from_wire(req.content))
  return httpx.Response(200,content=response.to_wire(),headers={'Content-Type':'application/dns-message','X-MatchAll-Blocked':'1','X-MatchAll-Blocklists':'hagezi_multi_pro,hagezi_tif_medium'})
 old=m.app.state.moddns_http;m.app.state.moddns_http=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
 try:
  r=client.post('/dns-query/'+token,content=query(),headers={'Content-Type':'application/dns-message'})
  assert r.status_code==200 and 'X-MatchAll-Blocked' not in r.headers
  assert 'X-MatchAll-Blocklists' not in r.headers
  assert client.get('/api/usage').json()['last_24h']['blocked']>=1
  stats=client.get('/api/statistics').json()
  assert stats['blocklist_attributed']>=1 and stats['blocklist_overlap']>=1
 finally:m.app.state.moddns_http=old

def test_filter_state_remains_error_on_ambiguous_remote_write(client,monkeypatch,tmp_path):
 key=tmp_path/"internal.key";key.write_text("test-only-key");monkeypatch.setenv("MODDNS_KEY_FILE",str(key))
 signin(client);create(client)
 with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,account_id,profile_id,state,routing,updated) VALUES('user-a','account-a','profile-a','ready',1,?)",(int(time.time()),))
 monkeypatch.setattr(a,'API','http://private-api')
 old=m.app.state.http;m.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(503)))
 try:
  assert client.post('/filters',data={'csrf_token':'csrf','action':'block','value':'example.com'}).status_code==503
  assert a.mapping(m.db,'user-a')['state']=='error'
 finally:m.app.state.http=old

def test_reconciliation_keeps_route_closed_until_proxy_cache_expires(client,monkeypatch):
 signin(client);create(client)
 with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,account_id,profile_id,state,routing,revision,updated) VALUES('user-a',?,'profileA','error',1,1,?)",('a'*24,int(time.time())))
 monkeypatch.setattr(a,'API','http://private-api');monkeypatch.setattr(a,'DOH','https://private-proxy')
 async def remote(h,sub,method,path,data=None):
  if path=='/account':return {'account_id':'a'*24,'profile_id':'profileA'}
  return {'account_id':'a'*24,'settings':{'privacy':{'blocklists':[]}}}
 async def wait(seconds):
  assert seconds>=1
  assert a.mapping(m.db,'user-a')['state']=='pending'
 monkeypatch.setattr(a,'call',remote);monkeypatch.setattr(a.asyncio,'sleep',wait)
 asyncio.run(a.provision(m.db,None,'user-a'))
 assert a.mapping(m.db,'user-a')['state']=='ready'

def test_optin_does_not_override_active_policy_write(client):
 signin(client);create(client)
 with m.db() as c:c.execute("INSERT INTO moddns_mapping(sub,state,routing,updated) VALUES('user-a','updating',1,?)",(int(time.time()),))
 r=client.post('/filters/enable',data={'csrf_token':'csrf'},follow_redirects=False)
 assert r.status_code==409
 assert a.mapping(m.db,'user-a')['state']=='updating'

def test_default_lists_only_initial_profile(client,monkeypatch):
 signin(client);create(client)
 monkeypatch.setattr(a,'API','http://private-api');monkeypatch.setattr(a,'DOH','https://private-proxy')
 writes=[]
 async def remote(h,sub,method,path,data=None):
  if method in ('POST','DELETE') and path.endswith('/blocklists'):writes.append((method,data['blocklist_ids']));return {}
  if path=='/account':return {'account_id':'a'*24,'profile_id':'profileA'}
  return {'account_id':'a'*24,'settings':{'privacy':{'blocklists':['oisd_small']}}}
 async def wait(seconds):pass
 monkeypatch.setattr(a,'call',remote);monkeypatch.setattr(a.asyncio,'sleep',wait)
 asyncio.run(a.provision(m.db,None,'user-a'))
 assert writes==[('POST',['hagezi_multi_pro','hagezi_tif_medium']),('DELETE',['oisd_small'])]
 assert a.mapping(m.db,'user-a')['routing']==0
 with m.db() as c:c.execute("UPDATE moddns_mapping SET personalized=1,revision=1")
 writes.clear();asyncio.run(a.provision(m.db,None,'user-a'))
 assert writes==[]
