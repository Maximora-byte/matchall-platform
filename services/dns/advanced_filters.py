"""Bounded advanced filtering; never accepts a client-selected profile or changes routing."""
import asyncio,ipaddress,json,re,time
from fastapi import Request,Form,HTTPException
from fastapi.responses import JSONResponse,RedirectResponse
import moddns_adapter as a

def rule_value(value):
    if not isinstance(value,str):raise HTTPException(422,'规则必须是文本')
    value=value.strip().lower().rstrip('.')
    if not value or len(value)>253:raise HTTPException(422,'规则长度不正确')
    try:return str(ipaddress.ip_address(value))
    except ValueError:pass
    if re.fullmatch(r'as[1-9][0-9]{0,9}',value) and int(value[2:])<=4294967295:return value.upper()
    domain=value[2:] if value.startswith('*.') else value
    if '.' not in domain or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',x) for x in domain.split('.')):
        raise HTTPException(422,'仅接受域名、*.域名、IP 或 AS 编号；不接受 URL 或广告过滤表达式')
    return value

def parse_rules(raw,action,group):
    try:
        if raw.lstrip().startswith('{'):
            doc=json.loads(raw)
            if doc.get('format')!='matchall-rules-v1':raise ValueError()
            rows=doc['rules']
        else:rows=[{'action':action,'value':x,'group':group} for x in raw.splitlines() if x.strip()]
        if not isinstance(rows,list) or not 1<=len(rows)<=200:raise ValueError()
        result=[];seen=set()
        for r in rows:
            if not isinstance(r,dict) or r.get('action') not in ('allow','block'):raise ValueError()
            value=rule_value(r.get('value'));g=r.get('group','');note=r.get('note','')
            if not isinstance(g,str) or not isinstance(note,str) or len(g)>64 or len(note)>80 or any(ord(c)<32 for c in g+note):raise ValueError()
            key=(r['action'],value)
            if key not in seen:result.append({'action':r['action'],'value':value,'group':g,'note':note});seen.add(key)
        return result
    except (ValueError,TypeError,KeyError,AttributeError):raise HTTPException(422,'导入格式不正确：最多 200 条，分组最多 64 字，备注最多 80 字') from None

def pointer(s):return '/'+s.replace('~','~0').replace('/','~1')

