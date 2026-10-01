import fs from "node:fs"; import path from "node:path";
const file=process.env.MATCHALL_ARTIFACT, form=new FormData();
for(const [k,v] of Object.entries({project_slug:"MATCHALL_PROJECT",version:"MATCHALL_VERSION",channel:"MATCHALL_CHANNEL",os_name:"MATCHALL_OS",arch:"MATCHALL_ARCH",notes:"MATCHALL_NOTES",rollout_percentage:"MATCHALL_ROLLOUT"})) form.set(k,process.env[v]||({channel:"stable",os_name:"any",arch:"any",rollout_percentage:"100"}[k]||""));
form.set("upload",new Blob([fs.readFileSync(file)]),path.basename(file));
const r=await fetch((process.env.MATCHALL_MIRRORS_URL||"https://mirrors.maximoraverse.org")+"/api/v1/developer/releases/upload",{method:"POST",headers:{Authorization:"Bearer "+process.env.MATCHALL_MIRRORS_TOKEN},body:form});
if(!r.ok) throw new Error(await r.text()); console.log(await r.text());
