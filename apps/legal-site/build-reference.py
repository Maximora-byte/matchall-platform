from pathlib import Path
import re,html
root=Path('/tmp/legal-stage');base='https://www.maximoraverse.org'
pages=[('privacy/policy','proxy-privacy.html','完整隐私政策','PRIVACY POLICY','理解信息如何被处理，\n从一份清楚的说明开始。'),('terms','proxy-terms.html','服务条款','TERMS OF SERVICE','清晰的规则，\n让每一次使用更安心。'),('contact','proxy-contact.html','联系与支持','CONTACT & SUPPORT','有问题，\n从这里找到我们。'),('refund','proxy-refund.html','退款政策','REFUND POLICY','关于退款，\n先把流程和边界说清。'),('pricing','proxy-pricing.html','定价说明','PRICING','了解费用，\n再选择适合你的服务。'),('legal/drive-privacy','privacy.html','网盘隐私政策','DRIVE PRIVACY','你的文件，\n有专门的数据说明。'),('legal/drive-terms','terms.html','网盘使用条款','DRIVE TERMS','存储与分享，\n遵循清晰的使用规则。')]
links={'privacy':'privacy/policy','terms':'terms','contact':'contact','refund':'refund','pricing':'pricing'}
for path,filename,title,english,intro in pages:
 raw=Path('/srv/personal-blog/drive-site',filename).read_text();body=re.search(r'<main[^>]*>(.*?)</main>',raw,re.S).group(1)
 body=re.sub(r'<h1>.*?</h1>','',body,count=1,flags=re.S)
 for old,new in links.items():
  dest='legal/drive-'+old if filename in ['privacy.html','terms.html'] and old in ['privacy','terms'] else new
  body=body.replace('href="/'+old+'"',f'href="/{dest}/"')
 headers=[]
 def heading(m):
  ident='section-'+str(len(headers)+1);label=re.sub('<[^>]*>','',m[1]);headers.append((ident,label));return f'<h2 id="{ident}">{m[1]}</h2>'
 body=re.sub(r'<h2>(.*?)</h2>',heading,body,flags=re.S)
 toc=''.join(f'<a href="#{i}">{t}</a>' for i,t in headers)
 nav=''.join(f'<a href="/{p}/"'+(' aria-current="page"' if p==path else '')+f'>{t}</a>' for p,_,t,_,_ in pages[:5])
 extra=''
 if path=='contact':extra='<div class="support-actions"><a class="button primary" href="https://proxyservice.maximoraverse.org/login">登录后提交工单 ↗</a><a class="button secondary" href="https://status.maximoraverse.org/">查看服务状态 ↗</a><a class="button secondary" href="https://docs.maximoraverse.org/">先查使用文档 ↗</a></div>'
 doc=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · MatchAll</title><meta name="description" content="MatchAll {title}。查看服务规则、数据说明与官方支持入口。"><link rel="canonical" href="{base}/{path}/"><meta property="og:title" content="{title} · MatchAll"><meta property="og:url" content="{base}/{path}/"><meta name="theme-color" content="#f7f8f5"><link rel="icon" href="/assets/brand/favicon.svg"><link rel="stylesheet" href="/privacy/privacy.css?v=20260926b"><link rel="stylesheet" href="/assets/legal-pages.css?v=20260926a"></head><body><a class="skip" href="#main">跳到主要内容</a><header class="topbar"><div class="nav-wrap"><a class="brand" href="/"><img src="/assets/brand/matchall-symbol.svg" width="28" height="28" alt="">MatchAll</a><span class="nav-divider" aria-hidden="true"></span><span class="page-label">政策与支持</span><nav aria-label="主导航"><a href="/privacy/">隐私保护</a><a class="nav-policy" href="/contact/">联系支持 ↗</a></nav></div></header><main id="main" class="wrap legal-main"><div class="legal-hero"><p class="eyebrow">{english}</p><h1>{title}</h1><p class="legal-intro">{intro.replace(chr(10),'<br>')}</p>{extra}</div><nav class="legal-tabs" aria-label="政策与支持页面">{nav}</nav><div class="legal-layout"><aside class="legal-toc"><p>本页内容</p>{toc}<a class="toc-back" href="/privacy/">了解 MatchAll 隐私保护 ↗</a></aside><article class="legal-copy">{body}</article></div><div class="legal-help"><h2>还有疑问？</h2><p>通过官方支持渠道说明问题。请勿提交密码、验证码、订阅令牌或支付密钥。</p><a class="text-link" href="/contact/">联系与支持 →</a></div></main><footer class="wrap footer"><div class="footer-bottom"><span>© 2026 MatchAll · 政策与支持</span><nav aria-label="页脚"><a href="/privacy/">隐私保护</a><a href="/privacy/policy/">完整隐私政策</a><a href="/terms/">服务条款</a><a href="/contact/">联系</a></nav></div></footer></body></html>'''
 out=root/path;out.mkdir(parents=True,exist_ok=True);(out/'index.html').write_text(doc)
 # preserve exact legal body text (headings receive IDs and hyperlinks change destination only).
 def plain(x):return re.sub(r'\s+','',html.unescape(re.sub('<[^>]+>','',x)))
 orig=re.search(r'<main[^>]*>(.*?)</main>',raw,re.S).group(1);orig=re.sub(r'<h1>.*?</h1>','',orig,count=1,flags=re.S)
 assert plain(orig)==plain(body),path
print('PASS seven legal bodies preserved verbatim after markup normalization')
