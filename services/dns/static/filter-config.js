(() => {
  const input=document.getElementById('config-file'), raw=document.getElementById('config-raw'), status=document.getElementById('config-file-status');
  if(!input||!raw||!status)return;
  input.addEventListener('change',async()=>{
    const file=input.files[0];raw.value='';
    if(!file)return;
    if(file.size>800000){status.textContent='文件超过 800 KB，请检查文件。';input.value='';return;}
    try {const text=await file.text();JSON.parse(text);raw.value=text;status.textContent='文件已读入，点击预览检查具体变更。';}
    catch {status.textContent='无法读取有效的 JSON 文件。';}
  });
})();
