const $=id=>document.getElementById(id);
const mode=()=>document.querySelector('input[name=keyMode]:checked').value;
function updateMode(){const random=mode()==='random';$('customFields').hidden=random;for(const id of ['newKey','confirmKey'])$(id).required=!random;$('changeKey').textContent=random?'验证管理员并随机重置':'验证管理员并修改密钥'}
document.querySelectorAll('input[name=keyMode]').forEach(e=>e.onchange=updateMode);
$('keyForm').onsubmit=async e=>{e.preventDefault();$('keyNotice').textContent='';$('keyResult').hidden=true;$('resultKey').value='';
if(mode()==='custom'&&$('newKey').value!==$('confirmKey').value){$('keyNotice').textContent='两次输入的新密钥不一致。';return}
$('changeKey').disabled=true;$('keyNotice').textContent='正在验证 NAS 管理员身份…';
try{
 const challenge=await fetch('/api/admin/challenge');const c=await challenge.json();if(!challenge.ok)throw Error(c.error);
 const r=await fetch('/api/admin/reset',{method:'POST',headers:{'Content-Type':'application/json','X-CardDock-Admin':'1'},body:JSON.stringify({nonce:c.nonce,username:$('adminUser').value.trim(),password:$('adminPassword').value,mode:mode(),key:mode()==='custom'?$('newKey').value:null})});
 const result=await r.json();if(!r.ok)throw Error(result.error||'更新失败，请重试');
 $('resultKey').value=result.key;$('resultKey').type='password';$('showKey').textContent='显示密钥';$('keyResult').hidden=false;sessionStorage.setItem('token',result.key);$('keyNotice').textContent=result.message;
}catch(error){$('keyNotice').textContent=error.message}
finally{$('adminPassword').value='';$('newKey').value='';$('confirmKey').value='';$('changeKey').disabled=false}
};
$('showKey').onclick=()=>{const hidden=$('resultKey').type==='password';$('resultKey').type=hidden?'text':'password';$('showKey').textContent=hidden?'隐藏密钥':'显示密钥'};
$('copyKey').onclick=async()=>{try{await navigator.clipboard.writeText($('resultKey').value);$('keyNotice').textContent='新密钥已复制'}catch{$('resultKey').select();$('keyNotice').textContent='请复制已选中的新密钥'}};
updateMode();
