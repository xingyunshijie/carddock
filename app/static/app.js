let currentView='ingest',previewData=null,previewSequence=0,deviceList=[],deviceSequence=0;const batchSelection=new Set();
const $=id=>document.getElementById(id);let selected='',state={},terminalStates=new Map(),soundReady=false,authInfo={mode:'legacy',enabled:true},browseCallback,browseKind,browseParent='',browseCurrent='',browseDisplay='',browseSequence=0;
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const size=n=>{let i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toFixed(i?1:0)+' '+['B','KB','MB','GB','TB'][i]};
function notice(t,error=false){$('notice').textContent=t;$('notice').style.display='block';$('notice').className=error?'error':''}
async function api(path,data,token=sessionStorage.getItem('token')||''){const r=await fetch('/api/'+path,{method:data?'POST':'GET',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const j=await r.json();if(!r.ok){const error=Error(j.error||r.statusText);error.status=r.status;throw error;}return j}
function guard(fn){return async()=>{try{await fn()}catch(e){notice(e.message,true)}}}
function displayPath(value){const map=state.storage_path_map||{};for(const key of Object.keys(map).sort((a,b)=>b.length-a.length)){if(value===key||value.startsWith(key+'/'))return map[key]+value.slice(key.length)}return value}
function setMode(auto){$('modeAuto').checked=!!auto;$('modeManual').checked=!auto}
function updateCopyFlow(){const n=$('backups').value.split('\n').filter(x=>x.trim()).length;$('copyFlow').textContent=n?($('backup_from_primary').checked?'存储卡 → 主盘校验 → '+n+' 份备份':'存储卡 → 主盘及 '+n+' 份备份，分别校验'):'存储卡 → 主文件夹校验完成';$('clearBackup').disabled=!n;renderCopyMode()}
const stringFields=['primary','brand','model','verify','project','card','directory_template','filename_template','extensions','date_from','date_to','conflict'];
const boolFields=['media_only','keep_parents','exclude_proxies','classify','backup_from_primary'];
function settings(){const c={auto:$('modeAuto').checked,backups:$('backups').value.split('\n').map(x=>x.trim()).filter(Boolean),camera:$('camera_name').value.trim()};for(const k of stringFields)c[k]=$(k).value.trim();for(const k of boolFields)c[k]=$(k).checked;return c}
function fillSettings(c){setMode(c.auto);for(const k of stringFields)$(k).value=k==='primary'?displayPath(c[k]??''):(c[k]??'');for(const k of boolFields)$(k).checked=!!c[k];$('camera_name').value=c.camera||'';$('backups').value=c.backups.map(displayPath).join('\n');updateCopyFlow()}
async function save(extra={}){state.config=await api('config',{...settings(),...extra});setMode(state.config.auto);updateAuto()}
function updateAuto(){$('auto').textContent=state.config?.auto?'自动导入已开启 · 点击暂停':'开启自动导入'}
const cameraBrands={Sony:'索尼',Canon:'佳能',Nikon:'尼康',Panasonic:'松下',ARRI:'ARRI',DJI:'大疆',GoPro:'GoPro',Insta360:'Insta360',Apple:'Apple'};
function sourceBrandLabel(d){
 const brands=[...new Set([...(d.brands||[]),d.brand].filter(Boolean))];
 if(brands.length>1)return brands.map(b=>cameraBrands[b]||b).join(' / ');
 return d.overview||(brands.length?cameraBrands[brands[0]]||brands[0]:'未识别相机');
}
async function devices(){
 const sequence=++deviceSequence,found=await api('devices');if(sequence!==deviceSequence)return;const list=found.filter(d=>d.external===true);
 deviceList=list;for(const path of [...batchSelection])if(!list.some(d=>d.path===path))batchSelection.delete(path);
 $('sourceStatus').textContent=list.some(d=>d.external)?`已识别 ${list.filter(d=>d.external).length} 个外接存储`:'未发现外接存储，可刷新或手动添加';
 $('devices').innerHTML=list.map((d,i)=>`<div class="source-row"><input type="checkbox" data-batch="${i}" aria-label="排队选择 ${esc(d.display_name||d.name)}" ${batchSelection.has(d.path)?'checked':''}><button class="card ${selected===d.path?'selected':''}" data-i="${i}" aria-pressed="${selected===d.path}"><b><svg class="device-icon" viewBox="0 0 32 28" aria-hidden="true"><path d="M7 4h18l5 17a3 3 0 0 1-3 4H5a3 3 0 0 1-3-4L7 4Z"/><path d="M4 18h24"/><circle cx="24" cy="22" r=".8"/></svg>${esc(d.external?sourceBrandLabel(d):d.name)}</b><span>${d.external?'外接存储':'素材目录'} · ${size(d.total)}</span><span>${esc(d.display_name||d.evidence)}</span>${!d.external&&d.brand?`<span>${esc(sourceBrandLabel(d))}</span>`:''}${d.model?`<span class="device-model">${esc(d.model)}</span>`:''}${d.inferred&&d.brand?'<span class="device-evidence">根据目录 / 格式识别</span>':''}<span class="device-path">${esc(displayPath(d.path))}</span></button></div>`).join('')||'<p class="hint">请先在 NAS 文件管理器确认存储卡已挂载。</p>';
 $('devices').querySelectorAll('button').forEach(b=>b.onclick=guard(()=>{setView('ingest');return select(list[Number(b.dataset.i)].path)}));
 $('devices').querySelectorAll('[data-batch]').forEach(c=>c.onchange=()=>{const path=list[Number(c.dataset.batch)].path;c.checked?batchSelection.add(path):batchSelection.delete(path);updateBatch()});
 updateBatch();updateFooter();
}
async function select(path){
 const sequence=++previewSequence;selected=path;$('selected').textContent=displayPath(path);$('preview').innerHTML='<div class="empty">正在扫描文件…</div>';
 await devices();const d=await api('preview?path='+encodeURIComponent(path));if(sequence!==previewSequence)return;
 previewData=d;$('summaryBytes').textContent=size(d.bytes);$('summaryCount').textContent=d.count.toLocaleString();
 $('camera').textContent=d.camera.overview||[d.camera.brand,d.camera.model].filter(Boolean).join(' ')||'未识别设备';
 const categories=Object.entries(d.counts).filter(([,v])=>v>0);
 $('fileFilters').innerHTML='<button data-category="" class="active">全部</button>'+categories.map(([k,v])=>`<button data-category="${esc(k)}">${esc(k)} ${v}</button>`).join('');
 renderPreview();
}
function renderPreview(){
 if(!previewData)return;
 const query=$('fileSearch').value.trim().toLowerCase(),category=$('fileFilters').querySelector('.active')?.dataset.category||'';
 const rows=previewData.files.filter(f=>(!category||f.category===category)&&(!query||f.path.toLowerCase().includes(query)));
 $('preview').innerHTML=`<div class="path">${esc(displayPath(selected))}</div><table><thead><tr><th>文件</th><th>类型</th><th>大小</th></tr></thead><tbody>${rows.map(f=>`<tr><td>${esc(f.path)}</td><td class="file-kind">${esc(f.category||'其他')}</td><td>${size(f.size)}</td></tr>`).join('')}</tbody></table>${rows.length?'':'<p class="hint">没有符合搜索条件的预览文件。</p>'}<p class="hint">共 ${previewData.count} 项；预览与搜索显示前 200 项，拷贝处理全部符合归档规则的文件。</p>`;
}
const timeLabel=n=>`${Math.floor(n/60)} 分 ${Math.max(0,Math.round(n%60))} 秒`;
function renderJobs(){
 const shown=(state.jobs||[]).filter(j=>currentView==='history'?!['queued','running','paused','pausing','stopping'].includes(j.status):['queued','running','paused','pausing','stopping'].includes(j.status));
 $('jobs').innerHTML=shown.length?shown.map(j=>{
  const active=['queued','running','pausing','paused','stopping'].includes(j.status),fraction=j.stage_fraction??(j.total?j.done/j.total:0);
  const stage=j.stage==='copy'?'拷贝':j.stage==='verify'?'校验':j.stage==='size'?'大小复核':j.status==='completed'?'完成':'处理';
  return `<div class="job"><div class="job-top"><b>${esc(j.source.split('/').pop())} <span class="muted">${esc(j.id)}</span></b><span class="${j.status==='failed'?'error':''}">${esc(j.phase)}</span></div><div class="progress"><div style="width:${Math.max(0,Math.min(100,fraction*100))}%"></div></div><p><strong>${stage} ${active?(j.stage_done??j.done):j.done} / ${active?(j.stage_total??j.total):j.total}</strong> · 当前阶段 ${Math.round(fraction*100)}% · 总体已校验 ${j.done} / ${j.total} · ${esc(j.options.verify.toUpperCase())}</p><p class="path">${esc(j.current_file||'')}</p><p>实际写入 ${size(j.transferred_bytes||0)} · ${j.status==='paused'?'已暂停':`${!active?'已结束':j.stage==='copy'?'实时 '+size(j.realtime_bps||0)+'/s':'校验中'} · 平均 ${size(j.speed_bps||0)}/s`} · 已用 ${timeLabel(j.elapsed_seconds||0)}${j.eta_seconds!=null?' · 预计剩余 '+timeLabel(j.eta_seconds)+'（不含待校验）':''} · 新拷贝 ${j.copied} · 复核跳过 ${j.skipped}</p><p>${Object.entries(j.destinations||{}).map(([p,s])=>esc(p)+'：'+({pending:'等待',running:'处理中',verified:'✓ 已校验',failed:'失败',cancelled:'已终止','skipped-conflict':'有未备份项'}[s]||s)).join('<br>')}</p>${j.primary_verified&&active?'<p class="safe">主拷贝所选范围已复核，正在处理后续任务；请等待全部副本完成。</p>':''}${j.safe_to_remove?'<p class="safe">✓ 全部目标内容校验完成；核对报告后，在 NAS 系统中安全弹出。</p>':''}${j.error?`<p class="error">${esc(j.error)}</p>`:''}${['running','pausing','paused'].includes(j.status)?`<button class="task-control" data-job="${esc(j.id)}" data-action="${['paused','pausing'].includes(j.status)?'resume':'pause'}">${['paused','pausing'].includes(j.status)?'继续':'暂停'}</button> <button class="task-control" data-job="${esc(j.id)}" data-action="stop">终止并释放文件</button> `:''}${!active?`<button class="retry" data-job="${esc(j.id)}">按原规则重试</button> `:''}${!active||j.status==='queued'?`<button class="remove" data-job="${esc(j.id)}">删除队列记录</button> `:''}${['json','txt','checksums','mhl','html','log'].map(f=>`<button class="export" data-job="${esc(j.id)}" data-format="${f}">${({json:'JSON',txt:'TXT',checksums:'校验清单',mhl:'MHL',html:'打印 / PDF',log:'传输日志'})[f]}</button>`).join(' ')}</div>`
 }).join(''):'<div class="empty">还没有导入任务</div>';
 for(const j of state.jobs){const old=terminalStates.get(j.id);if(old&&old!==j.status&&!['queued','running','paused','pausing','stopping'].includes(j.status)&&$('completionSound').checked)playSound(j.status==='completed');terminalStates.set(j.id,j.status)}
}
async function poll(initial=false){state=await api('state');$('connection').textContent='● NAS 1.6.2 · 服务在线';$('watchStatus').textContent=state.watch_status||'等待插卡';if(initial)fillSettings(state.config);updateAuto();$('start').disabled=state.active;$('runQueue').disabled=state.active;renderJobs();renderLiveProgress();updateFooter();if(state.scan_error)notice('自动扫描：'+state.scan_error,true)}
async function browse(path=''){
 const sequence=++browseSequence;$('browsePath').disabled=true;browseCurrent='';$('browseUse').disabled=true;$('newFolder').disabled=true;$('browseError').textContent='';$('directories').textContent='正在读取目录…';
 try{
  const d=await api('browse?kind='+browseKind+'&path='+encodeURIComponent(path));if(sequence!==browseSequence)return;
  browseCurrent=d.path;browseParent=d.parent;$('browseHelp').textContent=browseKind==='source'?'请选择来源位置，再进入所需文件夹。':(d.shared_folders?'所有存储区列出此 NAS 已授权的共享文件夹。请选择主拷贝或备份要使用的文件夹。':'当前只有默认存储位置。安装时开放 NAS 共享目录后，这里会显示共享文件夹列表。');$('newFolderRow').hidden=browseKind!=='target';$('newFolder').disabled=browseKind!=='target'||!d.path||!d.writable;browseDisplay=d.display_path||d.path;$('browsePath').value=browseDisplay;$('browseUp').disabled=!d.path;$('browseRoot').disabled=false;$('browseGo').disabled=!d.path;
  $('browseUse').disabled=!d.path||(browseKind==='target'&&!d.writable);
  if(d.path&&browseKind==='target'&&!d.writable)$('browseError').textContent='当前目录没有写入权限，请选择其他目录。';
  $('directories').innerHTML=d.entries.map((e,i)=>`<button data-i="${i}" ${e.readable===false?'disabled':''}><strong>▱ ${esc(e.name)}</strong><span class="path">${esc(e.display_path||e.path)}</span>${e.total!==undefined?`<span class="hint">可用 ${size(e.free)} / 总容量 ${size(e.total)}</span>`:''}${e.readable===false?'<span class="hint">无读取权限，请在NAS中授权</span>':browseKind==='target'&&!e.writable?'<span class="hint">只读</span>':''}</button>`).join('')||'<p class="hint">'+(d.path?'没有子目录，可使用当前目录。':'暂无可访问的存储区。')+'</p>';
  $('directories').querySelectorAll('button').forEach(b=>b.onclick=()=>browse(d.entries[Number(b.dataset.i)].path));
 }catch(e){if(sequence!==browseSequence)return;$('directories').textContent='';$('browseError').textContent=e.message.includes('超出允许')?'这个路径尚未开放给影像归仓。请选择下方已开放的位置；使用其他共享目录前需先在 NAS Docker 项目中开放访问。':e.message;$('browseRoot').disabled=false;}finally{if(sequence===browseSequence)$('browsePath').disabled=false}
}
async function openBrowser(kind,callback,title=''){browseKind=kind;browseCallback=callback;$('browserTitle').textContent=kind==='target'?(title||'选择拷贝目录'):'选择数据源文件夹';$('browser').showModal();await browse()}
function clearAuthError(){$('authError').textContent='';$('authToken').removeAttribute('aria-invalid')}
$('login').onclick=()=>{clearAuthError();$('authDialog').showModal();$('authToken').focus()};
$('authClose').onclick=()=>{$('authToken').value='';clearAuthError();$('authDialog').close()};
$('authToken').oninput=clearAuthError;
$('authSubmit').onclick=async()=>{
 if($('authSubmit').disabled)return;
 clearAuthError();let candidate=$('authToken').value;
 if(!candidate){$('authError').textContent=authInfo.mode==='password'?'请输入登录密码':'请输入访问密钥';$('authToken').focus();return}
 if(authInfo.mode==='password'&&([...candidate].length<8||[...candidate].length>256)){$('authError').textContent='登录密码至少8位，最多256位，请检查后重新输入。';$('authToken').setAttribute('aria-invalid','true');$('authToken').focus();return}
 $('authSubmit').disabled=true;$('authSubmit').textContent='连接中…';
 try{
  if(authInfo.mode==='password'){const result=await api('login',{password:candidate},'');candidate=result.token}else{await api('state',undefined,candidate)}
  sessionStorage.setItem('token',candidate);
  await poll(true);await devices();$('logout').hidden=authInfo.mode!=='password';$('authToken').value='';$('authDialog').close();$('notice').style.display='none';showInitialSetup();
 }catch(error){
  $('authError').textContent=error.status===401?'密码错误':'连接失败，请检查 NAS 服务或网络后重试。';
  $('authToken').setAttribute('aria-invalid','true');$('authToken').focus();$('authToken').select();
 }finally{$('authSubmit').disabled=false;$('authSubmit').textContent=authInfo.mode==='password'?'登录':'连接'}
};
$('authToken').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('authSubmit').click()}};
$('refresh').onclick=guard(devices);$('save').onclick=guard(async()=>{await save();notice(state.config.auto?'已保存自动模式：插卡后自动导入，无需打开网页；当前已接入的摄影卡也会开始导入。':'已保存手动模式：识别卡片后，点击开始拷贝才会运行。')});$('auto').onclick=guard(async()=>{await save({auto:!state.config.auto});notice(state.config.auto?'自动导入已开启：现有和新接入的已识别卡片将依次导入':'自动导入已暂停，正在进行的任务会继续')});$('start').onclick=guard(async()=>{if(!selected)throw Error('请先选择数据源');await save();await api('jobs',{source:selected});await poll()});
$('addSource').onclick=guard(()=>openBrowser('source',async path=>{await api('config',{manual_sources:[...new Set([...(state.config.manual_sources||[]),path])]});await poll();await select(path)}));
$('choosePrimary').onclick=guard(()=>openBrowser('target',async p=>{$('primary').value=displayPath(p);renderCopyMode()},'选择主拷贝目录'));$('chooseBackup').onclick=guard(()=>openBrowser('target',async p=>{$('backups').value=displayPath(p);updateCopyFlow()},'选择备份拷贝目录'));$('closeBrowser').onclick=()=>$('browser').close();$('browseRoot').onclick=()=>browse();$('browseUp').onclick=()=>browse(browseParent);$('browsePath').oninput=()=>{browseCurrent='';$('browseUse').disabled=true;$('browseGo').disabled=!$('browsePath').value.trim()};$('browseGo').onclick=guard(()=>browse($('browsePath').value.trim()));$('browsePath').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();if(!$('browseGo').disabled)$('browseGo').click()}};$('browseUse').onclick=guard(async()=>{const p=browseCurrent;if(!p||browseDisplay!==$('browsePath').value)throw Error('请先打开并确认目录');await browseCallback(p);$('browser').close()});
guard(async()=>{authInfo=await api('auth');if(authInfo.mode==='password'){$('login').textContent=authInfo.enabled?'登录':'认证未启用';document.querySelector('.admin-link').hidden=true}else{document.querySelector('.admin-link').hidden=false;$('login').textContent='访问密钥';$('authTitle').textContent='连接旧版实例';$('authHint').textContent='此实例未设置新的密码认证参数，沿用原访问密钥。';$('authLabel').textContent='访问密钥'}try{await poll(true);await devices();$('logout').hidden=authInfo.mode!=='password'||!authInfo.enabled;showInitialSetup()}catch(e){if(e.status===401&&authInfo.mode==='password'){$('authDialog').showModal();$('authToken').focus()}else throw e}})();setInterval(()=>poll().catch(e=>{$('connection').textContent='● 未连接';notice(e.message,true)}),2500);setInterval(()=>devices().catch(()=>{}),12000);

