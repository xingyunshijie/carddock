const $=id=>document.getElementById(id);let selected='',state={},terminalStates=new Map(),soundReady=false,authInfo={mode:'legacy',enabled:true},browseCallback,browseKind,browseParent='',browseCurrent='',browseSequence=0;
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const size=n=>{let i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toFixed(i?1:0)+' '+['B','KB','MB','GB','TB'][i]};
function notice(t,error=false){$('notice').textContent=t;$('notice').style.display='block';$('notice').className=error?'error':''}
async function api(path,data,token=sessionStorage.getItem('token')||''){const r=await fetch('/api/'+path,{method:data?'POST':'GET',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const j=await r.json();if(!r.ok){const error=Error(j.error||r.statusText);error.status=r.status;throw error;}return j}
function guard(fn){return async()=>{try{await fn()}catch(e){notice(e.message,true)}}}
function setMode(auto){$('modeAuto').checked=!!auto;$('modeManual').checked=!auto}
function updateCopyFlow(){const n=$('backups').value.split('\n').filter(x=>x.trim()).length;$('copyFlow').textContent=n?($('backup_from_primary').checked?'存储卡 → 主盘校验 → '+n+' 份备份':'存储卡 → 主盘及 '+n+' 份备份，分别校验'):'存储卡 → 主文件夹校验完成';$('clearBackup').disabled=!n}
const stringFields=['primary','brand','model','verify','project','card','directory_template','filename_template','extensions','date_from','date_to','conflict'];
const boolFields=['media_only','keep_parents','exclude_proxies','classify','backup_from_primary'];
function settings(){const c={auto:$('modeAuto').checked,backups:$('backups').value.split('\n').map(x=>x.trim()).filter(Boolean),camera:$('camera_name').value.trim()};for(const k of stringFields)c[k]=$(k).value.trim();for(const k of boolFields)c[k]=$(k).checked;return c}
function fillSettings(c){setMode(c.auto);for(const k of stringFields)$(k).value=c[k]??'';for(const k of boolFields)$(k).checked=!!c[k];$('camera_name').value=c.camera||'';$('backups').value=c.backups.join('\n');updateCopyFlow()}
async function save(extra={}){state.config=await api('config',{...settings(),...extra});setMode(state.config.auto);updateAuto()}
function updateAuto(){$('auto').textContent=state.config?.auto?'自动导入已开启 · 点击暂停':'开启自动导入'}
async function devices(){const list=await api('devices');$('devices').innerHTML=list.length?list.map((d,i)=>`<button class="card ${selected===d.path?'selected':''}" data-i="${i}"><b>▣ ${esc(d.display_name||d.name)}</b><span>${size(d.total)} · ${esc(d.brand||'未识别品牌')} ${esc(d.model)}</span><span>${esc(d.evidence)}${d.external?'':' · 手动目录'}</span><span>${esc(d.path)}</span>${d.external?`<span>${esc(d.origin_evidence)}</span>`:''}</button>`).join(''):'<div class="empty">尚未发现存储卡<br><br>插入读卡器，或手动添加媒体目录</div>';$('devices').querySelectorAll('button').forEach(b=>b.onclick=guard(()=>select(list[Number(b.dataset.i)].path)))}
async function select(path){selected=path;$('selected').textContent=path;$('preview').innerHTML='<div class="empty">正在扫描文件…</div>';await devices();const d=await api('preview?path='+encodeURIComponent(path));$('camera').textContent=d.camera.overview||[d.camera.brand,d.camera.model].filter(Boolean).join(' ')||'未识别';$('preview').innerHTML=`<h3>${esc(path.split('/').pop())}</h3><div class="path">${esc(path)}</div><div class="stats"><div class="stat"><b>${d.count}</b><span>文件总数</span></div><div class="stat"><b>${size(d.bytes)}</b><span>文件总体积</span></div></div><p class="hint">${Object.entries(d.counts).map(([k,v])=>esc(k)+' '+v).join(' · ')}</p><table><thead><tr><th>文件</th><th>类型</th><th>大小</th></tr></thead><tbody>${d.files.map(f=>`<tr><td>${esc(f.path)}</td><td>${esc(f.category)}</td><td>${size(f.size)}</td></tr>`).join('')}</tbody></table><p class="hint">预览最多显示 200 项；拷贝处理全部符合条件的文件。</p>`}
const timeLabel=n=>`${Math.floor(n/60)} 分 ${Math.max(0,Math.round(n%60))} 秒`;
function renderJobs(){
 $('jobs').innerHTML=state.jobs.length?state.jobs.map(j=>{
  const active=['queued','running','pausing','paused','stopping'].includes(j.status),fraction=j.stage_fraction??(j.total?j.done/j.total:0);
  const stage=j.stage==='copy'?'拷贝':j.stage==='verify'?'校验':j.stage==='size'?'大小复核':j.status==='completed'?'完成':'处理';
  return `<div class="job"><div class="job-top"><b>${esc(j.source.split('/').pop())} <span class="muted">${esc(j.id)}</span></b><span class="${j.status==='failed'?'error':''}">${esc(j.phase)}</span></div><div class="progress"><div style="width:${Math.max(0,Math.min(100,fraction*100))}%"></div></div><p><strong>${stage} ${active?(j.stage_done??j.done):j.done} / ${active?(j.stage_total??j.total):j.total}</strong> · 当前阶段 ${Math.round(fraction*100)}% · 总体已校验 ${j.done} / ${j.total} · ${esc(j.options.verify.toUpperCase())}</p><p class="path">${esc(j.current_file||'')}</p><p>实际写入 ${size(j.transferred_bytes||0)} · ${j.status==='paused'?'已暂停':`${!active?'已结束':j.stage==='copy'?'实时 '+size(j.realtime_bps||0)+'/s':'校验中'} · 平均 ${size(j.speed_bps||0)}/s`} · 已用 ${timeLabel(j.elapsed_seconds||0)}${j.eta_seconds!=null?' · 预计剩余 '+timeLabel(j.eta_seconds)+'（不含待校验）':''} · 新拷贝 ${j.copied} · 复核跳过 ${j.skipped}</p><p>${Object.entries(j.destinations||{}).map(([p,s])=>esc(p)+'：'+({pending:'等待',running:'处理中',verified:'✓ 已校验',failed:'失败',cancelled:'已终止','skipped-conflict':'有未备份项'}[s]||s)).join('<br>')}</p>${j.primary_verified&&active?'<p class="safe">主拷贝所选范围已复核，正在处理后续任务；请等待全部副本完成。</p>':''}${j.safe_to_remove?'<p class="safe">✓ 全部目标内容校验完成；核对报告后，在 NAS 系统中安全弹出。</p>':''}${j.error?`<p class="error">${esc(j.error)}</p>`:''}${['running','pausing','paused'].includes(j.status)?`<button class="task-control" data-job="${esc(j.id)}" data-action="${['paused','pausing'].includes(j.status)?'resume':'pause'}">${['paused','pausing'].includes(j.status)?'继续':'暂停'}</button> <button class="task-control" data-job="${esc(j.id)}" data-action="stop">终止并释放文件</button> `:''}${!active?`<button class="retry" data-job="${esc(j.id)}">按原规则重试</button> `:''}${!active||j.status==='queued'?`<button class="remove" data-job="${esc(j.id)}">删除队列记录</button> `:''}${['json','txt','checksums','mhl','html','log'].map(f=>`<button class="export" data-job="${esc(j.id)}" data-format="${f}">${({json:'JSON',txt:'TXT',checksums:'校验清单',mhl:'MHL',html:'打印 / PDF',log:'传输日志'})[f]}</button>`).join(' ')}</div>`
 }).join(''):'<div class="empty">还没有导入任务</div>';
 for(const j of state.jobs){const old=terminalStates.get(j.id);if(old&&old!==j.status&&!['queued','running','paused','pausing','stopping'].includes(j.status)&&$('completionSound').checked)playSound(j.status==='completed');terminalStates.set(j.id,j.status)}
}
async function poll(initial=false){state=await api('state');$('connection').textContent='● NAS V1.0 构建4 · 服务在线';$('watchStatus').textContent=state.watch_status||'等待插卡';if(initial)fillSettings(state.config);updateAuto();$('start').disabled=state.active;$('runQueue').disabled=state.active;renderJobs();if(state.scan_error)notice('自动扫描：'+state.scan_error,true)}
async function browse(path=''){
 const sequence=++browseSequence;$('browsePath').disabled=true;browseCurrent='';$('browseUse').disabled=true;$('newFolder').disabled=true;$('browseError').textContent='';$('directories').textContent='正在读取目录…';
 try{
  const d=await api('browse?kind='+browseKind+'&path='+encodeURIComponent(path));if(sequence!==browseSequence)return;
  browseCurrent=d.path;browseParent=d.parent;$('newFolderRow').hidden=browseKind!=='target';$('newFolder').disabled=browseKind!=='target'||!d.path||!d.writable;$('browsePath').value=d.path;$('browseUp').disabled=!d.path;
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
 clearAuthError();let candidate=$('authToken').value;
 if(!candidate){$('authError').textContent=authInfo.mode==='password'?'请输入登录密码':'请输入访问密钥';$('authToken').focus();return}
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
$('choosePrimary').onclick=guard(()=>openBrowser('target',async p=>{$('primary').value=p}));$('chooseBackup').onclick=guard(()=>openBrowser('target',async p=>{$('backups').value=[$('backups').value.trim(),p].filter(Boolean).join('\n');updateCopyFlow()}));$('closeBrowser').onclick=()=>$('browser').close();$('browseRoot').onclick=()=>browse();$('browseUp').onclick=()=>browse(browseParent);$('browsePath').oninput=()=>{browseCurrent='';$('browseUse').disabled=true};$('browseGo').onclick=guard(()=>browse($('browsePath').value));$('browseUse').onclick=guard(async()=>{const p=browseCurrent;if(!p||p!==$('browsePath').value)throw Error('请先打开并确认目录');await browseCallback(p);$('browser').close()});
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

$('newFolder').onclick=guard(async()=>{if(!browseCurrent||browseKind!=='target')throw Error('请先选择可写存储区');const r=await api('mkdir',{parent:browseCurrent,name:$('newFolderName').value});$('newFolderName').value='';await browse(r.path)});

$('backup_from_primary').onchange=updateCopyFlow;

$('logout').onclick=guard(async()=>{await api('logout',{});sessionStorage.removeItem('token');$('logout').hidden=true;$('authDialog').showModal();$('authToken').focus()});

function showInitialSetup(){
 if(state.config?.setup_complete!==false||$('initialSetup').open)return;
 $('setupPrimary').value=state.config.primary||'';
 $('setupBackups').value=(state.config.backups||[]).join('\n');
 $('setupError').textContent='';$('initialSetup').showModal();$('setupChoosePrimary').focus();
}
$('initialSetup').oncancel=e=>e.preventDefault();
$('setupChoosePrimary').onclick=guard(()=>openBrowser('target',p=>{$('setupPrimary').value=p;$('setupError').textContent=''}));
$('setupChooseBackup').onclick=guard(()=>openBrowser('target',p=>{$('setupBackups').value=[...new Set([...$('setupBackups').value.split('\n').filter(Boolean),p])].join('\n');$('setupError').textContent=''}));
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
