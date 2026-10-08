import hashlib,json,os,socket,subprocess,sys,tempfile,time,unittest,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        for name in ('source','primary','backup','state'):(self.root/name).mkdir()
        (self.root/'source/test.ARW').write_bytes(b'RAW fixture'*1000)
        with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
        self.token='test-only-key-not-a-production-secret'
        env={**os.environ,'SOURCE_ROOTS':str(self.root/'source'),'TARGET_ROOTS':':'.join(str(self.root/x) for x in ('primary','backup')),'STATE_DIR':str(self.root/'state'),'ACCESS_TOKEN':self.token,'PORT':str(self.port),'HOST_MOUNTINFO':'','TLS_CERT':'','TLS_KEY':''}
        self.proc=subprocess.Popen([sys.executable,str(ROOT/'app/server.py')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:self.request('/');break
            except OSError:time.sleep(.03)
        else:self.fail('server did not start')
    def tearDown(self):
        self.proc.terminate();self.proc.wait(timeout=5);self.tmp.cleanup()
    def request(self,path,data=None,token=True):
        headers={'Authorization':'Bearer '+self.token} if token else {}
        if data is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request('http://127.0.0.1:'+str(self.port)+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=5) as r:
            b=r.read();return json.loads(b) if r.headers['Content-Type'].startswith('application/json') else b
    def wait_job(self):
        for _ in range(100):
            s=self.request('/api/state')
            if not s['active']:return s['jobs'][0]
            time.sleep(.03)
        self.fail('job did not complete')
    def test_authenticated_two_copies_and_dedup(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.request('/api/state',token=False)
        self.assertEqual(ctx.exception.code,401)
        paths={k:str(self.root/k) for k in ('source','primary','backup')}
        self.request('/api/config',{'primary':paths['primary'],'backups':[paths['backup']]})
        self.request('/api/jobs',{'source':paths['source']});j=self.wait_job()
        self.assertEqual(j['status'],'completed');self.assertTrue(j['safe_to_remove'])
        expected=hashlib.sha256((self.root/'source/test.ARW').read_bytes()).hexdigest()
        for name in ('primary','backup'):
            out=self.root/name/'source/RAW/test.ARW';self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(),expected)
        report=self.request('/api/report?id='+j['id']);self.assertEqual(report['manifest'][0]['sha256'],expected)
        self.request('/api/jobs',{'source':paths['source']});j=self.wait_job();self.assertEqual(j['skipped'],2)
    def test_static_version_and_browse_boundary(self):
        version=(ROOT/'VERSION').read_text().strip();self.assertIn(version.encode(),self.request('/version',token=False))
        roots=self.request('/api/browse')['directories'];self.assertEqual(len(roots),2)
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.request('/api/browse?path=/etc')
        self.assertEqual(ctx.exception.code,400)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/config',[])
