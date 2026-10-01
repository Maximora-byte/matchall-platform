import time
import csv,io
import pytest
import app as m
import management as mg
import statistics_panel as stats
from test_app import client,signin,create,query
from test_management import make_admin

def add(sub,window,metric,value):
    with m.db() as c:c.execute('INSERT INTO usage VALUES(?,?,?,?)',(window,sub,metric,value))

def test_stat_permissions_and_account_isolation(client):
    for path in ['/statistics','/api/statistics','/admin/statistics','/api/admin/statistics']:
        assert client.get(path).status_code==401
    signin(client)
    t=int(time.time())//60*60
    add('user-a',t,'received',3);add('other',t,'received',99)
    data=client.get('/api/statistics?sub=other').json()
    assert data['totals']['received']==3
    assert client.get('/api/admin/statistics').status_code==403
    assert client.get('/admin/statistics').status_code==403
    make_admin();r=client.get('/api/admin/statistics');assert r.json()['totals']['received']==102
    assert r.headers['cache-control']=='no-store'
    with m.db() as c:c.execute('UPDATE account_settings SET is_admin=0')
    assert client.get('/api/admin/statistics').status_code==403

@pytest.mark.parametrize('period,size',[('24h',24),('7d',7),('30d',30)])
def test_bounded_windows_and_empty_rates(client,period,size):
    signin(client)
    now=1800000000;duration,_=stats.PERIODS[period];end=now//60*60+60;start=end-duration
    add('user-a',start-60,'received',99)
    add('user-a',start,'received',2)
    add('user-a',end-60,'received',3)
    add('user-a',end,'received',99)
    data=stats.report(m.db,mg,period,'user-a',now=now)
    assert len(data['series'])==size and data['totals']['received']==5
    assert data['series'][0]['received']==2 and data['series'][-1]['received']==3
    assert data['block_rate'] is None

def test_filter_rate_never_uses_legacy_success_or_old_block_counts(client):
    signin(client);t=int(time.time())//60*60
    for metric,value in [('success',1000),('blocked',200),('filter_success',8),('filter_blocked',2)]:add('user-a',t,metric,value)
    data=client.get('/api/statistics').json()
    assert data['totals']['blocked']==200 and data['block_rate']==25
    assert data['series'][-1]['block_rate']==25
    assert all(x['block_rate'] is None for x in data['series'][:-1])

def test_count_filter_pair_same_minute_and_flush(client,monkeypatch):
    signin(client);mg.pending.clear();t=int(time.time())//60*60
    monkeypatch.setattr(mg.time,'time',lambda:t+59)
    mg.count_filtered('user-a',True);mg.count_filtered('user-a',False)
    data=stats.report(m.db,mg,'24h','user-a')
    assert data['totals']['filter_success']==2 and data['totals']['filter_blocked']==1
    assert data['totals']['blocked']==1 and data['block_rate']==50

def test_blocklist_attribution_counts_exclusive_and_overlap_without_domains(client,monkeypatch):
    signin(client);mg.pending.clear();t=int(time.time())//60*60
    monkeypatch.setattr(mg.time,'time',lambda:t+30)
    mg.count_filtered('user-a',True,('hagezi_multi_pro',))
    mg.count_filtered('user-a',True,('hagezi_multi_pro','hagezi_tif_medium','unknown'))
    mg.count_filtered('user-a',True,('hagezi_tif_medium',))
    data=stats.report(m.db,mg,'24h','user-a')
    by_id={x['id']:x for x in data['blocklists']}
    assert data['blocklist_attributed']==3 and data['blocklist_overlap']==1
    assert by_id['hagezi_multi_pro']=={'id':'hagezi_multi_pro','label':'HaGeZi Multi Pro','hits':2,'only':1,'shared':1}
    assert by_id['hagezi_tif_medium']['hits']==2 and by_id['hagezi_tif_medium']['only']==1
    with m.db() as c:
        metrics=[r[0] for r in c.execute("SELECT metric FROM usage WHERE metric LIKE 'blocklist_%'")]
    assert all('example.com' not in metric for metric in metrics)

def test_page_controls_empty_state_and_validation(client):
    signin(client)
    for period in stats.PERIODS:
        r=client.get('/statistics?period='+period)
        assert r.status_code==200 and '所选时间内暂无统计记录' in r.text
        assert '<svg' in r.text and 'statistics.js' in r.text and 'data-trace="received"' in r.text
    assert client.get('/api/statistics?period=365d').status_code==422
    assert client.get('/statistics?period=invalid').status_code==422

def test_rate_chart_does_not_join_across_missing_samples(client):
    signin(client);data=stats.report(m.db,mg,'24h','user-a')
    data['series'][0]['block_rate']=20;data['series'][2]['block_rate']=40
    c=stats.chart(data);assert len(c['rate_segments'])==2 and len(c['rate_dots'])==2

def test_migration_does_not_retimestamp_or_backfill(client):
    signin(client);t=int(time.time())//60*60;add('user-a',t,'blocked',5)
    with m.db() as c:before=c.execute('SELECT applied FROM schema_migrations WHERE version=3').fetchone()[0]
    mg.migrate(m.db)
    with m.db() as c:
        assert c.execute('SELECT applied FROM schema_migrations WHERE version=3').fetchone()[0]==before
        assert c.execute("SELECT count(*) FROM usage WHERE metric='filter_success'").fetchone()[0]==0

def test_csv_own_scope_bom_and_null_rate(client):
    assert client.get('/statistics.csv').status_code==401
    signin(client);t=int(time.time())//60*60
    add('user-a',t,'received',4);add('other',t,'received',500)
    r=client.get('/statistics.csv?account=other')
    assert r.status_code==200 and r.content.startswith(b'\xef\xbb\xbf')
    rows=list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig'))))
    assert len(rows)==24 and sum(int(x['received']) for x in rows)==4
    assert all(x['filter_block_rate_pct']=='' for x in rows)
    assert 'attachment;' in r.headers['content-disposition'] and r.headers['cache-control']=='no-store'

def test_admin_account_scope_csv_links_and_missing_account(client):
    signin(client);t=int(time.time())//60*60
    with m.db() as c:c.execute("INSERT INTO users VALUES('other','=sensitive formula',?)",(t,))
    add('user-a',t,'received',3);add('other',t,'received',9)
    assert client.get('/admin/statistics.csv?account=other').status_code==403
    make_admin()
    assert client.get('/api/admin/statistics?account=other').json()['totals']['received']==9
    assert client.get('/api/admin/statistics').json()['totals']['received']==12
    r=client.get('/admin/statistics.csv?period=7d&account=other')
    rows=list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig'))))
    assert len(rows)==7 and sum(int(x['received']) for x in rows)==9
    assert '=sensitive' not in r.text
    page=client.get('/admin/statistics?account=other').text
    assert 'period=30d&amp;account=other' in page
    assert '/admin/statistics.csv?period=24h&amp;account=other' in page
    for path in ['/admin/statistics','/api/admin/statistics','/admin/statistics.csv']:
        assert client.get(path+'?account=missing').status_code==404
    with m.db() as c:c.execute("UPDATE account_settings SET is_admin=0 WHERE sub='user-a'")
    assert client.get('/admin/statistics.csv?account=other').status_code==403
