"""Opt-in modDNS adapter; no account is switched by installation or login."""
import os
import re
import time
import asyncio
from pathlib import Path
import httpx
from fastapi import Request,Form,HTTPException
from fastapi.responses import RedirectResponse

API=os.getenv('MODDNS_API','').rstrip('/')
DOH=os.getenv('MODDNS_DOH','').rstrip('/')
account_locks={}

def account_lock(sub):
    return account_locks.setdefault(sub,asyncio.Lock())

def migrate(db):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM schema_migrations WHERE version=2').fetchone():
            c.execute('''CREATE TABLE moddns_mapping(sub TEXT PRIMARY KEY, account_id TEXT UNIQUE, profile_id TEXT UNIQUE, state TEXT NOT NULL DEFAULT 'pending', routing INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0, personalized INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL, error TEXT NOT NULL DEFAULT '')''')
            c.execute('INSERT INTO schema_migrations VALUES(2,?)',(int(time.time()),))

def mapping(db,sub):
    with db() as c:
        r=c.execute('SELECT * FROM moddns_mapping WHERE sub=?',(sub,)).fetchone()
        return dict(r) if r else None

def headers(sub):
    return {'Authorization':'Bearer '+Path(os.environ['MODDNS_KEY_FILE']).read_text().strip(),'X-MatchAll-Subject':sub,'Accept':'application/json'}

async def call(h,sub,method,path,data=None):
    if not API:raise HTTPException(503,'过滤服务尚未开通')
    try:
        r=await h.request(method,API+'/internal/matchall'+path,headers=headers(sub),json=data,timeout=10)
    except (httpx.HTTPError,OSError):raise HTTPException(503,'过滤服务暂不可用') from None
    if not r.is_success:raise HTTPException(503 if r.status_code>=500 else 400,'过滤操作未完成，请检查规则或稍后重试')
    try:return r.json()
    except ValueError:return None

async def provision(db,h,sub,*,mark_ready=True):
    """Explicit opt-in only. Retries reconcile the remote immutable mapping."""
    if not API or not DOH:raise RuntimeError('modDNS endpoints not configured')
    previous=mapping(db,sub)
    if previous and previous['state'] in ('deleted','deleting'):raise HTTPException(410,'DNS 过滤账号已删除或正在删除')
    initial=not previous or (not previous['routing'] and previous['revision']==0 and not previous['personalized'])
    with db() as c:
        if not c.execute('SELECT 1 FROM users WHERE sub=?',(sub,)).fetchone():raise ValueError('unknown subject')
        if c.execute("INSERT INTO moddns_mapping(sub,updated) VALUES(?,?) ON CONFLICT(sub) DO UPDATE SET state='pending',updated=excluded.updated,error='' WHERE moddns_mapping.state NOT IN ('deleted','deleting')",(sub,int(time.time()))).rowcount!=1:raise HTTPException(410,'删除状态不能恢复')
    try:
        result=await call(h,sub,'PUT','/account')
        if not re.fullmatch('[a-f0-9]{24}',result['account_id']) or not re.fullmatch('[A-Za-z0-9]{6,64}',result['profile_id']):raise ValueError('invalid mapping')
        profile=await call(h,sub,'GET','/profiles/'+result['profile_id'])
        if profile['account_id']!=result['account_id']:raise ValueError('owner mismatch')
        defaults=['hagezi_multi_pro','hagezi_tif_medium']
        current=profile['settings']['privacy']['blocklists']
        missing=[v for v in defaults if v not in current]
        extra=[v for v in current if v not in defaults]
        if initial and missing:
            await call(h,sub,'POST','/profiles/'+result['profile_id']+'/blocklists',{'blocklist_ids':missing})
        if initial and extra:
            await call(h,sub,'DELETE','/profiles/'+result['profile_id']+'/blocklists',{'blocklist_ids':extra})
        # Remain pending while the sole proxy's old profile cache expires.
        await asyncio.sleep(1.1)
        with db() as c:
            current=c.execute('SELECT account_id,profile_id,state FROM moddns_mapping WHERE sub=?',(sub,)).fetchone()
            if not current or current[2]!='pending':raise HTTPException(409,'账号状态已变化')
            if current[0] and (current[0],current[1])!=(result['account_id'],result['profile_id']):raise ValueError('remote mapping changed; explicit repair required')
            c.execute("UPDATE moddns_mapping SET account_id=?,profile_id=?,state=?,updated=?,error='' WHERE sub=?",(result['account_id'],result['profile_id'],'ready' if mark_ready else 'pending',int(time.time()),sub))
        return result
    except Exception:
        with db() as c:c.execute("UPDATE moddns_mapping SET state='error',error='provision_failed',updated=? WHERE sub=? AND state NOT IN ('deleted','deleting')",(int(time.time()),sub))
        raise

