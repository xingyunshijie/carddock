import json,os,socket,subprocess,sys,tempfile,time,unittest,urllib.request,urllib.error
from pathlib import Path

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.source=self.root/'source';self.target=self.root/'target';self.state=self.root/'state'
        for p in [self.source,self.target,self.state]:p.mkdir()
        (self.source/'a.JPG').write_bytes(b'abc')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.url='http://127.0.0.1:'+str(self.port)
        env=dict(os.environ,STATE_DIR=str(self.state),SOURCE_ROOTS=str(self.source),TARGET_ROOTS=str(self.target),ACCESS_TOKEN='test-only-http-key',PORT=str(self.port),HOST_MOUNTINFO='')
        self.proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'app/server.py')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if self.request('state')[0]==200:break
            except OSError:time.sleep(.03)
        else:raise RuntimeError('fixture server failed to start')
    def tearDown(self):self.proc.terminate();self.proc.wait(timeout=5);self.temp.cleanup()
    def request(self,path,data=None,key=True,origin=None):
        headers={'Authorization':'Bearer test-only-http-key'} if key else {}
        if origin:headers['Origin']=origin
        if data is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(self.url+'/api/'+path,headers=headers,data=json.dumps(data).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
    def test_auth_cross_origin_and_new_folder(self):
        self.assertEqual(self.request('state',key=False)[0],401)
        self.assertEqual(self.request('config',{'primary':str(self.target)},origin='http://evil.invalid')[0],403)
        status,body,_=self.request('mkdir',{'parent':str(self.target),'name':'晨曦'});self.assertEqual(status,201,body)
        self.assertTrue((self.target/'晨曦').is_dir())
        self.assertEqual(self.request('mkdir',{'parent':str(self.target),'name':'../bad'})[0],400)
        self.assertEqual(self.request('mkdir',{'parent':str(self.source),'name':'no'})[0],400)
    def test_copy_export_retry_preset_delete(self):
        status,body,_=self.request('config',{'primary':str(self.target),'media_only':False});self.assertEqual(status,200,body)
        status,body,_=self.request('jobs',{'source':str(self.source)});self.assertEqual(status,201,body);ident=json.loads(body)['id']
        for _ in range(200):
            _,body,_=self.request('state');state=json.loads(body)
            if not state['active']:break
            time.sleep(.01)
        job=next(j for j in state['jobs'] if j['id']==ident);self.assertEqual(job['status'],'completed',job)
        for kind in ['json','txt','html','checksums','log']:
            status,body,headers=self.request('report?id='+ident+'&format='+kind);self.assertEqual(status,200,body);self.assertTrue(body)
        self.assertEqual(self.request('report?id='+ident+'&format=mhl')[0],400)
        self.assertEqual(self.request('presets',{'name':'test','options':{'project':'晨曦'}})[0],200)
        self.assertIn('test',json.loads(self.request('presets')[1]))
        status,body,_=self.request('retry',{'id':ident});self.assertEqual(status,201,body)
        for _ in range(200):
            if not json.loads(self.request('state')[1])['active']:break
            time.sleep(.01)
        self.assertEqual(self.request('remove',{'id':ident})[0],200)
        self.assertTrue((self.target/'source/JPG/a.JPG').exists())

if __name__=='__main__':unittest.main()
