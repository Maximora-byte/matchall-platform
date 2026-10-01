"""Public dual-stack acceptance with a self-cleaning temporary account."""
import hashlib
import json
import plistlib
import secrets
import shlex
import subprocess
import time

import httpx

CONTAINER = 'matchall-dns-dns-portal-1'
BASE = 'https://dns.maximoraverse.org'
IPV4 = '64.110.101.75'
IPV6 = '2603:c023:16:c400:0:249e:4aa8:be5a'
TABLES = ['users', 'devices', 'account_settings', 'moddns_mapping', 'query_log_settings']


def inside(code):
    result = subprocess.run(
        ['docker', 'exec', '-i', CONTAINER, 'python', '-c', code],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError('fixture operation failed; inspect container locally')
    return result.stdout.strip()


def fingerprint():
    return inside(
        "import app as m,hashlib,json\n"
        "tables=" + repr(TABLES) + "\n"
        "with m.db() as c:\n"
        " state={t:[tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY 1')] for t in tables}\n"
        " print(hashlib.sha256(json.dumps(state,sort_keys=True,default=str).encode()).hexdigest())"
    )


def remote_doh(token):
    code = r'''import subprocess,sys
token=sys.stdin.read().strip()
name=b'\x07example\x03org\x00'
wire=b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'+name+b'\x00\x01\x00\x01'
url='https://dns.maximoraverse.org/dns-query/'+token
result=subprocess.run(['curl','-6','-fsS','--connect-timeout','6','--max-time','15','--resolve','dns.maximoraverse.org:443:[2603:c023:16:c400:0:249e:4aa8:be5a]','-H','Content-Type: application/dns-message','-H','Accept: application/dns-message','--data-binary','@-',url],input=wire,capture_output=True)
if result.returncode or len(result.stdout)<12:raise SystemExit('DoH request failed')
flags=int.from_bytes(result.stdout[2:4],'big')
if result.stdout[:2]!=b'\x12\x34' or not flags&0x8000 or flags&15:raise SystemExit('invalid DNS response')
print('DoH IPv6 rcode=NOERROR')'''
    subprocess.run(['ssh', 'hk', 'python3 -c ' + shlex.quote(code)], input=token, text=True, check=True)


sub = 'dual-stack-smoke-' + secrets.token_hex(8)
session = secrets.token_urlsafe(32)
before = fingerprint()
try:
    created = inside(
        "import app as m,time,json\n"
        "sub=" + repr(sub) + "\n"
        "session=" + repr(session) + "\n"
        "with m.db() as c:\n"
        " c.execute('INSERT INTO users VALUES(?,?,?)',(sub,'dual-stack acceptance',int(time.time())))\n"
        " c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(m.digest(session),sub,'csrf',int(time.time())+300))\n"
        "d=m.account_token(sub)\n"
        "print(json.dumps({'id':d['id'],'token':m.cipher().decrypt(d['token_enc'].encode()).decode()}))"
    )
    fixture = json.loads(created)
    cookies = {'__Host-dns_session': session}
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        account = client.get(BASE + '/', cookies=cookies)
        assert account.status_code == 200
        assert IPV4 in account.text and IPV6 in account.text
        assert 'IPv4 / IPv6 双栈服务器' in account.text
        guide = client.get(BASE + '/guide')
        assert guide.status_code == 200 and 'IPv4 / IPv6 双栈怎么配置' in guide.text
        profile = client.get(BASE + '/devices/' + fixture['id'] + '/profile.mobileconfig', cookies=cookies)
        assert profile.status_code == 200
        payload = plistlib.loads(profile.content)
        assert payload['PayloadContent'][0]['DNSSettings']['ServerAddresses'] == [IPV4, IPV6]
    remote_doh(fixture['token'])
    print('PASS public account, guide, Apple IPv4/IPv6 profile and DoH over native IPv6')
finally:
    inside(
        "import app as m\n"
        "sub=" + repr(sub) + "\n"
        "with m.db() as c:\n"
        " for t in ['query_history','query_log_settings','usage','devices','sessions']:\n"
        "  c.execute('DELETE FROM '+t+' WHERE sub=?',(sub,))\n"
        " c.execute('DELETE FROM audit WHERE actor=? OR target=?',(sub,sub))\n"
        " c.execute('DELETE FROM moddns_mapping WHERE sub=?',(sub,))\n"
        " c.execute('DELETE FROM account_settings WHERE sub=?',(sub,))\n"
        " c.execute('DELETE FROM users WHERE sub=?',(sub,))"
    )
    assert fingerprint() == before, 'existing account state changed'
    print('PASS cleanup and existing-account invariants')