def install(app,db,require_user,csrf,mg):
    async def profile_for(u):
        row=a.mapping(db,u['sub'])
        if not row:raise HTTPException(404,'请先准备过滤配置')
        if row['state']!='ready':raise HTTPException(409,'配置正在同步或需要管理员恢复')
        p=await a.call(app.state.http,u['sub'],'GET','/profiles/'+row['profile_id'])
        if p.get('account_id')!=row['account_id']:raise HTTPException(403,'配置归属不匹配')
        return row,p

    @app.get('/filters/rules.json')
    async def export(request:Request):
        u=require_user(request);row,p=await profile_for(u)
        rows=[{k:r.get(k,'') for k in ('action','value','group','note')} for r in p['settings'].get('custom_rules',[]) if r['action'] in ('allow','block')]
        return JSONResponse({'format':'matchall-rules-v1','rules':rows},headers={'Content-Disposition':'attachment; filename="matchall-rules.json"','Cache-Control':'no-store'})

    @app.post('/filters/prepare')
    async def prepare(request:Request,csrf_token:str=Form(...)):
        u=require_user(request);csrf(request,u,csrf_token)
        if not u['enabled']:raise HTTPException(403,'账号已停用')
        lock=a.account_lock(u['sub'])
        if lock.locked():raise HTTPException(409,'请等待当前配置操作完成')
        async with lock:
            if not a.mapping(db,u['sub']):
                await a.provision(db,app.state.http,u['sub'])
                with db() as c:mg.audit(c,u['sub'],u['sub'],'filter.prepare',{}, {'routing':0})
        return RedirectResponse('/filters',303)

    @app.post('/filters/advanced')
    async def advanced(request:Request,csrf_token:str=Form(...),operation:str=Form(...),value:str=Form('',max_length=255),action:str=Form('block'),group:str=Form('',max_length=64),note:str=Form('',max_length=80),raw:str=Form('',max_length=100000)):
        u=require_user(request);csrf(request,u,csrf_token)
        if not u['enabled']:raise HTTPException(403,'账号已停用')
        if operation not in ('import','rule_meta','group_save','group_rename','group_remove','service_on','service_off','rebinding_on','rebinding_off'):raise HTTPException(422,'无效操作')
        if action not in ('allow','block'):raise HTTPException(422,'无效规则类型')
        if any(ord(c)<32 for c in group+note):raise HTTPException(422,'分组和备注不可包含控制字符')
        rules=parse_rules(raw,action,group) if operation=='import' else None
        if operation=='rule_meta' and not re.fullmatch('[a-f0-9]{24}',value):raise HTTPException(422,'无效规则编号')
        if operation.startswith('group_') and not group.strip():raise HTTPException(422,'请填写分组名称')
        if operation=='group_rename' and (not value.strip() or len(value)>64 or any(ord(c)<32 for c in value)):raise HTTPException(422,'无效新分组名称')
        if operation.startswith('service_') and not re.fullmatch('[a-z0-9_-]{1,100}',value):raise HTTPException(422,'无效服务')
        lock=a.account_lock(u['sub'])
        if lock.locked():raise HTTPException(409,'请等待当前配置操作完成')
        async with lock:
            row,p=await profile_for(u);path='/profiles/'+row['profile_id'];created=skipped=0
            existing={r['value'] for r in p['settings'].get('custom_rules',[])}
            if rules is not None:
                normalized=[];seen=set()
                for r in rules:
                    value=r['value']
                    if p['settings'].get('privacy',{}).get('custom_rules_subdomains_rule','include')!='exact' and not value.startswith('*.') and not re.fullmatch(r'AS[0-9]+',value):
                        try:ipaddress.ip_address(value)
                        except ValueError:value='*.'+value
                    if value in seen:
                        skipped+=1
                        continue
                    seen.add(value);normalized.append({**r,'value':value})
                rules=normalized
            if operation=='rule_meta' and value not in [r['id'] for r in p['settings'].get('custom_rules',[])]:raise HTTPException(404,'规则不存在')
            if operation.startswith('service_'):
                catalog=await a.call(app.state.http,u['sub'],'GET','/services')
                if value not in [x['id'] for x in catalog['services']]:raise HTTPException(422,'服务不存在')
            if rules and len(existing)+sum(r['value'] not in existing for r in rules)>10000:raise HTTPException(422,'规则总量超出限制')
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                enabled=c.execute('SELECT enabled FROM account_settings WHERE sub=?',(u['sub'],)).fetchone()
                if not enabled or not enabled[0]:raise HTTPException(403,'账号已停用')
                if c.execute("UPDATE moddns_mapping SET state='updating',personalized=1,updated=? WHERE sub=? AND state='ready'",(int(time.time()),u['sub'])).rowcount!=1:raise HTTPException(409,'配置状态已变化')
            async def call(method,suffix,data):return await a.call(app.state.http,u['sub'],method,path+suffix,data)
            try:
                if rules is not None:
                    for mode in ('allow','block'):
                        new=[r for r in rules if r['action']==mode and r['value'] not in existing]
                        skipped+=sum(r['action']==mode and r['value'] in existing for r in rules)
                        for i in range(0,len(new),20):
                            part=new[i:i+20];res=await call('POST','/custom_rules/batch',{'action':mode,'values':[r['value'] for r in part]})
                            made=res['created'];created+=len(made);skipped+=len(res.get('skipped',[]))
                            metadata={r['value']:r for r in part}
                            for r in made:
                                info=metadata[r['value']]
                                if info['group'] or info['note']:await call('PATCH','/custom_rules/'+r['id'],{'group':info['group'],'note':info['note']})
                elif operation=='rule_meta':await call('PATCH','/custom_rules/'+value,{'group':group,'note':note})
                elif operation.startswith('group_'):
                    op={'action':action,'path':pointer(group),'operation':{'group_save':'replace','group_remove':'remove','group_rename':'move'}[operation]}
                    if operation=='group_rename':op.update({'from':pointer(group),'path':pointer(value)})
                    elif operation=='group_save':op['value']=note
                    await call('PATCH','/custom_rule_groups',{'updates':[op]})
                elif operation.startswith('service_'):await call('POST' if operation=='service_on' else 'DELETE','/services',{'service_ids':[value]})
                else:await call('PATCH','/rebinding',{'enabled':operation=='rebinding_on'})
                verified=await a.call(app.state.http,u['sub'],'GET',path)
                if verified.get('account_id')!=row['account_id']:raise HTTPException(403,'配置归属不匹配')
                await asyncio.sleep(1.1)
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    if c.execute("UPDATE moddns_mapping SET state='ready',revision=revision+1,updated=?,error='' WHERE sub=? AND state='updating'",(int(time.time()),u['sub'])).rowcount!=1:raise HTTPException(409,'配置状态已变化')
                    mg.audit(c,u['sub'],u['sub'],'filter.advanced',{'revision':row['revision']},{'revision':row['revision']+1,'operation':operation,'created':created,'skipped':skipped})
            except Exception:
                with db() as c:c.execute("UPDATE moddns_mapping SET state='error',error='advanced_needs_reconciliation',updated=? WHERE sub=? AND state NOT IN ('deleted','deleting')",(int(time.time()),u['sub']))
                raise HTTPException(503,'配置可能已部分保存；请让管理员恢复同步后查看实际规则，再重试。不会切换原解析路由。') from None
        suffix=('?imported='+str(created)+'&skipped='+str(skipped)) if rules is not None else '?saved=1'
        return RedirectResponse('/filters'+suffix,303)
