"""Portable filtering snapshots and session-bound, expiring compare-and-apply previews."""
import asyncio,base64,hashlib,ipaddress,json,os,re,time
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken
from fastapi import Request,Form,HTTPException
from fastapi.responses import JSONResponse,RedirectResponse
import moddns_adapter as a
from advanced_filters import rule_value,pointer

FORMAT='matchall-filter-config-v1'
MAX_BYTES=800000

def digest(doc):return hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def signer():return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b'matchall-config-preview-v1\0'+Path(os.environ['TOKEN_KEY_FILE']).read_bytes()).digest()))
def rule_sort(r):return (r['value'],r['action'])

def snapshot(profile):
    s=profile['settings'];p=s['privacy']
    rules=[{k:r.get(k,'') for k in ('action','value','group','note')} for r in s.get('custom_rules',[])]
    groups={mode:[{'name':g['name'],'note':g.get('comment','')} for g in (s.get('custom_rule_groups') or {}).get(mode,[])] for mode in ('allow','block')}
    # Semantics are compatibility guards, not writable switches in this release.
    semantics={k:p.get(k,default) for k,default in [('default_rule','allow'),('custom_rules_subdomains_rule','include'),('blocklists_subdomains_rule','block')]}
    return {'format':FORMAT,'semantics':semantics,'blocklists':sorted(p.get('blocklists') or []),'services':sorted(p.get('services') or []),
            'rebinding':s['security']['rebinding_protection']['enabled'],'rules':sorted(rules,key=rule_sort),
            'groups':{k:sorted(v,key=lambda g:g['name']) for k,v in groups.items()}}

