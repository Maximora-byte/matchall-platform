from pathlib import Path
import re, shutil
base='https://www.maximoraverse.org'
mapping={'privacy':'privacy/policy','terms':'terms','contact':'contact','refund':'refund','pricing':'pricing'}
def replace(s):
 for old,new in mapping.items():
  for host in ['auth','proxyservice']:
   s=re.sub(r'https://'+host+r'\.maximoraverse\.org/'+old+r'/?(?=["\'<>\s])',base+'/'+new+'/',s)
 for old in ['privacy','terms']:
  s=re.sub(r'https://drive\.maximoraverse\.org/'+old+r'/?(?=["\'<>\s])',base+'/legal/drive-'+old+'/',s)
 return s
# stage static files and source templates
for root in [Path('/tmp/legal-stage'),Path('main/privacy-page'),Path('main/hub-platform/templates'),Path('main/mirror-platform/templates')]:
 for p in root.rglob('*'):
  if p.is_file() and p.suffix in ['.html','.js']:
   s=p.read_text();new=replace(s)
   if new!=s:p.write_text(new)
# brand root HTML copies staged separately
brand=Path('/tmp/legal-brand');brand.mkdir(exist_ok=True)
for p in Path('/srv/personal-blog/drive').glob('*.html'):
 s=p.read_text();new=replace(s)
 # policy links on branded account/network/drive landing pages can be relative
 for old,newpath in mapping.items():
  target='legal/drive-'+old if p.name.startswith('drive-') and old in ['privacy','terms'] else newpath
  new=re.sub(r'href="/'+old+r'/?"',f'href="{base}/{target}/"',new)
 if new!=s:(brand/p.name).write_text(new)
# same-origin URLs inside remaining historical policy documents, maintained for rollback/cache
# old route handlers become compatibility redirects
p=Path('/srv/personal-blog/Caddyfile');s=p.read_text()
for prefix in ['account','proxy']:
 for old,newpath in mapping.items():
  pattern=r'  handle @'+prefix+'_'+old+r' \{.*?\n  \}'
  s,n=re.subn(pattern,'  handle @'+prefix+'_'+old+' {\n    redir '+base+'/'+newpath+'/ 308\n  }',s,flags=re.S);assert n==1,(prefix,old,n)
for old in ['privacy','terms']:
 pattern=r'  handle @'+old+r' \{.*?\n  \}'
 s,n=re.subn(pattern,'  handle @'+old+' {\n    redir '+base+'/legal/drive-'+old+'/ 308\n  }',s,flags=re.S);assert n==1
Path('/tmp/legal-Caddyfile').write_text(s)
# public sitemap adds new pages; old hosts omit their redirected policy pages
p=Path('/tmp/legal-stage/seo/main.sitemap.xml');s=p.read_text()
for path in list(mapping.values())+['legal/drive-privacy','legal/drive-terms']:
 url=base+'/'+path+'/'
 if url not in s:s=s.replace('</urlset>',f'  <url><loc>{url}</loc><lastmod>2026-09-26</lastmod></url>\n</urlset>')
p.write_text(s)
for name in ['auth','proxy','drive']:
 p=Path('/tmp/legal-stage/seo/'+name+'.sitemap.xml');s=p.read_text();s=re.sub(r'\s*<url>\s*<loc>https://[^<]+/(?:privacy|terms|contact|refund|pricing)/?</loc>.*?</url>','',s,flags=re.S);p.write_text(s)