def install(app,db,require_user,csrf,templates,mg):

    import filter_config
    filter_config.install(app,db,require_user,csrf,templates,mg)
    import advanced_filters
    advanced_filters.install(app,db,require_user,csrf,mg)

    @app.post('/filters/enable')
    async def enable(request:Request,csrf_token:str=Form(...)):
        u=require_user(request);csrf(request,u,csrf_token)
        if not u['enabled']:raise HTTPException(403,'账号已停用')
        lock=account_lock(u['sub'])
        if lock.locked():raise HTTPException(409,'请等待当前配置操作完成')
        async with lock:
            old=mapping(db,u['sub'])
            if old and old['routing'] and old['state']=='ready':return RedirectResponse('/filters',303)
            if old and old['state']=='updating':raise HTTPException(409,'请等待当前配置更新完成')
            await provision(db,app.state.http,u['sub'])
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                current=c.execute('SELECT enabled FROM account_settings WHERE sub=?',(u['sub'],)).fetchone()
                if not current or not current[0]:raise HTTPException(403,'账号已停用')
                c.execute('UPDATE moddns_mapping SET routing=1 WHERE sub=?',(u['sub'],))
                mg.audit(c,u['sub'],u['sub'],'filter.opt_in',{'routing':0},{'routing':1,'default_lists':['hagezi_multi_pro','hagezi_tif_medium']})
        return RedirectResponse('/filters',303)

    def selected(u):
        row=mapping(db,u['sub'])
        if not row:raise HTTPException(404,'此账号尚未开通过滤设置')
        if row['state']!='ready':raise HTTPException(503,'过滤配置正在同步或需要恢复')
        return row

    @app.get('/filters')
    async def filters(request:Request):
        u=require_user(request);row=selected(u)
        profile=await call(app.state.http,u['sub'],'GET','/profiles/'+row['profile_id'])
        if profile.get('account_id')!=row['account_id']:raise HTTPException(403,'配置归属不匹配')
        lists=await call(app.state.http,u['sub'],'GET','/blocklists')
        services=await call(app.state.http,u['sub'],'GET','/services')
        stats=mg.totals(db,u['sub'])
        import service_catalog
        catalog=services.get('services',[])
        return templates.TemplateResponse(request=request,name='filters.html',context={'user':u,'profile':profile,'lists':lists,'mapping':row,'stats':stats,'services':catalog,'service_groups':service_catalog.decorate(catalog)})

    @app.post('/filters')
    async def change(request:Request,csrf_token:str=Form(...),action:str=Form(...),value:str=Form(...,max_length=255)):
        u=require_user(request);csrf(request,u,csrf_token)
        lock=account_lock(u['sub'])
        if lock.locked():raise HTTPException(409,'请等待当前配置操作完成')
        async with lock:
            row=selected(u)
            if not u['enabled']:raise HTTPException(403,'账号已停用')
            path='/profiles/'+row['profile_id'];method='POST';payload=None
            if action in ('allow','block'):
                path+='/custom_rules';payload={'action':action,'value':value}
            elif action=='remove':
                if not re.fullmatch('[a-f0-9]{24}',value):raise HTTPException(422,'无效规则编号')
                method='DELETE';path+='/custom_rules/'+value
            elif action in ('enable_list','disable_list'):
                if not re.fullmatch('[A-Za-z0-9_-]{1,100}',value):raise HTTPException(422,'无效过滤列表')
                method='POST' if action=='enable_list' else 'DELETE';path+='/blocklists';payload={'blocklist_ids':[value]}
            else:raise HTTPException(422,'无效操作')
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute("UPDATE moddns_mapping SET state='updating',personalized=1,updated=? WHERE sub=? AND state='ready'",(int(time.time()),u['sub'])).rowcount!=1:raise HTTPException(409,'请等待当前配置更新完成')
            try:
                await call(app.state.http,u['sub'],method,path,payload)
                verified=await call(app.state.http,u['sub'],'GET','/profiles/'+row['profile_id'])
                if verified['account_id']!=row['account_id']:raise HTTPException(403,'配置归属不匹配')
                # Proxy lab cache TTL is 1 second; remain fail-closed until it expires.
                import asyncio
                await asyncio.sleep(1.1)
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    if c.execute("UPDATE moddns_mapping SET state='ready',revision=revision+1,updated=?,error='' WHERE sub=? AND state='updating'",(int(time.time()),u['sub'])).rowcount!=1:raise HTTPException(409,'账号状态已变化')
                    mg.audit(c,u['sub'],u['sub'],'filter.update',{'revision':row['revision']},{'revision':row['revision']+1,'operation':action})
            except Exception:
                with db() as c:c.execute("UPDATE moddns_mapping SET state='error',error='update_needs_reconciliation',updated=? WHERE sub=? AND state NOT IN ('deleted','deleting')",(int(time.time()),u['sub']))
                raise
        return RedirectResponse('/filters',303)
