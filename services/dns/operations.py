"""Admin-only metadata and explicit reconciliation; no query domains or credentials."""
import datetime,json,os,time
from pathlib import Path
from fastapi import Request,Form,HTTPException
from fastapi.responses import RedirectResponse
import moddns_adapter as adapter

STATE_LABELS={'legacy':'未开通','ready':'就绪','pending':'同步中','updating':'更新中','error':'需要恢复','deleting':'删除中','deleted':'已删除'}

def host_status():
    try:
        path=Path(os.getenv('DNS_HOST_HEALTH_FILE','/run/dns-health/health.json'))
        if path.stat().st_size>65536:raise ValueError('oversize')
        raw=json.loads(path.read_text())
        if not isinstance(raw,dict):raise ValueError('invalid report')
        checked=datetime.datetime.fromisoformat(raw['checked']).timestamp()
        age=time.time()-checked
        if age< -60 or age>900:return {'ok':False,'status':'stale','errors':['健康报告已过期'],'checked':raw['checked']}
        return {'ok':raw.get('ok') is True,'status':'current','checked':raw['checked'],'errors':raw.get('errors',[]),'disks':raw.get('disks',[]),'backup':raw.get('backup',{}),'certificate':raw.get('certificate',{})}
    except (OSError,ValueError,TypeError,KeyError):
        return {'ok':False,'status':'unavailable','errors':['健康报告暂不可用'],'checked':None}

def summary(db,app,mg):
    with db() as c:
        counts={r['state']:r['n'] for r in c.execute('SELECT state,count(*) n FROM moddns_mapping GROUP BY state')}
        enabled=c.execute('SELECT count(*) FROM moddns_mapping WHERE routing=1').fetchone()[0]
    return {'host':host_status(),'mapping_counts':counts,'routed_accounts':enabled,
            'statistics_ok':not app.state.stats_error and time.monotonic()-app.state.last_flush<=20,
            'dns_nodes':[{'name':name,'fresh':time.time()-node['checked']<90,**node} for name,node in mg.health.items()],
            'scope':'single-worker-single-proxy','backup_location':'same-host'}

def install(app,db,require_admin,csrf,templates,mg):
    @app.get('/api/admin/operations')
    def api_operations(request:Request):
        require_admin(request)
        return summary(db,app,mg)

    @app.get('/admin/operations')
    def operations_page(request:Request):
        u=require_admin(request)
        return templates.TemplateResponse(request=request,name='operations.html',context={'user':u,'ops':summary(db,app,mg),'state_labels':STATE_LABELS})

    @app.post('/admin/filters/{sub}/recover')
    async def recover(request:Request,sub:str,csrf_token:str=Form(...)):
        u=require_admin(request);csrf(request,u,csrf_token)
        lock=adapter.account_lock(sub)
        if lock.locked():raise HTTPException(409,'该账号正在执行配置操作')
        async with lock:
            old=adapter.mapping(db,sub)
            if not old:raise HTTPException(404,'账号未主动开通过滤，不能通过恢复操作开通')
            if old['state'] in ('deleted','deleting'):raise HTTPException(410,'删除状态不能自动恢复')
            if old['state']=='ready':return RedirectResponse('/admin',303)
            # A crashed worker may leave pending/updating behind; active work owns the lock.
            if old['state'] in ('pending','updating') and time.time()-old['updated']<60:
                raise HTTPException(409,'同步尚未超时，请稍后再试')
            before={'state':old['state'],'revision':old['revision'],'routing':old['routing']}
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                role=c.execute('SELECT is_admin FROM account_settings WHERE sub=?',(u['sub'],)).fetchone()
                if not role or not role[0]:raise HTTPException(403,'管理员权限已撤销')
                mg.audit(c,u['sub'],sub,'filter.recover.start',before,{'state':'pending'})
            try:
                # The final ready transition and audit must commit together.
                await adapter.provision(db,app.state.http,sub,mark_ready=False)
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    role=c.execute('SELECT is_admin FROM account_settings WHERE sub=?',(u['sub'],)).fetchone()
                    if not role or not role[0]:raise HTTPException(403,'管理员权限已撤销，恢复未提交')
                    row=c.execute('SELECT * FROM moddns_mapping WHERE sub=?',(sub,)).fetchone()
                    if row['state']!='pending' or row['routing']!=old['routing']:raise HTTPException(409,'账号状态已变化')
                    c.execute("UPDATE moddns_mapping SET state='ready',updated=?,error='' WHERE sub=?",(int(time.time()),sub))
                    mg.audit(c,u['sub'],sub,'filter.recover.complete',before,{'state':'ready','revision':row['revision'],'routing':row['routing']})
            except Exception as exc:
                with db() as c:
                    c.execute("UPDATE moddns_mapping SET state='error',error='recovery_failed',updated=? WHERE sub=? AND state NOT IN ('deleted','deleting')",(int(time.time()),sub))
                    mg.audit(c,u['sub'],sub,'filter.recover.failed',before,{'state':'error'},result='failed')
                if isinstance(exc,HTTPException):raise
                raise HTTPException(503,'恢复未完成；保持原路由和停用状态，请检查服务与身份映射') from None
        return RedirectResponse('/admin',303)
