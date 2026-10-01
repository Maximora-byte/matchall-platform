import datetime,hashlib,json,os,sqlite3,tarfile
from pathlib import Path
os.umask(0o077)
root=Path('/srv/personal-blog/dns-platform')
dest=Path('/mnt/data/matchall-dns/backups')/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
dest.mkdir(parents=True,exist_ok=False)
with sqlite3.connect('/mnt/data/matchall-dns/portal-data/dns.sqlite3') as src, sqlite3.connect(dest/'dns.sqlite3') as out:
    src.backup(out)
    assert out.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
with tarfile.open(dest/'config.tar.gz','w:gz') as tar:
    for p in (root/'secrets',Path('/root/.openclaw/workspace/main/dns-platform'),Path('/srv/personal-blog/Caddyfile')):
        tar.add(p,arcname=str(p).lstrip('/'),filter=lambda info: None if '/.pytest_cache' in info.name or '/__pycache__' in info.name else info)
(dest/'SHA256SUMS').write_text(''.join(hashlib.sha256((dest/name).read_bytes()).hexdigest()+'  '+name+'\n' for name in ['dns.sqlite3','config.tar.gz']))
print(dest)
