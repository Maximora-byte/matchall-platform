"""Bounded aggregate statistics. Never selects DNS domains, tokens or other users' IDs."""
from datetime import datetime,timezone
from typing import Literal
import time,csv,io
from urllib.parse import urlencode
from fastapi import Request,Query,HTTPException
from fastapi.responses import Response

Period=Literal['24h','7d','30d','90d','all']
PERIODS={'24h':(86400,3600),'7d':(7*86400,86400),'30d':(30*86400,86400),'90d':(90*86400,86400),'all':(0,0)}
METRICS=('received','admitted','forwarded','success','failed','limited','disabled','invalid','blocked','filter_success','filter_blocked')
TRACES=(('received','请求'),('success','成功'),('blocked','已确认拦截'),('failed','上游失败'))
BLOCKLISTS=(('hagezi_multi_pro','HaGeZi Multi Pro'),('hagezi_tif_medium','HaGeZi TIF Medium'))

def stamp(value):return datetime.fromtimestamp(value,timezone.utc).strftime('%m-%d %H:%M')

def report(db,mg,period,sub=None,now=None):
    now=int(time.time()) if now is None else now
    mg.flush(db)
    if period=='all':
        with db() as c:
            row=c.execute('SELECT MIN(window) first FROM usage'+(' WHERE sub=?' if sub is not None else ''),(sub,) if sub is not None else ()).fetchone()
        first=row['first'] if row and row['first'] is not None else now-86400
        span=max(86400,now-first)
        step=86400 if span<=366*86400 else 7*86400
        start=first//step*step;end=(now//step+1)*step;duration=end-start
    else:
        duration,step=PERIODS[period]
        # Existing counters are minute buckets. Include the in-progress current minute.
        end=now//60*60+60;start=end-duration
    with db() as c:
        rows=c.execute('SELECT ((window-?)/?) bucket,metric,SUM(count) n FROM usage WHERE window>=? AND window<?'+(' AND sub=?' if sub is not None else '')+' GROUP BY bucket,metric', (start,step,start,end,sub) if sub is not None else (start,step,start,end)).fetchall()
        migrations=dict(c.execute('SELECT version,applied FROM schema_migrations WHERE version IN (1,3)').fetchall())
    series=[{'start':start+i*step,'label':stamp(start+i*step),**dict.fromkeys(METRICS,0)} for i in range(max(1,duration//step))]
    totals=dict.fromkeys(METRICS,0)
    for row in rows:
        if row['metric'] in totals:
            series[row['bucket']][row['metric']]+=row['n'];totals[row['metric']]+=row['n']
    def rate(item):return round(item['filter_blocked']*100/item['filter_success'],2) if item['filter_success'] else None
    for item in series:item['block_rate']=rate(item)
    aggregate={}
    for row in rows:
        if row['metric'].startswith('blocklist_'):
            aggregate[row['metric']]=aggregate.get(row['metric'],0)+row['n']
    blocklists=[{'id':blocklist_id,'label':label,
                 'hits':aggregate.get('blocklist_hit:'+blocklist_id,0),
                 'only':aggregate.get('blocklist_only:'+blocklist_id,0)} for blocklist_id,label in BLOCKLISTS]
    for item in blocklists:item['shared']=item['hits']-item['only']
    return {'period':period,'start':start,'end':end,'generated':now,'start_label':stamp(start),'end_label':stamp(end),'timezone':'UTC',
            'step_seconds':step,'totals':totals,'series':series,'block_rate':rate(totals),'has_data':any(totals.values()),
            'blocklists':blocklists,'blocklist_attributed':aggregate.get('blocklist_attributed',0),'blocklist_overlap':aggregate.get('blocklist_overlap',0),
            'aggregate_since':migrations.get(1),'filter_rate_since':migrations.get(3),'filter_rate_since_label':stamp(migrations[3]) if 3 in migrations else '暂无记录'}

def chart(data):
    points=data['series'];maximum=max(1,max(p[k] for p in points for k,_ in TRACES));traces=[]
    def x(i):return round(60+880*i/max(1,len(points)-1),2)
    for metric,label in TRACES:
        dots=[{'x':x(i),'y':round(210-180*p[metric]/maximum,2),'value':p[metric],'label':p['label']} for i,p in enumerate(points)]
        traces.append({'metric':metric,'label':label,'dots':dots,'line':' '.join(f"{d['x']},{d['y']}" for d in dots)})
    segments=[];dots=[];segment=[]
    for i,p in enumerate(points):
        if p['block_rate'] is None:
            if segment:segments.append(' '.join(segment));segment=[]
        else:
            d={'x':x(i),'y':round(210-1.8*p['block_rate'],2),'value':p['block_rate'],'label':p['label']};dots.append(d);segment.append(f"{d['x']},{d['y']}")
    if segment:segments.append(' '.join(segment))
    return {'traces':traces,'maximum':maximum,'rate_segments':segments,'rate_dots':dots,'ticks':[{'x':x(i),'label':p['label']} for i,p in enumerate(points) if i in (0,len(points)//2,len(points)-1)]}

def csv_response(data):
    output=io.StringIO(newline='');writer=csv.writer(output)
    writer.writerow(['start_utc','end_utc',*METRICS,'filter_block_rate_pct','filter_rate_since_utc'])
    def iso(ts):return datetime.fromtimestamp(ts,timezone.utc).isoformat() if ts is not None else ''
    for p in data['series']:
        writer.writerow([iso(p['start']),iso(p['start']+data['step_seconds']),*[p[k] for k in METRICS],p['block_rate'] if p['block_rate'] is not None else '',iso(data['filter_rate_since'])])
    # Only timestamps and numeric aggregates, never user-supplied names/formulas.
    return Response(output.getvalue().encode('utf-8-sig'),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="dns-statistics-{data["period"]}.csv"','Cache-Control':'no-store'})

def install(app,db,require_user,require_admin,templates,mg):
    def selected_account(account):
        if not account:return None
        with db() as c:r=c.execute('SELECT sub,name FROM users WHERE sub=?',(account,)).fetchone()
        if not r:raise HTTPException(404,'账号不存在，不回退到全站统计')
        return dict(r)
    def render(request,u,period,admin,account=''):
        selected=selected_account(account) if admin else None
        data=report(db,mg,period,selected['sub'] if selected else None if admin else u['sub'])
        accounts=[]
        if admin:
            with db() as c:accounts=[dict(r) for r in c.execute('SELECT sub,name FROM users ORDER BY created DESC LIMIT 200')]
            if selected and selected['sub'] not in [x['sub'] for x in accounts]:accounts.append(selected)
        path='/admin/statistics' if admin else '/statistics'
        links={key:path+'?'+urlencode({'period':key,**({'account':account} if account else {})}) for key in PERIODS}
        export=path+'.csv?'+urlencode({'period':period,**({'account':account} if account else {})})
        return templates.TemplateResponse(request=request,name='statistics.html',context={'user':u,'stats':data,'chart':chart(data),'sitewide':admin,'stats_path':path,'period_links':links,'export_url':export,'accounts':accounts,'selected_account':selected})
    @app.get('/statistics')
    def user_page(request:Request,period:Period='24h'):
        return render(request,require_user(request),period,False)
    @app.get('/admin/statistics')
    def admin_page(request:Request,period:Period='24h',account:str=Query('',max_length=255)):
        return render(request,require_admin(request),period,True,account)
    @app.get('/api/statistics')
    def user_api(request:Request,period:Period='24h'):
        u=require_user(request);return report(db,mg,period,u['sub'])
    @app.get('/api/admin/statistics')
    def admin_api(request:Request,period:Period='24h',account:str=Query('',max_length=255)):
        require_admin(request);selected=selected_account(account)
        return report(db,mg,period,selected['sub'] if selected else None)
    @app.get('/statistics.csv')
    def user_csv(request:Request,period:Period='24h'):
        u=require_user(request);return csv_response(report(db,mg,period,u['sub']))
    @app.get('/admin/statistics.csv')
    def admin_csv(request:Request,period:Period='24h',account:str=Query('',max_length=255)):
        require_admin(request);selected=selected_account(account)
        return csv_response(report(db,mg,period,selected['sub'] if selected else None))
