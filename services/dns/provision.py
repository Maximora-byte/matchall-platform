"""One-time secret provisioning; never prints secret values."""
import base64,os,secrets,shutil,datetime
from pathlib import Path
os.umask(0o077)
root=Path('/srv/personal-blog/dns-platform')
root.mkdir(exist_ok=False)
(root/'data').mkdir(mode=0o700)
(root/'secrets').mkdir(mode=0o700)
for p in [root/'data',root/'secrets']:os.chown(p,10001,10001)
oidc=secrets.token_urlsafe(48)
for name,value in [('oidc.secret',oidc),('token.key',base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())]:
    p=root/'secrets'/name;p.write_text(value);os.chown(p,10001,10001);p.chmod(0o400)
target=Path('/srv/authentik/data/matchall-dns-client.secret')
assert not target.exists()
target.write_text(oidc);target.chmod(0o600)
backup=Path('/srv/personal-blog/backups')/('dns-site-before-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
shutil.copy2('/srv/personal-blog/Caddyfile',backup/'Caddyfile')
print('Provisioned protected secrets; Caddy backup:',backup)