def parse(raw,current,lists,services):
    def require(ok,detail='配置文件格式不正确或超出限制'):
        if not ok:raise HTTPException(422,detail)
    def text(v,n):return isinstance(v,str) and len(v)<=n and not any(ord(c)<32 for c in v)
    def object_pairs(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('duplicate JSON key')
            d[k]=v
        return d
    require(len(raw.encode())<=MAX_BYTES,'配置文件最大 800 KB')
    try:d=json.loads(raw,object_pairs_hook=object_pairs)
    except (ValueError,RecursionError):raise HTTPException(422,'不是有效的 JSON 配置文件') from None
    require(isinstance(d,dict) and set(d)=={'format','semantics','blocklists','services','rebinding','rules','groups'})
    require(d['format']==FORMAT,'仅接受 MatchAll 完整过滤配置格式；规则文件请使用批量导入')
    require(d['semantics']==current['semantics'],'源配置的基础匹配语义不同，不能直接恢复到此配置')
    require(type(d['rebinding']) is bool)
    for field,available in [('blocklists',lists),('services',services)]:
        v=d[field];require(isinstance(v,list) and len(v)<=100 and all(text(x,100) and x in available for x in v),'包含当前不可用的过滤列表或服务，未写入任何配置')
        require(len(v)==len(set(v)),'列表或服务编号重复');d[field]=sorted(v)
    require(isinstance(d['groups'],dict) and set(d['groups'])=={'allow','block'})
    for mode,groups in d['groups'].items():
        require(isinstance(groups,list) and len(groups)<=100)
        for g in groups:require(isinstance(g,dict) and set(g)=={'name','note'} and text(g['name'],64) and len(g['name'].encode())<=64 and bool(g['name'].strip()) and text(g['note'],80))
        require(len(groups)==len({g['name'] for g in groups}),'分组名称重复');d['groups'][mode]=sorted(groups,key=lambda g:g['name'])
    require(isinstance(d['rules'],list) and len(d['rules'])<=1000,'每份完整配置最多 1,000 条规则；不会静默截断')
    seen=set()
    for r in d['rules']:
        require(isinstance(r,dict) and set(r)=={'action','value','group','note'})
        require(r['action'] in ('allow','block') and text(r['group'],64) and text(r['note'],80))
        v=rule_value(r['value'])
        if current['semantics']['custom_rules_subdomains_rule']!='exact' and not v.startswith('*.') and not re.fullmatch('AS[0-9]+',v):
            try:ipaddress.ip_address(v)
            except ValueError:v='*.'+v
        require(v not in seen,'存在重复或冲突的规范化规则');seen.add(v);r['value']=v
    d['rules']=sorted(d['rules'],key=rule_sort)
    return d

def diff(before,after):
    old={r['value']:r for r in before['rules']};new={r['value']:r for r in after['rules']}
    rows=[]
    for value in sorted(old.keys()|new.keys()):
        if old.get(value)!=new.get(value):rows.append({'value':value,'kind':'新增' if value not in old else '移除' if value not in new else '修改','before':old.get(value),'after':new.get(value)})
    return {'rules':rows,'lists_added':sorted(set(after['blocklists'])-set(before['blocklists'])),'lists_removed':sorted(set(before['blocklists'])-set(after['blocklists'])),
            'services_added':sorted(set(after['services'])-set(before['services'])),'services_removed':sorted(set(before['services'])-set(after['services'])),
            'groups_changed':before['groups']!=after['groups'],'rebinding_changed':before['rebinding']!=after['rebinding'],'changed':before!=after}

def install(app,db,require_user,csrf,templates,mg):
    async def current(u):
        row=a.mapping(db,u['sub'])
        if not row:raise HTTPException(404,'请先准备过滤配置')
        if row['state']!='ready':raise HTTPException(409,'配置正在同步或需要管理员恢复')
        p=await a.call(app.state.http,u['sub'],'GET','/profiles/'+row['profile_id'])
        if p.get('account_id')!=row['account_id']:raise HTTPException(403,'配置归属不匹配')
        return row,p
    async def catalogs(u):
        lists=await a.call(app.state.http,u['sub'],'GET','/blocklists')
        services=await a.call(app.state.http,u['sub'],'GET','/services')
        return {x['blocklist_id'] for x in lists if x.get('entries',0)>0},{x['id'] for x in services['services']}
    def check_enabled(u):
        with db() as c:r=c.execute('SELECT enabled FROM account_settings WHERE sub=?',(u['sub'],)).fetchone()
        if not r or not r[0]:raise HTTPException(403,'账号已停用，不能恢复配置')

    @app.get('/filters/config.json')
    async def export(request:Request):
        u=require_user(request);_,p=await current(u);doc=snapshot(p)
        # Backups remain downloadable without availability of a list/service catalog.
        parse(json.dumps(doc),doc,set(doc['blocklists']),set(doc['services']))
        return JSONResponse(doc,headers={'Content-Disposition':'attachment; filename="matchall-filter-config.json"','Cache-Control':'no-store'})

    @app.get('/filters/config')
    async def page(request:Request):
        u=require_user(request);row,p=await current(u)
        return templates.TemplateResponse(request=request,name='filter_config.html',context={'user':u,'mapping':row,'preview':None})

    @app.post('/filters/config/preview')
    async def preview(request:Request,csrf_token:str=Form(...),raw:str=Form(...,max_length=MAX_BYTES)):
        u=require_user(request);csrf(request,u,csrf_token);check_enabled(u)
        lock=a.account_lock(u['sub'])
        if lock.locked():raise HTTPException(409,'请等待当前配置操作完成')
        async with lock:
            row,p=await current(u);before=snapshot(p);lists,services=await catalogs(u);target=parse(raw,before,lists,services)
            envelope={'sub':u['sub'],'session':u['hash'],'revision':row['revision'],'profile':row['profile_id'],'account':row['account_id'],'routing':row['routing'],'before_hash':digest(before),'target':target}
            token=signer().encrypt(json.dumps(envelope,separators=(',',':'),ensure_ascii=False).encode()).decode()
        return templates.TemplateResponse(request=request,name='filter_config.html',context={'user':u,'mapping':row,'preview':diff(before,target),'before':before,'target':target,'token':token})

    @app.post('/filters/config/apply')
    async def apply(request:Request,csrf_token:str=Form(...),token:str=Form(...,max_length=1500000),confirm:str=Form(...)):
        u=require_user(request);csrf(request,u,csrf_token);check_enabled(u)
        if confirm!='replace':raise HTTPException(422,'请确认按预览覆盖过滤配置')
        try:
            envelope=json.loads(signer().decrypt(token.encode(),ttl=600))
            if envelope['sub']!=u['sub'] or envelope['session']!=u['hash']:raise ValueError()
        except (InvalidToken,ValueError,KeyError,TypeError):raise HTTPException(409,'预览无效或已过期，请重新预览') from None
        lock=a.account_lock(u['sub'])
        if lock.locked():raise HTTPException(409,'请等待当前配置操作完成')
        async with lock:
            row,p=await current(u);before=snapshot(p)
            if (row['revision'],row['profile_id'],row['account_id'],row['routing'],digest(before))!=(envelope['revision'],envelope['profile'],envelope['account'],envelope['routing'],envelope['before_hash']):raise HTTPException(409,'预览后配置或解析状态已改变，请重新预览')
            lists,services=await catalogs(u);target=parse(json.dumps(envelope['target']),before,lists,services)
            if before==target:return RedirectResponse('/filters/config?unchanged=1',303)
            path='/profiles/'+row['profile_id']
            check_enabled(u)
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute("UPDATE moddns_mapping SET state='updating',personalized=1,updated=? WHERE sub=? AND state='ready' AND revision=?",(int(time.time()),u['sub'],row['revision'])).rowcount!=1:raise HTTPException(409,'配置状态已变化')
            async def call(method,suffix,data=None):return await a.call(app.state.http,u['sub'],method,path+suffix,data)
            try:
                new={r['value']:r for r in target['rules']};old={r['value']:r for r in p['settings'].get('custom_rules',[])}
                for value,r in old.items():
                    if value not in new:await call('DELETE','/custom_rules/'+r['id'])
                # Group removal only ungroups rules; reassign every retained rule afterwards.
                if before['groups']!=target['groups']:
                    for mode in ('allow','block'):
                        for g in before['groups'][mode]:await call('PATCH','/custom_rule_groups',{'updates':[{'operation':'remove','action':mode,'path':pointer(g['name'])}]})
                        for g in target['groups'][mode]:await call('PATCH','/custom_rule_groups',{'updates':[{'operation':'replace','action':mode,'path':pointer(g['name']),'value':g['note']}]})
                for mode in ('allow','block'):
                    values=[r['value'] for r in target['rules'] if r['action']==mode and r['value'] not in old]
                    for i in range(0,len(values),20):
                        res=await call('POST','/custom_rules/batch',{'action':mode,'values':values[i:i+20]})
                        if res.get('skipped') or len(res['created'])!=len(values[i:i+20]):raise ValueError('incomplete rules')
                        for r in res['created']:old[r['value']]={**r,'action':mode,'group':'','note':''}
                for value,r in new.items():
                    prior=old[value]
                    if before['groups']!=target['groups'] or any(prior.get(k,'')!=r[k] for k in ('action','group','note')):
                        await call('PATCH','/custom_rules/'+prior['id'],{k:r[k] for k in ('action','group','note')})
                for field,suffix,param in [('blocklists','/blocklists','blocklist_ids'),('services','/services','service_ids')]:
                    removed=sorted(set(before[field])-set(target[field]));added=sorted(set(target[field])-set(before[field]))
                    if removed:await call('DELETE',suffix,{param:removed})
                    if added:await call('POST',suffix,{param:added})
                if before['rebinding']!=target['rebinding']:await call('PATCH','/rebinding',{'enabled':target['rebinding']})
                verified=await call('GET','')
                if verified.get('account_id')!=row['account_id'] or snapshot(verified)!=target:raise ValueError('restore verification mismatch')
                await asyncio.sleep(1.1)
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    if c.execute("UPDATE moddns_mapping SET state='ready',revision=revision+1,updated=?,error='' WHERE sub=? AND state='updating' AND revision=?",(int(time.time()),u['sub'],row['revision'])).rowcount!=1:raise HTTPException(409,'配置状态已变化')
                    mg.audit(c,u['sub'],u['sub'],'filter.config.restore',{'revision':row['revision']},{'revision':row['revision']+1,'rules':len(target['rules']),'lists':len(target['blocklists']),'services':len(target['services'])})
            except Exception:
                with db() as c:c.execute("UPDATE moddns_mapping SET state='error',error='config_restore_needs_reconciliation',updated=? WHERE sub=? AND state NOT IN ('deleted','deleting')",(int(time.time()),u['sub']))
                raise HTTPException(503,'恢复未完成，可能部分保存；请由管理员恢复同步后检查实际配置。解析路由和账号状态未改变。') from None
        return RedirectResponse('/filters/config?restored=1',303)
