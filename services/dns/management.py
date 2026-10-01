"""Single-process management state. No raw DNS names or bearer tokens are stored."""
import asyncio
import os
import json
import threading
import time
from collections import Counter

LOCK = threading.RLock()
pending = Counter()
account_buckets = {}
health = {}
METRICS = ('received','admitted','forwarded','success','failed','limited','disabled','invalid')
BLOCKLIST_IDS = ('hagezi_multi_pro','hagezi_tif_medium')
FLUSH_SECONDS = 5

def migrate(db):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied INTEGER NOT NULL)')
        if not c.execute('SELECT 1 FROM schema_migrations WHERE version=1').fetchone():
            c.execute('''CREATE TABLE account_settings(sub TEXT PRIMARY KEY REFERENCES users(sub), enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), qps INTEGER NOT NULL DEFAULT 60 CHECK(qps BETWEEN 1 AND 1000), burst INTEGER NOT NULL DEFAULT 60 CHECK(burst BETWEEN 1 AND 2000), is_admin INTEGER NOT NULL DEFAULT 0 CHECK(is_admin IN (0,1)))''')
            c.execute('INSERT INTO account_settings(sub) SELECT sub FROM users')
            c.execute('''CREATE TRIGGER user_settings AFTER INSERT ON users BEGIN INSERT OR IGNORE INTO account_settings(sub) VALUES(new.sub); END''')
            c.execute('CREATE TABLE audit(id INTEGER PRIMARY KEY, timestamp INTEGER NOT NULL, actor TEXT NOT NULL, target TEXT NOT NULL, action TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL, result TEXT NOT NULL)')
            c.execute('CREATE TABLE usage(window INTEGER NOT NULL, sub TEXT NOT NULL, metric TEXT NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(window,sub,metric))')
            c.execute('CREATE TABLE node_events(id INTEGER PRIMARY KEY,timestamp INTEGER NOT NULL,node TEXT NOT NULL,event TEXT NOT NULL)')
            c.execute('INSERT INTO schema_migrations VALUES(1,?)',(int(time.time()),))
        if not c.execute('SELECT 1 FROM schema_migrations WHERE version=3').fetchone():
            c.execute('CREATE INDEX IF NOT EXISTS usage_subject_window ON usage(sub,window)')
            c.execute('INSERT INTO schema_migrations VALUES(3,?)',(int(time.time()),))

def count(sub, metric):
    with LOCK:
        pending[(int(time.time())//60*60,sub,metric)] += 1

def count_filtered(sub,blocked,blocklists=()):
    """Matched numerator/denominator in the same minute; legacy data is not backfilled."""
    with LOCK:
        window=int(time.time())//60*60
        pending[(window,sub,'filter_success')] += 1
        if blocked:
            pending[(window,sub,'filter_blocked')] += 1
            pending[(window,sub,'blocked')] += 1
            ids=tuple(sorted(set(blocklists).intersection(BLOCKLIST_IDS)))
            if ids:
                pending[(window,sub,'blocklist_attributed')] += 1
                for blocklist_id in ids:
                    pending[(window,sub,'blocklist_hit:'+blocklist_id)] += 1
                if len(ids)==1:
                    pending[(window,sub,'blocklist_only:'+ids[0])] += 1
                else:
                    pending[(window,sub,'blocklist_overlap')] += 1

def flush(db):
    with LOCK:
        if not pending:return
        with db() as c:
            c.executemany('INSERT INTO usage VALUES(?,?,?,?) ON CONFLICT(window,sub,metric) DO UPDATE SET count=count+excluded.count', [(*k,v) for k,v in pending.items()])
        pending.clear()

def allow(sub, rate, capacity):
    now=time.monotonic()
    with LOCK:
        tokens,ts,oldrate,oldcap=account_buckets.get(sub,(float(capacity),now,rate,capacity))
        tokens=min(capacity,oldcap,tokens+max(0,now-ts)*oldrate)
        passed=tokens>=1
        account_buckets[sub]=(tokens-1 if passed else tokens,now,rate,capacity)
        return passed

def resize(sub,rate,capacity):
    with LOCK:
        if sub in account_buckets:
            tokens,ts,oldrate,oldcap=account_buckets[sub]
            account_buckets[sub]=(min(capacity,oldcap,tokens+max(0,time.monotonic()-ts)*oldrate),time.monotonic(),rate,capacity)

def totals(db,sub=None):
    flush(db)
    with db() as c:
        rows=c.execute('SELECT metric,SUM(count) n FROM usage WHERE window>=?'+(' AND sub=?' if sub else '')+' GROUP BY metric', (int(time.time())-86400,sub) if sub else (int(time.time())-86400,))
        return {r['metric']:r['n'] for r in rows}

def audit(c,actor,target,action,before,after,result='ok'):
    c.execute('INSERT INTO audit(timestamp,actor,target,action,before_json,after_json,result) VALUES(?,?,?,?,?,?,?)',(int(time.time()),actor,target,action,json.dumps(before),json.dumps(after),result))

async def monitor(app,db,upstreams):
    import dns.message
    last_probe=0
    while True:
        await asyncio.sleep(FLUSH_SECONDS)
        if time.monotonic()-last_probe<30:continue
        last_probe=time.monotonic()
        targets=[(ep,app.state.http,ep) for ep in upstreams]
        if os.getenv('MODDNS_HEALTH_PROFILE') and os.getenv('MODDNS_DOH'):
            targets.append((os.environ['MODDNS_DOH']+'/dns-query/'+os.environ['MODDNS_HEALTH_PROFILE'],app.state.moddns_http,'modDNS 主节点'))
        for endpoint,client,label in targets:
            start=time.monotonic();error='';rcode=None
            try:
                q=dns.message.make_query('example.com','A')
                r=await client.post(endpoint,content=q.to_wire(),headers={'Content-Type':'application/dns-message','Accept':'application/dns-message'})
                if r.status_code!=200:raise ValueError('http_'+str(r.status_code))
                answer=dns.message.from_wire(r.content)
                if not q.is_response(answer):raise ValueError('invalid_response')
                rcode=answer.rcode()
                if rcode==2:raise ValueError('servfail')
            except Exception as exc:error=type(exc).__name__ if not isinstance(exc,ValueError) else str(exc)
            health[label]={'checked':int(time.time()),'latency_ms':round((time.monotonic()-start)*1000),'error':error,'rcode':rcode,'dns_ok':not error}
        with db() as c:
            c.execute('DELETE FROM audit WHERE timestamp<?',(int(time.time())-90*86400,))
            c.execute('DELETE FROM node_events WHERE timestamp<?',(int(time.time())-7*86400,))


async def flush_loop(app,db):
    while True:
        await asyncio.sleep(FLUSH_SECONDS)
        try:
            flush(db)
            app.state.last_flush=time.monotonic()
            app.state.stats_error=False
        except Exception:
            app.state.stats_error=True
