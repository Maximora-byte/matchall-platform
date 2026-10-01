"""Read-only service classification for private query analytics."""
import json
from pathlib import Path

CATALOG=Path(__file__).with_name('data')/'service-catalog.json'
_cache=None

def load():
    global _cache
    if _cache is None:
        doc=json.loads(CATALOG.read_text())
        suffix={}
        by_id={}
        for service in doc['services']:
            by_id[service['id']]=service
            for domain in service['domains']:suffix.setdefault(domain,service['id'])
        _cache=(doc,by_id,suffix)
    return _cache

def classify(domain):
    doc,by_id,suffix=load();parts=domain.lower().rstrip('.').split('.')
    for i in range(len(parts)-1):
        if sid:=suffix.get('.'.join(parts[i:])):return by_id[sid]
    return None

def aggregate(rows):
    services={};groups={};unclassified=0
    for domain,count,blocked in rows:
        item=classify(domain)
        if not item:unclassified+=count;continue
        service=services.setdefault(item['id'],{'id':item['id'],'name':item['name'],'group':item['group_name'],'count':0,'blocked':0})
        service['count']+=count;service['blocked']+=blocked or 0
        group=groups.setdefault(item['group'],{'id':item['group'],'name':item['group_name'],'count':0,'blocked':0})
        group['count']+=count;group['blocked']+=blocked or 0
    return {'services':sorted(services.values(),key=lambda x:(-x['count'],x['name']))[:15],
            'groups':sorted(groups.values(),key=lambda x:(-x['count'],x['name'])),'unclassified':unclassified}

def decorate(services):
    doc,by_id,_=load();groups={}
    for service in services:
        meta=by_id.get(service['id'],{'group':'other','group_name':'其他','source':'MatchAll'})
        item={**service,'group':meta['group'],'group_name':meta['group_name'],'source':meta['source']}
        groups.setdefault(meta['group'],{'id':meta['group'],'name':meta['group_name'],'services':[]})['services'].append(item)
    return sorted(groups.values(),key=lambda x:x['name'])
