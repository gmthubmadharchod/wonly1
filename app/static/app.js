const $=s=>document.querySelector(s);
const fmt=n=>{n=Number(n||0);const u=["B","KB","MB","GB","TB"];let i=0;while(n>=1024&&i<u.length-1){n/=1024;i++}return `${n.toFixed(i?1:0)} ${u[i]}`};
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
async function api(url,opt={}){const r=await fetch(url,{credentials:"include",...opt});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||"Request failed");return d}
function showMsg(e){const m=$("#msg");if(m)m.textContent=e.message}
document.addEventListener("DOMContentLoaded",()=>{
 const login=$("#login"), register=$("#register"), upload=$("#upload");
 if(login)login.onsubmit=async e=>{e.preventDefault();try{await api("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.fromEntries(new FormData(login)))});location="/dashboard.html"}catch(x){showMsg(x)}};
 if(register)register.onsubmit=async e=>{e.preventDefault();try{await api("/api/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.fromEntries(new FormData(register)))});location="/dashboard.html"}catch(x){showMsg(x)}};
 if($("#logout"))$("#logout").onclick=async()=>{await api("/api/auth/logout",{method:"POST"});location="/login.html"};
 if(upload)upload.onchange=async()=>{
   const f=upload.files[0]; if(!f)return;
   if(f.size>2147483648){alert("Maximum individual file size is 2 GiB.");upload.value="";return}
   const fd=new FormData(); fd.append("file",f); const folderId=$("#uploadFolder")?.value||""; if(folderId)fd.append("folder_id",folderId);
   const job=crypto.randomUUID?crypto.randomUUID():Date.now().toString(36);
   try{
     await uploadWithProgress("/api/files/upload",fd,job);
     upload.value=""; await loadFiles(); await loadMe();
   }catch(x){alert(x.message)}
 };
  if($("#urlImport"))$("#urlImport").onclick=async()=>{
   const url=prompt("Paste a direct file download URL:"); if(!url)return;
   const filename=prompt("Filename (optional):")||null;
   const job=crypto.randomUUID?crypto.randomUUID():Date.now().toString(36);
   try{
     showProgress("Starting remote import…",0);
     const r=await api("/api/files/import-url",{method:"POST",headers:{"Content-Type":"application/json","X-Upload-ID":job},body:JSON.stringify({url,filename,folder_id:$("#uploadFolder")?.value||null})});
     await waitProgress(job); await loadFiles(); await loadMe(); alert("Remote file imported.");
   }catch(e){alert(e.message)} finally{hideProgress()}
 };
  if($("#fileList")){loadMe();loadFiles();loadFolders()}
 if($("#newfolder"))$("#newfolder").onclick=async()=>{const n=prompt("Folder name");if(n?.trim()){await api("/api/folders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n.trim()})});loadFolders()}};
 if($("#users")){loadAdmin();loadAdminSettings();if($("#adminSearch"))$("#adminSearch").oninput=adminSearch;if($("#settingsForm"))$("#settingsForm").onsubmit=saveAdminSettings;}
 if($("#search"))$("#search").oninput=loadFiles;
});
async function loadMe(){
 try{
  const d=await api("/api/auth/me");
  if($("#usage"))$("#usage").textContent=fmt(d.used_storage)+" / "+(d.role==="admin"?"Unlimited":fmt(d.storage_limit));
  if($("#plan"))$("#plan").textContent=d.role==="admin"?"OWNER":d.plan.toUpperCase();
  if($("#bar"))$("#bar").style.width=d.role==="admin"?"0%":Math.min(100,d.used_storage/Math.max(1,d.storage_limit)*100)+"%";
  if($("#supportEmail"))$("#supportEmail").textContent=d.admin_email;
  if($("#supportLink"))$("#supportLink").href="mailto:"+d.admin_email;
  if(d.role==="admin"&&$("#adminLink"))$("#adminLink").style.display="inline";
  if($("#expiryNote"))$("#expiryNote").textContent=d.plan==="free"&&d.role!=="admin"?"Free files expire according to the cloud policy.":"No file expiry.";
 }catch(e){
  // Only redirect when the session itself is rejected.
  const msg=String(e.message||"").toLowerCase();
  if(msg.includes("401")||msg.includes("unauthorized")||msg.includes("not authenticated")||msg.includes("session")) location="/login.html";
  else console.error("SST /me:",e);
 }
}
async function loadFiles(){
 try{
  const d=await api("/api/files"),q=($("#search")?.value||"").toLowerCase();
  const list=d.files.filter(x=>x.name.toLowerCase().includes(q));
  if($("#fileList"))$("#fileList").innerHTML=list.map(x=>{
   const exp=x.expires_at?` · expires ${new Date(x.expires_at).toLocaleDateString()}`:" · no expiry";
   return `<div class="file"><div><div class="file-name">📄 ${esc(x.name)}</div><small class="muted">${x.size_text}${exp}</small></div><div class="status">${esc(x.mime||"file")}</div><div class="file-actions"><a href="${x.stream_url}" target="_blank" data-stream="1">▶ Stream</a><a href="${x.download_url}">↓ Download</a><button onclick="copyLink('${x.id}')">🔗 Link</button><button onclick="renameFile('${x.id}','${esc(x.name)}')">✏️ Rename</button><button onclick="deleteFile('${x.id}')">🗑️ Delete</button></div></div>`
  }).join("")||'<p class="muted">No files yet.</p>';
 }catch(e){if($("#fileList"))$("#fileList").innerHTML='<p class="muted">Unable to load files: '+esc(e.message)+'</p>'}
}
async function loadFolders(){
 try{
   const d=await api("/api/folders");
   const html=d.folders.map(x=>`<div class="folder"><span>📁 ${esc(x.name)}</span><span><button class="small" onclick="renameFolder('${x.id}','${esc(x.name)}')">✏️</button> <button class="small" onclick="deleteFolder('${x.id}')">🗑️</button></span></div>`).join("")||'<span class="muted">No folders yet.</span>';
   if($("#folderList"))$("#folderList").innerHTML=html;
   const sel=$("#uploadFolder");
   if(sel)sel.innerHTML='<option value="">Root folder</option>'+d.folders.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join("");
 }catch(e){}
}
async function saveAdminSettings(e){
 e.preventDefault();
 const f=e.target, o=Object.fromEntries(new FormData(f));
 o.free_storage_gb=Number(o.free_storage_gb);
 o.premium_storage_gb=Number(o.premium_storage_gb);
 o.max_user_quota_gb=Number(o.max_user_quota_gb);
 o.free_expiry_days=Number(o.free_expiry_days);
 try{
   await api("/api/admin/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(o)});
   $("#settingsMsg").textContent="✓ Settings saved. New admin password is active.";
   f.elements.admin_password.value="";
   loadAdmin();
 }catch(e){$("#settingsMsg").textContent=e.message}
}

function showProgress(text,pct){
 let box=document.getElementById("sstProgress");
 if(!box){box=document.createElement("div");box.id="sstProgress";box.style.cssText="position:fixed;left:16px;right:16px;bottom:18px;z-index:9999;background:#111827;color:#fff;padding:14px 16px;border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.25);font-family:system-ui";
 box.innerHTML='<div id="sstProgressText"></div><div style="height:8px;background:#374151;border-radius:99px;margin-top:10px;overflow:hidden"><div id="sstProgressBar" style="height:100%;width:0%;background:#60a5fa;transition:width .15s"></div></div>';
 document.body.appendChild(box)}
 document.getElementById("sstProgressText").textContent=text;
 document.getElementById("sstProgressBar").style.width=Math.max(0,Math.min(100,pct||0))+"%";
}
function hideProgress(){document.getElementById("sstProgress")?.remove()}
function uploadWithProgress(url,form,job){
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest(); xhr.open("POST",url); xhr.setRequestHeader("X-Upload-ID",job);
  xhr.upload.onprogress=e=>{if(e.lengthComputable)showProgress("Uploading to SST Cloud… "+Math.round(e.loaded/e.total*100)+"%",e.loaded/e.total*70)}
  xhr.onload=async()=>{
   let d={};try{d=JSON.parse(xhr.responseText)}catch{}
   if(xhr.status<200||xhr.status>=300){hideProgress();reject(new Error(d.detail||"Upload failed"));return}
   try{await waitProgress(job);resolve(d)}catch(e){reject(e)}finally{hideProgress()}
  };
  xhr.onerror=()=>{hideProgress();reject(new Error("Network error during upload"))};
  xhr.send(form);
 });
}
async function waitProgress(job){
 for(let i=0;i<3600;i++){
   const p=await api("/api/files/progress/"+encodeURIComponent(job));
   if(p.phase==="telegram_upload")showProgress("Saving to Telegram… "+Math.round(p.percent||0)+"%",70+(Number(p.percent||0)*0.3));
   else if(p.phase==="remote_download")showProgress("Downloading remote file… "+(p.total?Math.round(p.percent||0)+"%":"Receiving…"),p.total?Number(p.percent||0)*0.7:0);
   else if(p.phase==="complete"){showProgress("Complete ✓",100);return p}
   else if(p.phase==="error")throw new Error(p.error||"Upload failed");
   await new Promise(r=>setTimeout(r,500));
 }
 throw new Error("Upload timed out");
}

async function deleteFile(id){if(!confirm("Delete this file?"))return;try{await api("/api/files/"+id,{method:"DELETE"});await loadFiles();await loadMe()}catch(e){alert(e.message)}}
async function renameFile(id,current){const name=prompt("New filename:",current||"");if(!name?.trim())return;try{await api("/api/files/"+id,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name.trim()})});await loadFiles()}catch(e){alert(e.message)}}
async function renameFolder(id,current){const name=prompt("New folder name:",current||"");if(!name?.trim())return;try{await api("/api/folders/"+id,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name.trim()})});await loadFolders()}catch(e){alert(e.message)}}
async function deleteFolder(id){if(!confirm("Delete this folder? Files will become unfiled."))return;try{await api("/api/folders/"+id,{method:"DELETE"});await loadFolders();await loadFiles()}catch(e){alert(e.message)}}

async function copyLink(id){
 try{
  const d=await api("/api/files/"+id+"/link");
  const url=d.download_url;
  if(navigator.clipboard) await navigator.clipboard.writeText(url);
  else {const t=document.createElement("textarea");t.value=url;document.body.appendChild(t);t.select();document.execCommand("copy");t.remove();}
  alert("Download link copied.");
 }catch(e){alert(e.message)}
}
async function permanentLink(id){
 try{
  const d=await api("/api/files/"+id+"/permanent-link");
  if(navigator.clipboard) await navigator.clipboard.writeText(d.url);
  alert("Permanent link copied.");
 }catch(e){alert(e.message)}
}