$('jobs').addEventListener('click',e=>{if(e.target.matches('.report'))guard(async()=>{const report=await api('report?id='+e.target.dataset.job);const u=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='carddock-'+report.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)})()});

$('jobs').addEventListener('click',e=>{if(e.target.matches('.task-control'))guard(async()=>{const action=e.target.dataset.action;await api('control',{id:e.target.dataset.job,action});if(action==='stop'){setMode(false);notice('正在终止任务，同时暂停自动导入。请等待文件释放提示后在 NAS 中弹出。')}await poll()})()});

$('clearBackup').onclick=()=>{$('backups').value='';updateCopyFlow()};$('backups').oninput=updateCopyFlow;updateCopyFlow();

$('previewRules').onclick=guard(async()=>{await save();if(selected)await select(selected)});
$('enqueue').onclick=guard(async()=>{if(!selected)throw Error('请先选择数据源');await save();await api('jobs',{source:selected,enqueue:true});await poll();notice('已按当前规则加入队列；每项规则单独保存')});
$('runQueue').onclick=guard(async()=>{await api('queue/start',{});await poll()});
$('jobs').addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.matches('.retry'))guard(async()=>{await api('retry',{id:b.dataset.job});await poll()})();
 if(b.matches('.remove'))guard(async()=>{await api('remove',{id:b.dataset.job});await poll();notice('已删除记录，素材与已导出报告保留')})();
 if(b.matches('.export'))guard(async()=>{const r=await fetch('/api/report?id='+encodeURIComponent(b.dataset.job)+'&format='+b.dataset.format,{headers:{Authorization:'Bearer '+(sessionStorage.getItem('token')||'')}});if(!r.ok){const j=await r.json();throw Error(j.error)}const blob=await r.blob(),url=URL.createObjectURL(blob);if(b.dataset.format==='html'){const w=window.open(url,'_blank');if(!w)notice('浏览器阻止弹窗，请允许后重试');setTimeout(()=>URL.revokeObjectURL(url),60000)}else{const a=document.createElement('a');a.href=url;a.download='carddock-'+b.dataset.job+'.'+({checksums:'checksums.txt'}[b.dataset.format]||b.dataset.format);a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}})();
});
async function refreshPresets(){const data=await api('presets');$('presetList').innerHTML='<option value="">选择已保存的预设</option>'+Object.keys(data).map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');return data}
$('presetSave').onclick=guard(async()=>{await api('presets',{name:$('presetName').value,options:settings()});await refreshPresets();notice('预设已保存')});
$('presetLoad').onclick=guard(async()=>{const data=await refreshPresets(),name=$('presetName').value||$('presetList').dataset.choice;if(!data[name])throw Error('请选择已保存预设');fillSettings({...data[name],auto:false});await save();notice('预设已应用，自动导入保持关闭')});
$('presetList').onchange=()=>{$('presetList').dataset.choice=$('presetList').value;$('presetName').value=$('presetList').value};
$('presetList').onfocus=guard(refreshPresets);
$('presetExport').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify({...settings(),auto:false},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='CardDock-NAS-工作流设置.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
$('presetImport').onchange=guard(async()=>{const f=$('presetImport').files[0];if(!f)return;if(f.size>65536)throw Error('设置文件过大');const c=JSON.parse(await f.text());await api('config',{...c,auto:false});await poll(true);notice('设置已导入，请核对来源和目标')});
function theme(){const mode=$('theme').value,dark=mode==='dark'||mode==='system'&&matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.dataset.theme=dark?'dark':'light';localStorage.setItem('carddock-theme',mode)}
$('theme').value=localStorage.getItem('carddock-theme')||'light';$('theme').onchange=theme;theme();matchMedia('(prefers-color-scheme: dark)').addEventListener('change',theme);
function playSound(ok=true){try{const C=window.AudioContext||window.webkitAudioContext,ctx=new C(),o=ctx.createOscillator(),g=ctx.createGain();o.type='sine';o.frequency.value=ok?660:220;g.gain.setValueAtTime(.12,ctx.currentTime);g.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+.5);o.connect(g);g.connect(ctx.destination);o.start();o.stop(ctx.currentTime+.5);o.onended=()=>ctx.close()}catch(e){notice('浏览器未允许播放提示音')}}
$('soundTest').onclick=()=>playSound();$('completionSound').checked=localStorage.getItem('carddock-sound')==='1';$('completionSound').onchange=()=>{localStorage.setItem('carddock-sound',$('completionSound').checked?'1':'0');if($('completionSound').checked)playSound()};

$('newFolder').onclick=async()=>{try{if(!browseCurrent||browseKind!=='target')throw Error('请先点击下方的可写位置');const r=await api('mkdir',{parent:browseCurrent,name:$('newFolderName').value});$('newFolderName').value='';await browse(r.path)}catch(e){$('browseError').textContent=e.message}};

$('backup_from_primary').onchange=updateCopyFlow;

$('logout').onclick=guard(async()=>{await api('logout',{});sessionStorage.removeItem('token');$('logout').hidden=true;$('authDialog').showModal();$('authToken').focus()});

function showInitialSetup(){
 if(state.config?.setup_complete!==false||$('initialSetup').open)return;
 $('setupPrimary').value=displayPath(state.config.primary||'');
 $('setupBackups').value=(state.config.backups||[]).map(displayPath).join('\n');
 $('setupError').textContent='';$('initialSetup').showModal();$('setupChoosePrimary').focus();
}
$('initialSetup').oncancel=e=>e.preventDefault();
$('setupChoosePrimary').onclick=guard(()=>openBrowser('target',p=>{$('setupPrimary').value=displayPath(p);$('setupError').textContent=''},'选择主拷贝目录'));
$('setupChooseBackup').onclick=guard(()=>openBrowser('target',p=>{$('setupBackups').value=displayPath(p);$('setupError').textContent=''},'选择备份拷贝目录'));
$('setupClearBackup').onclick=()=>{$('setupBackups').value=''};
$('setupSave').onclick=async()=>{
 const button=$('setupSave');if(button.disabled)return;
 const primary=$('setupPrimary').value.trim(),backups=$('setupBackups').value.split('\n').filter(Boolean);
 $('setupError').textContent='';
 if(!primary){$('setupError').textContent='请先选择拷贝主目录。';$('setupChoosePrimary').focus();return}
 if(backups.includes(primary)){$('setupError').textContent='备份目录不能与主目录相同，请重新选择。';return}
 button.disabled=true;button.textContent='正在保存…';
 try{
  state.config=await api('config',{primary,backups,auto:false,setup_complete:true});
  fillSettings(state.config);updateAuto();$('initialSetup').close();notice('目录已保存，可以选择来源开始拷贝。');
 }catch(e){$('setupError').textContent=e.message}
 finally{button.disabled=false;button.textContent='保存并进入'}
};

function setView(view){
 currentView=view;document.body.dataset.view=view;
 const panels={ingest:'ingestPanel',queue:'historyPanel',history:'historyPanel',workflow:'workflowPanel',preferences:'preferencesPanel',help:'helpPanel'};
 for(const id of new Set(Object.values(panels)))$(id).hidden=id!==panels[view];
 document.querySelectorAll('.workspace-nav [data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);if(b.dataset.view===view)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});
 if(view==='queue'||view==='history'){$('historyTitle').textContent=view==='queue'?'任务队列':'拷贝记录';$('runQueue').hidden=view==='history';renderJobs()}
}
function renderCopyMode(){
 const algorithm=$('verify').value,backup=$('backups').value.trim(),mode=algorithm==='quick'?'quick':backup?'dual':'safe';
 document.querySelectorAll('[data-copy-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.copyMode===mode);b.setAttribute('aria-pressed',b.dataset.copyMode===mode)});
 $('modeHint').textContent=algorithm==='quick'?'只检查文件大小，不执行内容哈希校验。完整性优先请用安全校验。':backup?'主盘内容校验完成，再生成并校验一份备份。':'逐个比较文件内容，确认拷贝完整。';
 $('modeHint').classList.toggle('warning',algorithm==='quick');$('verifyRow').hidden=algorithm==='quick';
 $('summaryVerify').textContent=algorithm==='quick'?'快速':backup?'双盘':'安全';
 $('summaryVerifyHint').textContent=algorithm==='quick'?'仅大小检查':algorithm.toUpperCase()+' 内容校验';
 const primary=$('primary').value.trim();$('primaryName').textContent=primary?primary.split('/').filter(Boolean).pop():'选择主拷贝目录';
 $('backupName').textContent=backup?backup.split('/').filter(Boolean).pop():'添加一份备份';
 updateFooter();
}
function updateFooter(){
 $('footerCounts').textContent=`${deviceList.length} 个数据源 · ${$('primary').value.trim()?1+Number(!!$('backups').value.trim()):0} 个拷贝目标`;
}
function updateBatch(){$('batchQueue').textContent='批量排队 · '+batchSelection.size;$('batchQueue').disabled=!batchSelection.size||!!state.active}
function liveJob(){return (state.jobs||[]).find(j=>['running','paused','pausing','stopping'].includes(j.status))||(state.jobs||[])[0]}
function renderLiveProgress(){
 const j=liveJob();if(!j){$('liveControls').hidden=true;return}
 const active=['running','paused','pausing','stopping'].includes(j.status),fraction=j.stage_fraction??(j.total?j.done/j.total:0),percent=Math.max(0,Math.min(100,Math.round(fraction*100)));
 $('liveStage').textContent=j.phase||j.status;$('livePercent').textContent=percent+'%';$('liveBar').style.width=percent+'%';$('liveBar').parentElement.setAttribute('aria-valuenow',percent);
 $('liveLabel').textContent=j.stage==='verify'?'校验进度':j.stage==='copy'?'拷贝进度':'任务进度';
 $('liveSpeed').textContent=active&&j.stage==='copy'?size(j.realtime_bps||0)+'/s':'';
 $('liveFile').textContent=j.current_file||displayPath(j.source);$('liveFile').title=$('liveFile').textContent;
 $('liveCount').textContent=`${active?(j.stage_done??j.done):j.done} / ${active?(j.stage_total??j.total):j.total}${j.eta_seconds!=null?' · 约 '+timeLabel(j.eta_seconds):''}`;
 $('liveControls').hidden=!active;$('livePause').textContent=['paused','pausing'].includes(j.status)?'继续':'暂停';
 updateBatch();
}
document.querySelectorAll('[data-view]').forEach(b=>{if(b.tagName==='BUTTON')b.onclick=()=>setView(b.dataset.view)});
$('fileSearch').oninput=renderPreview;$('fileFilters').onclick=e=>{const b=e.target.closest('[data-category]');if(!b)return;for(const x of $('fileFilters').children)x.classList.toggle('active',x===b);renderPreview()};
$('verify').onchange=renderCopyMode;$('primary').oninput=renderCopyMode;
document.querySelectorAll('[data-copy-mode]').forEach(b=>b.onclick=()=>{if(b.dataset.copyMode==='dual'){if($('verify').value==='quick')$('verify').value='sha256';if(!$('backups').value.trim())$('chooseBackup').click()}else if(b.dataset.copyMode==='quick')$('verify').value='quick';else if($('verify').value==='quick')$('verify').value='sha256';renderCopyMode()});
$('targetAdd').onclick=()=>$('chooseBackup').click();$('addSourceTile').onclick=()=>$('addSource').click();$('emptyChooseSource').onclick=()=>$('addSource').click();
$('saveTargets').onclick=()=>$('save').click();
$('selectAll').onclick=()=>{deviceList.forEach(d=>batchSelection.add(d.path));devices().catch(e=>notice(e.message,true))};
$('clearSelection').onclick=()=>{batchSelection.clear();devices().catch(e=>notice(e.message,true))};
$('batchQueue').onclick=guard(async()=>{await save();for(const source of [...batchSelection])await api('jobs',{source,enqueue:true});batchSelection.clear();await devices();await poll();setView('queue');notice('所选数据源已加入队列；空闲时立即开始，其余任务依次执行')});
for(const id of ['livePause','liveStop'])$(id).onclick=guard(async()=>{const j=liveJob();if(!j)return;const action=id==='liveStop'?'stop':['paused','pausing'].includes(j.status)?'resume':'pause';await api('control',{id:j.id,action});if(action==='stop')setMode(false);await poll()});
renderCopyMode();

$('saveAutoMode').onclick=guard(async()=>{await save();notice(state.config.auto?'已保存自动模式，将导入当前与新接入的已识别存储卡':'已保存手动模式，点击开始拷贝才会运行')});
