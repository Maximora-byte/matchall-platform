#!/usr/bin/env python3
"""Build a deterministic service catalog from pinned, locally verified sources."""
import json,re,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent/'moddns-matchall/dev/bootstrap/services/catalog.yml'
SOURCES=ROOT/'data/service-sources'
OUT_META=ROOT/'data/service-catalog.json'
GROUP_NAMES={'ai':'AI','cdn':'CDN','dating':'交友','gambling':'博彩','gaming':'游戏','hosting':'托管与云服务','messenger':'即时通讯','privacy':'隐私工具','shopping':'购物','social_network':'社交网络','software':'软件服务','streaming':'流媒体','other':'其他'}
V2_GROUP={'bilibili':'streaming','bytedance':'social_network','douyin':'social_network','mihoyo':'gaming','netease':'gaming','sina':'social_network','tencent':'messenger','zhihu':'social_network'}
V2_NAMES={'bilibili':'哔哩哔哩','bytedance':'字节跳动','douyin':'抖音','mihoyo':'米哈游','netease':'网易','sina':'新浪','tencent':'腾讯／微信／QQ','zhihu':'知乎'}

def base_services(path):
    text=path.read_text()
    if text.lstrip().startswith('{'):return json.loads(text)['services']
    rows=[];cur=None
    for raw in text.splitlines():
        line=raw.strip()
        if line.startswith('- id:'):
            cur={'id':line.split(':',1)[1].strip(),'name':'','logo_key':'','asns':[],'domains':[]};rows.append(cur)
        elif cur and ':' in line:
            key,val=(x.strip() for x in line.split(':',1))
            if key in ('name','logo_key'):cur[key]=val
            elif key=='asns' and val.startswith('['):cur[key]=[int(x.strip()) for x in val[1:-1].split(',') if x.strip()]
            elif key=='domains' and val.startswith('['):cur[key]=[x.strip() for x in val[1:-1].split(',') if x.strip()]
    return rows

def valid_domain(value):
    value=value.lower().rstrip('.')
    return value if len(value)<=253 and '.' in value and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',x) for x in value.split('.')) else None

def adguard_domains(rules):
    out=[]
    for rule in rules:
        m=re.fullmatch(r'\|\|([A-Za-z0-9._-]+)\^',rule)
        if m and (d:=valid_domain(m.group(1))):out.append(d)
    return out

def v2_domains(path):
    out=[]
    for raw in path.read_text().splitlines():
        line=raw.split('#',1)[0].strip().split('@',1)[0]
        if not line or line.startswith(('include:','regexp:','keyword:')):continue
        if line.startswith('full:'):line=line[5:]
        if d:=valid_domain(line):out.append(d)
    return out

def main():
    versions=dict(line.split('=',1) for line in (SOURCES/'VERSIONS').read_text().splitlines())
    base=base_services(BASE);used={d for s in base for d in s.get('domains',[])};ids={s['id'] for s in base}
    meta=[]
    for s in base:
        meta.append({'id':s['id'],'name':s['name'],'group':'other','group_name':GROUP_NAMES['other'],'source':'MatchAll legacy','domains':s.get('domains',[])})
    doc=json.loads((SOURCES/'adguard-services.json').read_text())
    for item in doc['blocked_services']:
        sid=item['id'].lower().replace('.','_')
        if not re.fullmatch(r'[a-z0-9_-]{1,64}',sid) or sid in ids:continue
        domains=[]
        for d in adguard_domains(item.get('rules',[])):
            if d not in used:domains.append(d);used.add(d)
        if not domains:continue
        group=item.get('group','other');base.append({'id':sid,'name':item['name'],'logo_key':sid,'asns':[],'domains':domains});ids.add(sid)
        meta.append({'id':sid,'name':item['name'],'group':group,'group_name':GROUP_NAMES.get(group,group),'source':'AdGuard HostlistsRegistry','domains':domains})
    for path in sorted((SOURCES/'v2fly').iterdir()):
        sid='v2_'+path.name
        if sid in ids:continue
        domains=[]
        for d in v2_domains(path):
            if d not in used:domains.append(d);used.add(d)
        if not domains:continue
        group=V2_GROUP[path.name];base.append({'id':sid,'name':V2_NAMES[path.name],'logo_key':sid,'asns':[],'domains':domains});ids.add(sid)
        meta.append({'id':sid,'name':V2_NAMES[path.name],'group':group,'group_name':GROUP_NAMES[group],'source':'v2fly/domain-list-community','domains':domains})
    BASE.write_text(json.dumps({'services':base},ensure_ascii=False,indent=2)+'\n')
    OUT_META.write_text(json.dumps({'schema':1,'sources':versions,'groups':GROUP_NAMES,'services':meta},ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({'services':len(base),'domains':sum(len(x['domains']) for x in base),'adguard_commit':versions['adguard_commit'],'v2fly_commit':versions['v2fly_commit']}))

if __name__=='__main__':main()
