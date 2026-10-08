const $=id=>document.getElementById(id);let selected='',state={},browseCallback,browseKind,browseParent='',browseCurrent='',browseSequence=0;
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const size=n=>{let i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toFixed(i?1:0)+' '+['B','KB','MB','GB','TB'][i]};
function notice(t,error=false){$('notice').textContent=t;$('notice').style.display='block';$('notice').className=error?'error':''}
async function api(path,data,token=sessionStorage.getItem('token')||''){const r=await fetch('/api/'+path,{method:data?'POST':'GET',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const j=await r.json();if(!r.ok){const error=Error(j.error||r.statusText);error.status=r.status;throw error;}return j}
function guard(fn){return async()=>{try{await fn()}catch(e){notice(e.message,true)}}}
function setMode(auto){$('modeAuto').checked=!!auto;$('modeManual').checked=!auto}
function updateCopyFlow(){$('copyFlow').textContent=$('backups').value.trim()?'存储卡 → 主文件夹校验 → 备份文件夹校验':'存储卡 → 主文件夹校验完成';$('clearBackup').disabled=!$('backups').value}
function settings(){return {auto:$('modeAuto').checked,primary:$('primary').value.trim(),backups:[$('backups').value.trim()].filter(Boolean),brand:$('brand').value,model:$('model').value.trim(),verify:$('verify').value,media_only:$('media_only').checked,keep_parents:$('keep_parents').checked}}
async function save(extra={}){state.config=await api('config',{...settings(),...extra});setMode(state.config.auto);updateAuto()}
function updateAuto(){$('auto').textContent=state.config?.auto?'自动导入已开启 · 点击暂停':'开启自动导入'}
async function devices(){const list=await api('devices');$('devices').innerHTML=list.length?list.map((d,i)=>`<button class="card ${selected===d.path?'selected':''}" data-i="${i}"><b>▣ ${esc(d.display_name||d.name)}</b><span>${size(d.total)} · ${esc(d.brand||'未识别品牌')} ${esc(d.model)}</span><span>${esc(d.evidence)}${d.external?'':' · 手动目录'}</span><span>${esc(d.path)}</span>${d.external?`<span>${esc(d.origin_evidence)}</span>`:''}</button>`).join(''):'<div class="empty">尚未发现存储卡<br><br>插入读卡器，或手动添加媒体目录</div>';$('devices').querySelectorAll('button').forEach(b=>b.onclick=guard(()=>select(list[Number(b.dataset.i)].path)))}
async function select(path){selected=path;$('selected').textContent=path;$('preview').innerHTML='<div class="empty">正在扫描文件…</div>';await devices();const d=await api('preview?path='+encodeURIComponent(path));$('camera').textContent=[d.camera.brand,d.camera.model].filter(Boolean).join(' ')||'未识别';$('preview').innerHTML=`<h3>${esc(path.split('/').pop())}</h3><div class="path">${esc(path)}</div><div class="stats"><div class="stat"><b>${d.count}</b><span>文件总数</span></div><div class="stat"><b>${size(d.bytes)}</b><span>文件总体积</span></div></div><p class="hint">${Object.entries(d.counts).map(([k,v])=>esc(k)+' '+v).join(' · ')}</p><table><thead><tr><th>文件</th><th>类型</th><th>大小</th></tr></thead><tbody>${d.files.map(f=>`<tr><td>${esc(f.path)}</td><td>${esc(f.category)}</td><td>${size(f.size)}</td></tr>`).join('')}</tbody></table><p class="hint">预览最多显示 200 项；拷贝处理全部符合条件的文件。</p>`}
async function poll(initial=false){state=await api('state');$('connection').textContent='● NAS 服务在线';$('watchStatus').textContent=state.watch_status||'等待插卡';if(initial){setMode(state.config.auto);for(const k of ['primary','brand','model','verify'])$(k).value=state.config[k];$('backups').value=state.config.backups.join('\n');updateCopyFlow();for(const k of ['media_only','keep_parents'])$(k).checked=state.config[k]}updateAuto();$('start').disabled=state.active;$('jobs').innerHTML=state.jobs.length?state.jobs.map(j=>`<div class="job"><div class="job-top"><b>${esc(j.source.split('/').pop())} <span class="muted">${esc(j.id)}</span></b><span class="${j.status==='failed'?'error':''}">${esc(j.phase)}</span></div><div class="progress"><div style="width:${j.total?Math.min(100,j.done/j.total*100):0}%"></div></div><p>${j.done} / ${j.total} 文件步骤 · ${size(j.bytes_done)} / ${size(j.bytes_total)} · 新拷贝 ${j.copied} · 跳过 ${j.skipped} · ${esc(j.options.verify.toUpperCase())}</p><p>实际写入 ${size(j.transferred_bytes||0)} · ${j.status==='paused'?'已暂停':`平均 ${size(j.speed_bps||0)}/s`} <span class="hint">（含校验耗时，不含暂停）</span></p><p>${Object.entries(j.destinations||{}).map(([p,s])=>esc(p)+'：'+({pending:'等待',running:'处理中',verified:'✓ 已校验',failed:'失败',cancelled:'已终止'}[s]||s)).join('<br>')}</p>${j.safe_to_remove?'<p class="safe">✓ 主文件夹校验完成，可拔出存储卡（操作系统卸载仍请在 NAS 中执行）</p>':''}${j.error?`<p class="error">${esc(j.error)}</p>`:''}${['queued','running','pausing','paused'].includes(j.status)?`<button class="task-control" data-job="${esc(j.id)}" data-action="${['paused','pausing'].includes(j.status)?'resume':'pause'}">${['paused','pausing'].includes(j.status)?'继续':'暂停'}</button> <button class="task-control" data-job="${esc(j.id)}" data-action="stop">终止并释放存储卡</button> `:''}${j.status==='stopping'?'<p>正在关闭文件，请等待终止完成后弹出。</p>':''}${j.status==='cancelled'&&j.io_released?'<p class="safe">已停止读写并关闭任务文件。请在 NAS 中安全弹出存储卡；任务已终止，完成情况请查看各目标校验记录。</p>':''}<button class="report" data-job="${esc(j.id)}">导出校验清单</button></div>`).join(''):'<div class="empty">还没有导入任务</div>';if(state.scan_error)notice('自动扫描：'+state.scan_error,true)}
async function browse(path=''){
 const sequence=++browseSequence;$('browsePath').disabled=true;browseCurrent='';$('browseUse').disabled=true;$('browseError').textContent='';$('directories').textContent='正在读取目录…';
 try{
  const d=await api('browse?kind='+browseKind+'&path='+encodeURIComponent(path));if(sequence!==browseSequence)return;
  browseCurrent=d.path;browseParent=d.parent;$('browsePath').value=d.path;$('browseUp').disabled=!d.path;
  $('browseUse').disabled=!d.path||(browseKind==='target'&&!d.writable);
  if(d.path&&browseKind==='target'&&!d.writable)$('browseError').textContent='当前目录没有写入权限，请选择其他目录。';
  $('directories').innerHTML=d.entries.map((e,i)=>`<button data-i="${i}"><strong>▱ ${esc(e.name)}</strong><span class="path">${esc(e.path)}</span>${e.total!==undefined?`<span class="hint">可用 ${size(e.free)} / 总容量 ${size(e.total)}</span>`:''}${browseKind==='target'&&!e.writable?'<span class="hint">只读</span>':''}</button>`).join('')||'<p class="hint">'+(d.path?'没有子目录，可使用当前目录。':'暂无可访问的存储区。')+'</p>';
  $('directories').querySelectorAll('button').forEach(b=>b.onclick=()=>browse(d.entries[Number(b.dataset.i)].path));
 }catch(e){if(sequence!==browseSequence)return;$('directories').textContent='';$('browseError').textContent=e.message;}finally{if(sequence===browseSequence)$('browsePath').disabled=false}
}
async function openBrowser(kind,callback){browseKind=kind;browseCallback=callback;$('browserTitle').textContent=kind==='target'?'选择数据拷贝目标目录':'选择数据源文件夹';$('browser').showModal();await browse()}
function clearAuthError(){$('authError').textContent='';$('authToken').removeAttribute('aria-invalid')}
$('login').onclick=()=>{clearAuthError();$('authDialog').showModal();$('authToken').focus()};
$('authClose').onclick=()=>{$('authToken').value='';clearAuthError();$('authDialog').close()};
$('authToken').oninput=clearAuthError;
$('authSubmit').onclick=async()=>{
 if($('authSubmit').disabled)return;
 clearAuthError();const candidate=$('authToken').value;
 if(!candidate){$('authError').textContent='请输入访问密钥';$('authToken').focus();return}
 $('authSubmit').disabled=true;$('authSubmit').textContent='连接中…';
 try{
  await api('state',undefined,candidate);
  sessionStorage.setItem('token',candidate);
  await poll(true);await devices();$('authToken').value='';$('authDialog').close();$('notice').style.display='none';
 }catch(error){
  $('authError').textContent=error.status===401?'密码错误':'连接失败，请检查 NAS 服务或网络后重试。';
  $('authToken').setAttribute('aria-invalid','true');$('authToken').focus();$('authToken').select();
 }finally{$('authSubmit').disabled=false;$('authSubmit').textContent='连接'}
};
$('authToken').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('authSubmit').click()}};
$('refresh').onclick=guard(devices);$('save').onclick=guard(async()=>{await save();notice(state.config.auto?'已保存自动模式：插卡后自动导入，无需打开网页；当前已接入的摄影卡也会开始导入。':'已保存手动模式：识别卡片后，点击开始拷贝才会运行。')});$('auto').onclick=guard(async()=>{await save({auto:!state.config.auto});notice(state.config.auto?'自动导入已开启：现有和新接入的已识别卡片将依次导入':'自动导入已暂停，正在进行的任务会继续')});$('start').onclick=guard(async()=>{if(!selected)throw Error('请先选择数据源');await save();await api('jobs',{source:selected});await poll()});
$('addSource').onclick=guard(()=>openBrowser('source',async path=>{await api('config',{manual_sources:[...new Set([...(state.config.manual_sources||[]),path])]});await poll();await select(path)}));
$('choosePrimary').onclick=guard(()=>openBrowser('target',async p=>{$('primary').value=p}));$('chooseBackup').onclick=guard(()=>openBrowser('target',async p=>{$('backups').value=p;updateCopyFlow()}));$('closeBrowser').onclick=()=>$('browser').close();$('browseRoot').onclick=()=>browse();$('browseUp').onclick=()=>browse(browseParent);$('browsePath').oninput=()=>{browseCurrent='';$('browseUse').disabled=true};$('browseGo').onclick=guard(()=>browse($('browsePath').value));$('browseUse').onclick=guard(async()=>{const p=browseCurrent;if(!p||p!==$('browsePath').value)throw Error('请先打开并确认目录');await browseCallback(p);$('browser').close()});
guard(async()=>{await poll(true);await devices()})();setInterval(()=>poll().catch(e=>{$('connection').textContent='● 未连接';notice(e.message,true)}),2500);setInterval(()=>devices().catch(()=>{}),12000);

$('jobs').addEventListener('click',e=>{if(e.target.matches('.report'))guard(async()=>{const report=await api('report?id='+e.target.dataset.job);const u=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='carddock-'+report.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)})()});

$('jobs').addEventListener('click',e=>{if(e.target.matches('.task-control'))guard(async()=>{const action=e.target.dataset.action;await api('control',{id:e.target.dataset.job,action});if(action==='stop'){setMode(false);notice('正在终止任务，同时暂停自动导入。请等待文件释放提示后在 NAS 中弹出。')}await poll()})()});

$('clearBackup').onclick=()=>{$('backups').value='';updateCopyFlow()};$('backups').oninput=updateCopyFlow;updateCopyFlow();
