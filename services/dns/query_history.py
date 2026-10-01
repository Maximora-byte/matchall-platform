"""Opt-in persistent query history.

Only the DNS name, type, outcome, rcode, latency and route are stored. Client
addresses, bearer tokens and DNS answer bodies are deliberately excluded.
"""
import asyncio,time,threading
from datetime import datetime,timezone
from fastapi import Request,Form,Query,HTTPException
from fastapi.responses import RedirectResponse
import dns.rdatatype,dns.rcode
from advanced_filters import rule_value
import moddns_adapter as adapter
import service_catalog

LOCK=threading.RLock()
preferences={}
pending=[]
db_factory=None
started=0
LABELS={'response':'正常响应','blocked':'已确认过滤拦截','nxdomain':'域名不存在（未确认拦截）','failed':'上游失败／超时','policy_unavailable':'过滤配置未就绪','dns_error':'其他 DNS 错误'}
RETENTIONS=(0,3600,86400)
PERIODS={'24h':86400,'7d':7*86400,'30d':30*86400,'all':None}

def initialize(db):
    global started,db_factory
    with LOCK:
        db_factory=db;preferences.clear();pending.clear();started=int(time.time())
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM schema_migrations WHERE version=4').fetchone():
                c.execute('CREATE TABLE query_log_settings(sub TEXT PRIMARY KEY REFERENCES users(sub),enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),retention INTEGER NOT NULL DEFAULT 3600 CHECK(retention IN (3600,86400)))')
                c.execute('INSERT INTO schema_migrations VALUES(4,?)',(int(time.time()),))
            if not c.execute('SELECT 1 FROM schema_migrations WHERE version=5').fetchone():
                c.execute('ALTER TABLE query_log_settings RENAME TO query_log_settings_v4')
                c.execute('CREATE TABLE query_log_settings(sub TEXT PRIMARY KEY REFERENCES users(sub),enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),retention INTEGER NOT NULL DEFAULT 3600 CHECK(retention IN (0,3600,86400)))')
                c.execute('INSERT INTO query_log_settings SELECT sub,enabled,retention FROM query_log_settings_v4')
                c.execute('DROP TABLE query_log_settings_v4')
                c.execute('''CREATE TABLE query_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    sub TEXT NOT NULL REFERENCES users(sub),
                    domain TEXT NOT NULL,
                    qtype TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    rcode TEXT,
                    latency_ms REAL NOT NULL,
                    route TEXT NOT NULL
                )''')
                c.execute('CREATE INDEX query_history_owner_id ON query_history(sub,id DESC)')
                c.execute('CREATE INDEX query_history_owner_time ON query_history(sub,timestamp)')
                c.execute('CREATE INDEX query_history_owner_domain ON query_history(sub,domain)')
                c.execute('CREATE INDEX query_history_owner_outcome_domain ON query_history(sub,outcome,domain)')
                c.execute('INSERT INTO schema_migrations VALUES(5,?)',(int(time.time()),))
            for r in c.execute('SELECT * FROM query_log_settings'):
                preferences[r['sub']]={'enabled':bool(r['enabled']),'retention':r['retention'],'epoch':0}

def _flush_locked(db=None):
    if not pending:return
    factory=db or db_factory
    if factory is None:return
    batch=list(pending);pending.clear()
    try:
        with factory() as c:
            c.executemany('INSERT INTO query_history(timestamp,sub,domain,qtype,outcome,rcode,latency_ms,route) VALUES(?,?,?,?,?,?,?,?)',batch)
    except Exception:
        pending[:0]=batch
        raise

def flush(db=None):
    with LOCK:_flush_locked(db)

def _clear_locked(sub,db=None):
    pending[:]=[row for row in pending if row[1]!=sub]
    factory=db or db_factory
    if factory is not None:
        with factory() as c:c.execute('DELETE FROM query_history WHERE sub=?',(sub,))

def _prune_locked(sub,now,db=None):
    pref=preferences.get(sub)
    if not pref or pref['retention']==0:return
    factory=db or db_factory
    if factory is not None:
        with factory() as c:c.execute('DELETE FROM query_history WHERE sub=? AND timestamp<?',(sub,now-pref['retention']))

def begin(sub):
    with LOCK:
        pref=preferences.get(sub)
        return (sub,pref['epoch'],time.monotonic()) if pref and pref['enabled'] else None

def record(ticket,q,outcome,rcode,route):
    if ticket is None:return
    sub,epoch,begin_at=ticket
    with LOCK:
        pref=preferences.get(sub)
        if not pref or not pref['enabled'] or pref['epoch']!=epoch:return
        domain=q.question[0].name.to_text(omit_final_dot=True).lower()[:253]
        pending.append((time.time(),sub,domain,dns.rdatatype.to_text(q.question[0].rdtype),outcome,
                        dns.rcode.to_text(rcode) if rcode is not None else None,
                        round((time.monotonic()-begin_at)*1000,2),route))

