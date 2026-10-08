'use strict';
const VERSION='0.12.0-beta.1';
function validPath(value){
 const p=value.trim().replace(/\/+$/,'');
 if(!p.startsWith('/')||p==='/'||p.split('/').some(x=>x==='..'||x==='.')||/[\x00-\x1f:$]/.test(p))throw Error('请填写真实的绝对目录，禁止根目录、..、冒号和 $');
 return p;
}
function overlaps(a,b){return a===b||a.startsWith(b+'/')||b.startsWith(a+'/');}
function buildConfig(v){
 const source=validPath(v.source),primary=validPath(v.primary),state=validPath(v.state),backup=v.backup.trim()?validPath(v.backup):'';
 const extra=v.extra.split('\n').filter(p=>p.trim()).map(validPath),targets=[primary,...(backup?[backup]:[]),...extra];
 if(overlaps(source,state)||targets.some(p=>overlaps(p,source)||overlaps(p,state)))throw Error('源、目标、状态目录不能相同或互相包含');
 if(backup&&overlaps(primary,backup))throw Error('主文件夹与备份文件夹不能重合');
 const uid=Number(v.uid),gid=Number(v.gid),port=Number(v.port);
 if(![uid,gid].every(n=>Number.isInteger(n)&&n>0)||!Number.isInteger(port)||port<1||port>65535)throw Error('UID/GID 须为非 root 整数，端口须为 1–65535');
 if(!/^[A-Za-z0-9_./:@-]+$/.test(v.image))throw Error('镜像名称无效');
 if(!/^[A-Za-z0-9_-]{32,128}$/.test(v.key))throw Error('访问密钥无效');
 const bind=(s,t,ro=false,prop)=>({type:'bind',source:s,target:t,read_only:ro,bind:{create_host_path:false,...(prop?{propagation:prop}:{})}});
 const env={ACCESS_TOKEN:v.key,SOURCE_ROOTS:'/sources',TARGET_ROOTS:'/destinations/primary',STATE_DIR:'/state',HOST_MOUNTINFO:'/host/mountinfo'};
 const volumes=[bind(source,'/sources',true,'rslave'),bind(primary,'/destinations/primary'),bind(state,'/state'),bind('/proc/1/mountinfo','/host/mountinfo',true),bind('/sys','/sys',true)];
 const labels={'/destinations/primary':'主存储区 · '+primary};
 if(backup){env.TARGET_ROOTS+=':/destinations/backup';volumes.push(bind(backup,'/destinations/backup'));labels['/destinations/backup']='备份存储区 · '+backup;}
 extra.forEach((p,i)=>{const t='/storage/area'+(i+1);env.TARGET_ROOTS+=':'+t;volumes.push(bind(p,t));labels[t]=p;});
 env.TARGET_LABELS=JSON.stringify(labels);
 return {name:'carddock',services:{carddock:{image:v.image,restart:'unless-stopped',user:uid+':'+gid,ports:[port+':8080'],environment:env,volumes,read_only:true,tmpfs:['/tmp:size=64m'],cap_drop:['ALL'],security_opt:['no-new-privileges:true']}}};
}
if(typeof module!=='undefined')module.exports={buildConfig,validPath};
if(typeof document!=='undefined'){
 const $=id=>document.getElementById(id),bytes=new Uint8Array(32);crypto.getRandomValues(bytes);$('key').value=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
 $('show').onclick=()=>{$('key').type=$('key').type==='password'?'text':'password';};
 $('setup').onsubmit=e=>{e.preventDefault();try{const v={};for(const id of ['image','source','primary','backup','state','extra','uid','gid','port','key'])v[id]=$(id).value;
 const data=JSON.stringify(buildConfig(v),null,2)+'\n',url=URL.createObjectURL(new Blob([data],{type:'application/yaml'})),a=document.createElement('a');a.href=url;a.download='compose.yaml';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('error').textContent='配置已下载。它使用 YAML 兼容的 JSON 格式，可由 Docker Compose 直接读取。';}catch(err){$('error').textContent=err.message;}};
}
