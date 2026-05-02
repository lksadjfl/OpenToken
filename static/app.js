async function api(url, options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...options});return {ok:r.ok,data:await r.json()};}
async function loadHealth(){const r=await api('/health');document.getElementById('health').textContent='Health: '+(r.ok?'OK':'FAIL');}
async function loadKeys(){const r=await api('/api/keys');const rows=document.getElementById('keyRows');rows.innerHTML='';(r.data||[]).forEach(k=>{rows.innerHTML+=`<tr><td>${k.name}</td><td>${k.key_mask}</td><td>${k.permissions}</td><td>${k.created_at}</td></tr>`;});}
async function loadLogs(){const r=await api('/api/logs');document.getElementById('logs').textContent=JSON.stringify(r.data,null,2);}
document.getElementById('createKey').onclick=async()=>{const name=document.getElementById('keyName').value;const permissions=document.getElementById('perm').value;await api('/api/keys',{method:'POST',body:JSON.stringify({name,permissions})});loadKeys();};
document.getElementById('send').onclick=async()=>{const model=document.getElementById('model').value;const prompt=document.getElementById('prompt').value;const r=await api('/api/playground',{method:'POST',body:JSON.stringify({model,prompt})});document.getElementById('resp').textContent=JSON.stringify(r.data,null,2);loadLogs();};
document.getElementById('reload').onclick=loadLogs;loadHealth();loadKeys();loadLogs();