def _where(sub,domain='',outcome='',before=0,since=0):
    clauses=['sub=?'];args=[sub]
    if domain:
        escaped=domain.lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        clauses.append("domain LIKE ? ESCAPE '\\'");args.append('%'+escaped+'%')
    if outcome:clauses.append('outcome=?');args.append(outcome)
    if before:clauses.append('id<?');args.append(before)
    if since:clauses.append('timestamp>=?');args.append(since)
    return ' AND '.join(clauses),args

def _chart_points(series,width=760,height=180):
    maximum=max((item['count'] for item in series),default=0) or 1
    length=max(len(series)-1,1)
    return [{'x':round(i*width/length,1),'y':round(height-item['count']*height/maximum,1),
             'blocked_y':round(height-item['blocked']*height/maximum,1),**item}
            for i,item in enumerate(series)]

def report(sub,domain='',outcome='',before=0,period='all'):
    with LOCK:
        _flush_locked();_prune_locked(sub,time.time())
        pref=preferences.get(sub,{'enabled':False,'retention':3600})
        if period not in PERIODS:raise HTTPException(422,'无效时间范围')
        now=time.time();span=PERIODS[period];since=now-span if span else 0
        where,args=_where(sub,domain,outcome,before,since)
        scope_where,scope_args=_where(sub,since=since)
        bucket=3600 if period=='24h' else 86400
        if period=='all':
            with db_factory() as c:first=c.execute('SELECT MIN(timestamp) FROM query_history WHERE sub=?',(sub,)).fetchone()[0]
            bucket=max(86400,int(max(now-(first or now),86400)/30))
        with db_factory() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM query_history WHERE '+where+' ORDER BY id DESC LIMIT 51',args)]
            retained_count=c.execute('SELECT COUNT(*) FROM query_history WHERE sub=?',(sub,)).fetchone()[0]
            count=c.execute('SELECT COUNT(*) FROM query_history WHERE '+scope_where,scope_args).fetchone()[0]
            tops=[dict(r) for r in c.execute('SELECT domain,COUNT(*) count FROM query_history WHERE '+scope_where+' GROUP BY domain ORDER BY count DESC,domain LIMIT 10',scope_args)]
            blocked=[dict(r) for r in c.execute("SELECT domain,COUNT(*) count FROM query_history WHERE "+scope_where+" AND outcome='blocked' GROUP BY domain ORDER BY count DESC,domain LIMIT 10",scope_args)]
            outcomes={r['outcome']:r['count'] for r in c.execute('SELECT outcome,COUNT(*) count FROM query_history WHERE '+scope_where+' GROUP BY outcome',scope_args)}
            latency=c.execute('SELECT AVG(latency_ms),MAX(latency_ms) FROM query_history WHERE '+scope_where,scope_args).fetchone()
            trend=[dict(r) for r in c.execute('SELECT CAST(timestamp/? AS INTEGER)*? bucket,COUNT(*) count,SUM(outcome=\'blocked\') blocked FROM query_history WHERE '+scope_where+' GROUP BY bucket ORDER BY bucket',(bucket,bucket,*scope_args))]
            domain_stats=[tuple(r) for r in c.execute('SELECT domain,COUNT(*) count,SUM(outcome=\'blocked\') blocked FROM query_history WHERE '+scope_where+' GROUP BY domain',scope_args)]
        more=len(rows)>50;rows=rows[:50]
        for r in rows:
            r['time']=datetime.fromtimestamp(r['timestamp'],timezone.utc).strftime('%m-%d %H:%M:%S')
            r['type']=r.pop('qtype');r['label']=LABELS.get(r['outcome'],r['outcome']);r.pop('sub',None)
        trend=[{'time':datetime.fromtimestamp(r['bucket'],timezone.utc).strftime('%m-%d %H:%M'),'count':r['count'],'blocked':r['blocked']} for r in trend]
        blocked_count=outcomes.get('blocked',0)
        return {'enabled':pref['enabled'],'retention':pref['retention'],'started':started,'count':count,'retained_count':retained_count,'rows':rows,
                'next_before':rows[-1]['id'] if more else None,'top_domains':tops,'top_blocked':blocked,
                'outcomes':[{'id':key,'label':LABELS[key],'count':outcomes.get(key,0)} for key in LABELS],
                'period':period,'periods':PERIODS,'blocked_count':blocked_count,
                'blocked_rate':round(blocked_count*100/count,1) if count else 0,
                'avg_latency':round(latency[0],1) if latency and latency[0] is not None else 0,
                'max_latency':round(latency[1],1) if latency and latency[1] is not None else 0,
                'trend':_chart_points(trend),'trend_max':max((r['count'] for r in trend),default=0),
                'classification':service_catalog.aggregate(domain_stats),
                'top_max':max((r['count'] for r in tops),default=1),'blocked_max':max((r['count'] for r in blocked),default=1),
                'per_account_limit':None,'global_limit':None}

