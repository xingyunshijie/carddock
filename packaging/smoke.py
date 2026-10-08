#!/usr/bin/env python3
"""Verify actual container: restricted UID, readonly source, API, two hashes, dedup."""
import hashlib,json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
image=sys.argv[1]
def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
with tempfile.TemporaryDirectory(prefix='carddock-smoke-') as td:
    root=Path(td)
    for n in ('source','primary','backup','state'):(root/n).mkdir()
    (root/'source/test.JPG').write_bytes(b'synthetic photo fixture'*4096)
    key='CI-only-'+os.urandom(24).hex();cid=''
    uid=os.getuid();gid=os.getgid();assert uid>0 and gid>0,'Run as nonroot test user'
    try:
        args=['run','-d','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges:true','--user',f'{uid}:{gid}','--tmpfs','/tmp:size=64m','-p','127.0.0.1::8080','-e','ACCESS_TOKEN='+key,'-e','STATE_DIR=/state','-e','SOURCE_ROOTS=/sources','-e','TARGET_ROOTS=/primary:/backup','-e','HOST_MOUNTINFO=/host/mountinfo']
        for src,dst,mode in [(root/'source','/sources','ro'),(root/'primary','/primary','rw'),(root/'backup','/backup','rw'),(root/'state','/state','rw'),('/proc/1/mountinfo','/host/mountinfo','ro'),('/sys','/sys','ro')]:args+=['-v',f'{src}:{dst}:{mode}']
        cid=docker(*args,image);port=docker('port',cid,'8080/tcp').split(':')[-1]
        def api(path,data=None):
            req=urllib.request.Request('http://127.0.0.1:'+port+path,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None)
            return json.load(urllib.request.urlopen(req,timeout=10))
        for _ in range(60):
            try:api('/api/state');break
            except OSError:time.sleep(1)
        else:raise RuntimeError('Container did not start')
        print(docker('exec',cid,'python','/app/preflight.py'))
        print('ExifTool:',docker('exec',cid,'exiftool','-ver'))
        api('/api/config',{'primary':'/primary','backups':['/backup']})
        for attempt in range(2):
            api('/api/jobs',{'source':'/sources'})
            for _ in range(100):
                state=api('/api/state')
                if not state['active']:break
                time.sleep(.1)
            j=state['jobs'][0];assert j['status']=='completed',j.get('error');assert j['safe_to_remove']
            if attempt:assert j['skipped']==2
        expected=hashlib.sha256((root/'source/test.JPG').read_bytes()).hexdigest()
        for n in ('primary','backup'):assert hashlib.sha256((root/n/'sources/JPG/test.JPG').read_bytes()).hexdigest()==expected
        print('Container SHA256, primary+backup and dedup passed.')
    except Exception:
        if cid:print(docker('logs',cid))
        raise
    finally:
        if cid:docker('rm','-f',cid)
