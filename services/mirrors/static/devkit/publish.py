#!/usr/bin/env python3
import json, mimetypes, os, pathlib, secrets, urllib.request
base=os.getenv("MATCHALL_MIRRORS_URL","https://mirrors.maximoraverse.org").rstrip("/")
token=os.environ["MATCHALL_MIRRORS_TOKEN"]; path=pathlib.Path(os.environ["MATCHALL_ARTIFACT"])
boundary="----matchall"+secrets.token_hex(12); fields={k:os.getenv(v,d) for k,v,d in [
("project_slug","MATCHALL_PROJECT",""),("version","MATCHALL_VERSION",""),("channel","MATCHALL_CHANNEL","stable"),
("os_name","MATCHALL_OS","any"),("arch","MATCHALL_ARCH","any"),("notes","MATCHALL_NOTES",""),
("rollout_percentage","MATCHALL_ROLLOUT","100")]}
parts=[]
for k,v in fields.items(): parts += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()]
parts += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"upload\"; filename=\"{path.name}\"\r\nContent-Type: {mimetypes.guess_type(path.name)[0] or 'application/octet-stream'}\r\n\r\n".encode(),path.read_bytes(),b"\r\n",f"--{boundary}--\r\n".encode()]
req=urllib.request.Request(base+"/api/v1/developer/releases/upload",data=b"".join(parts),method="POST",
 headers={"Authorization":"Bearer "+token,"Content-Type":"multipart/form-data; boundary="+boundary})
with urllib.request.urlopen(req,timeout=300) as r: print(json.dumps(json.load(r),ensure_ascii=False))
