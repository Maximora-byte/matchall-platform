"""Host-only administrator binding; never exposed as a browser-controlled claim."""
import argparse
import app as m
import management as mg
p=argparse.ArgumentParser();p.add_argument('sub');p.add_argument('--revoke',action='store_true');args=p.parse_args()
m.init_db();mg.migrate(m.db)
with m.db() as c:
    c.execute('BEGIN IMMEDIATE')
    row=c.execute('SELECT is_admin FROM account_settings WHERE sub=?',(args.sub,)).fetchone()
    if not row:raise SystemExit('Unknown immutable OIDC subject')
    value=0 if args.revoke else 1
    c.execute('UPDATE account_settings SET is_admin=? WHERE sub=?',(value,args.sub))
    mg.audit(c,'host-operator',args.sub,'admin.binding',{'is_admin':row[0]},{'is_admin':value})
print('Role binding updated; effective on next management request.')