async def cleanup(db):
    while True:
        await asyncio.sleep(5)
        with LOCK:
            try:
                _flush_locked(db)
                with db() as c:existing={r[0] for r in c.execute('SELECT sub FROM users')}
                for sub in list(preferences):
                    if sub not in existing:preferences.pop(sub,None)
                now=time.time()
                for sub in list(preferences):_prune_locked(sub,now,db)
            except Exception:
                pass

def install(app,db,require_user,csrf,templates,mg):
    def params(outcome):
        if outcome and outcome not in LABELS:raise HTTPException(422,'无效结果类型')

    @app.get('/api/queries')
    def api(request:Request,domain:str=Query('',max_length=253),outcome:str='',before:int=Query(0,ge=0),period:str='24h'):
        u=require_user(request);params(outcome);return report(u['sub'],domain,outcome,before,period)

    @app.get('/queries')
    def page(request:Request,domain:str=Query('',max_length=253),outcome:str='',before:int=Query(0,ge=0),period:str='24h'):
        u=require_user(request);params(outcome);data=report(u['sub'],domain,outcome,before,period);mapping=adapter.mapping(db,u['sub'])
        for r in data['rows']:
            try:rule_value(r['domain']);r['can_rule']=bool(mapping and mapping['state']=='ready' and u['enabled'])
            except HTTPException:r['can_rule']=False
        return templates.TemplateResponse(request=request,name='queries.html',context={'user':u,'history':data,'labels':LABELS,'domain':domain,'outcome':outcome,'period':period,'mapping':mapping})

    @app.post('/queries/settings')
    def settings(request:Request,csrf_token:str=Form(...),action:str=Form(...),retention:int=Form(3600),consent:str=Form('')):
        u=require_user(request);csrf(request,u,csrf_token)
        if action not in ('enable','disable','clear') or retention not in RETENTIONS:raise HTTPException(422,'无效日志设置')
        if action=='enable' and consent!='record_domains':raise HTTPException(422,'请确认记录查询域名')
        with LOCK:
            old=preferences.get(u['sub'],{'enabled':False,'retention':3600,'epoch':0})
            new={**old,'epoch':old['epoch']+1}
            if action=='enable':new.update(enabled=True,retention=retention)
            if action=='disable':new['enabled']=False
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                state=c.execute('SELECT enabled FROM account_settings WHERE sub=?',(u['sub'],)).fetchone()
                if action=='enable' and (not state or not state[0]):raise HTTPException(403,'账号已停用')
                c.execute('INSERT INTO query_log_settings VALUES(?,?,?) ON CONFLICT(sub) DO UPDATE SET enabled=excluded.enabled,retention=excluded.retention',(u['sub'],int(new['enabled']),new['retention']))
                mg.audit(c,u['sub'],u['sub'],'query_logs.'+action,{k:old[k] for k in ('enabled','retention')},{k:new[k] for k in ('enabled','retention')})
            preferences[u['sub']]=new
            if action in ('disable','clear'):_clear_locked(u['sub'],db)
            else:_prune_locked(u['sub'],time.time(),db)
        return RedirectResponse('/queries',303)

    @app.post('/queries/rule')
    async def from_record(request:Request,csrf_token:str=Form(...),record_id:int=Form(...),action:str=Form(...)):
        u=require_user(request);csrf(request,u,csrf_token)
        if action not in ('allow','block'):raise HTTPException(422,'无效操作')
        with LOCK:
            _flush_locked(db);_prune_locked(u['sub'],time.time(),db)
            with db() as c:row=c.execute('SELECT domain FROM query_history WHERE id=? AND sub=?',(record_id,u['sub'])).fetchone()
            if not row:raise HTTPException(404,'记录已清空、过期或不属于当前账号')
            value=rule_value(row['domain'])
        mapping=adapter.mapping(db,u['sub'])
        if not u['enabled']:raise HTTPException(403,'账号已停用')
        if not mapping or mapping['state']!='ready':raise HTTPException(409,'请先准备过滤配置并等待同步完成')
        return templates.TemplateResponse(request=request,name='query_rule.html',context={'user':u,'value':value,'action':action,'mapping':mapping})
