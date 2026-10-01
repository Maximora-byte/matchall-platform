"""Temporary-account transport test; no existing account changes."""
import subprocess, json, os, tempfile, time, secrets
container='matchall-dns-dns-portal-1'
def probe(env):
 if os.environ.get('REMOTE_PROBE'):
  host=os.environ.get('REMOTE_PROBE_HOST','osaka')
  addr=os.environ.get('REMOTE_PROBE_ADDR','64.110.101.75:853')
  command='umask 077; cat > /tmp/matchall-transport-smoke-token; TOKEN_FILE=/tmp/matchall-transport-smoke-token PROBE_ADDR='+subprocess.list2cmdline([addr])+' EXPECT_RCODE='+env['EXPECT_RCODE']+' /tmp/matchall-dns-probe; result=$?; rm -f /tmp/matchall-transport-smoke-token; exit $result'
  subprocess.run(['ssh',host,command],input=open(env['TOKEN_FILE']).read(),text=True,check=True)
 else:
  subprocess.run(['/tmp/matchall-dns-probe'],env=env,check=True)
def run(code):
 p=subprocess.run(['docker','exec','-i',container,'python','-c',code],capture_output=True,text=True)
 if p.returncode:raise RuntimeError('fixture operation failed (inspect locally; output withheld)')
 return p.stdout.strip()
sub='transport-smoke-'+secrets.token_hex(8)
state=run("import app as m,json,hashlib\nwith m.db() as c:\n print(hashlib.sha256(json.dumps({t:[tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY 1')] for t in ['users','devices','account_settings','moddns_mapping']},sort_keys=True).encode()).hexdigest())")
fd,path=tempfile.mkstemp(prefix='dns-transport-token-',dir='/tmp');os.close(fd)
try:
 token=run("import app as m,time\nsub="+repr(sub)+"\nwith m.db() as c:c.execute('INSERT INTO users VALUES(?,?,?)',(sub,'transport acceptance',int(time.time())))\nd=m.account_token(sub);print(m.cipher().decrypt(d['token_enc'].encode()).decode())")
 page=run("import app as m,httpx,secrets,time,base64\nsub="+repr(sub)+"\ncookie=secrets.token_urlsafe(32)\nwith m.db() as c:c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(m.digest(cookie),sub,'csrf',int(time.time())+120))\nr=httpx.get(m.BASE+'/',cookies={'__Host-dns_session':cookie},timeout=15);assert r.status_code==200\nd=m.account_token(sub);tok=m.cipher().decrypt(d['token_enc'].encode()).decode();host=base64.b32encode(bytes.fromhex(tok)).decode().rstrip('=').lower()+'.tls.dns.maximoraverse.org'\nassert host in r.text and 'quic://'+host+':853' in r.text\nprint(r.text.replace(tok,'0'*64).replace(host,'a'*52+'.tls.dns.maximoraverse.org'))")
 with open('/tmp/dns-transports-account-fixture.html','w') as f:f.write(page)
 with open(path,'w') as f:f.write(token)
 env=dict(os.environ,TOKEN_FILE=path,EXPECT_RCODE='NOERROR')
 probe(env)
 run("import app as m\nwith m.db() as c:c.execute('UPDATE account_settings SET enabled=0 WHERE sub=?',("+repr(sub)+",))")
 env['EXPECT_RCODE']='REFUSED';probe(env)
 run("import app as m\nwith m.db() as c:c.execute('UPDATE account_settings SET enabled=1 WHERE sub=?',("+repr(sub)+",))\nm.account_token("+repr(sub)+",rotate=True)")
 probe(env)
 print('PASS transport resolution, account disable, token rotation')
finally:
 os.unlink(path)
 run("import app as m\nwith m.db() as c:c.execute('UPDATE account_settings SET enabled=0 WHERE sub=?',("+repr(sub)+",))")
 time.sleep(6)
 run("import app as m\nwith m.db() as c:\n for t in ['query_log_settings','usage','devices','sessions','account_settings','users']:c.execute('DELETE FROM '+t+' WHERE sub=?',("+repr(sub)+",))")
 after=run("import app as m,json,hashlib\nwith m.db() as c:\n print(hashlib.sha256(json.dumps({t:[tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY 1')] for t in ['users','devices','account_settings','moddns_mapping']},sort_keys=True).encode()).hexdigest())")
 assert state==after,'existing account state changed'
 print('PASS cleanup and existing-account invariants')
