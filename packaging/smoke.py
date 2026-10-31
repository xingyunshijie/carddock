#!/usr/bin/env python3
"""Exercise the self-contained image without any host program directory."""
import json,os,pathlib,subprocess,tempfile,time,urllib.request,urllib.error,uuid
root=pathlib.Path(__file__).resolve().parents[1]
image=os.environ.get('CARDDOCK_TEST_IMAGE','carddock:ci')
def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
with tempfile.TemporaryDirectory(prefix='carddock-container-') as tmp:
 base=pathlib.Path(tmp);source=base/'source';primary=base/'primary';backup=base/'backup';state=base/'state'
 for p in [source,primary,backup,state]:p.mkdir()
 samples=['DCIM/PANORAMA/001_0061/F.DNG','DCIM/PANORAMA/001_0061/F.JPG','DCIM/PANORAMA/001_0061/metadata.json','DCIM/photo.ARW','DCIM/photo.JPG','DCIM/photo.XMP','DCIM/film.LRF','HYPERLAPSE/001_0003/F.DNG']
 for name in samples:
  p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('synthetic '+name).encode())
 name='carddock-smoke-'+uuid.uuid4().hex[:10]
 args=['run','-d','--name',name,'--user',str(os.getuid())+':'+str(os.getgid()),'--read-only','--tmpfs','/tmp:size=128m,mode=1777','--cap-drop','ALL','--security-opt','no-new-privileges:true','-p','127.0.0.1::8080']
 for key,value in {'AUTHENTICATION_ENABLED':'true','AUTHENTICATION_PASSWORD':'CI-Only-Password-2026','SOURCE_ROOTS':'/sources','TARGET_ROOTS':'/destinations/primary:/destinations/backup','STATE_DIR':'/state','HOST_MOUNTINFO':'/host/mountinfo','PYTHONDONTWRITEBYTECODE':'1'}.items():args+=['-e',key+'='+value]
 for host,target,ro in [(source,'/sources',True),(primary,'/destinations/primary',False),(backup,'/destinations/backup',False),(state,'/state',False),(pathlib.Path('/proc/1/mountinfo'),'/host/mountinfo',True),(pathlib.Path('/sys'),'/sys',True)]:args+=['--mount','type=bind,source='+str(host)+',target='+target+(',readonly' if ro else '')]
 args += [image]
 volume=name+'-state'
 docker('volume','create',volume)
 try:
  assert docker('run','--rm','--mount','type=volume,source='+volume+',target=/state','-e','TARGET_ROOTS=/state',image,'python','-c',"import os;from pathlib import Path;assert os.getuid()==1000;Path('/state/write-test').write_text('ok');print('state-ok')")=='state-ok'
  print('PASS non-root service and fresh persistent state volume',flush=True)
 finally:docker('volume','rm',volume)
 token=''
 try:
  docker(*args);port=docker('port',name,'8080/tcp').rsplit(':',1)[1];url='http://127.0.0.1:'+port
  def request(path,data=None,authenticated=True):
   headers={'Content-Type':'application/json'}
   if authenticated and token:headers['Authorization']='Bearer '+token
   req=urllib.request.Request(url+'/api/'+path,headers=headers,data=json.dumps(data).encode() if data is not None else None)
   try:
    with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
   except urllib.error.HTTPError as e:
    if e.code==401:raise
    raise RuntimeError('API '+path+': '+e.read().decode()) from e
  for _ in range(120):
   try:
    assert request('auth',authenticated=False)=={'mode':'password','enabled':True};break
   except (OSError,ValueError):
    if docker('inspect','-f','{{.State.Running}}',name)!='true':raise RuntimeError('Container exited during startup')
    time.sleep(1)
  else:raise RuntimeError('Container startup timeout')
  try:request('state',authenticated=False);raise AssertionError('Unauthenticated request accepted')
  except urllib.error.HTTPError as e:assert e.code==401
  token=request('login',{'password':'CI-Only-Password-2026'},False)['token']
  initial=request('state')['config']
  assert initial['primary']=='/destinations/primary/影像归仓' and initial['backups']==[] and not initial['auto'] and not initial['setup_complete']
  assert (primary/'影像归仓').is_dir()
  print('PASS fresh default archive directory and primary-only mode',flush=True)
  request('config',{'primary':'/destinations/primary','backups':['/destinations/backup'],'media_only':False,'setup_complete':True})
  for algorithm in ['sha256','xxh64','blake3','md5']:
   request('config',{'verify':algorithm});job=request('jobs',{'source':'/sources'})
   for _ in range(120):
    report=request('report?id='+job['id'])
    if report['status'] not in ('queued','running'):break
    time.sleep(.1)
   assert report['status']=='completed',report.get('error')
   assert report['done']==len(samples)*2 and report['selected_scope_verified'] and report['safe_to_remove']
   assert all(r['checksum'] for r in report['manifest'])
   assert all(r['read_source'].startswith('/destinations/primary/') for r in report['manifest'] if r['destination'].startswith('/destinations/backup/'))
   assert (primary/'sources/全景序列/001_0061/F.DNG').read_bytes()==(source/'DCIM/PANORAMA/001_0061/F.DNG').read_bytes()
   assert (primary/'sources/视频代理/film.LRF').exists()
   if algorithm!='sha256':assert report['skipped']==len(samples)*2
   print('PASS native Docker startup, login, primary/backup, panorama, retry and '+algorithm,flush=True)
  docker('restart',name)
  port=docker('port',name,'8080/tcp').rsplit(':',1)[1];url='http://127.0.0.1:'+port
  for _ in range(30):
   try:
    token=request('login',{'password':'CI-Only-Password-2026'},False)['token'];break
   except (OSError,ValueError):time.sleep(1)
  else:raise RuntimeError('Container restart timeout')
  assert request('state')['config']['backups']==['/destinations/backup']
  assert request('state')['config']['setup_complete']
  print('PASS persistent configuration after restart',flush=True)
  request('logout',{})
  try:request('state');raise AssertionError('Logged-out session accepted')
  except urllib.error.HTTPError as e:assert e.code==401
  print('PASS session logout and strict non-root/read-only self-contained image',flush=True)
 except Exception:
  subprocess.run(['docker','logs',name],check=False);raise
 finally:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
