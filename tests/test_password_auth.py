import json,os,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from authentication import PasswordAuthentication
from test_http_api import ApiTests

class PasswordUnit(unittest.TestCase):
    def auth(self,password='MyPrivatePassword_123'):
        return PasswordAuthentication({'AUTHENTICATION_ENABLED':'true','AUTHENTICATION_PASSWORD':password})
    def test_password_login_and_session_not_plaintext(self):
        a=self.auth();self.assertIsNone(a.login('wrong'));token=a.login('MyPrivatePassword_123')
        self.assertTrue(a.authorized('Bearer '+token));self.assertFalse(a.authorized('Bearer MyPrivatePassword_123'));a.logout('Bearer '+token);self.assertFalse(a.authorized('Bearer '+token))
    def test_unicode_and_symbols(self):
        a=self.auth('我的登录密码_强密码$2026!');token=a.login('我的登录密码_强密码$2026!');self.assertTrue(a.authorized('Bearer '+token))
    def test_invalid_password_fail_closed(self):
        for password in ['', 'admin','short','改成你自己的密码','CHANGE_ME_Use_A_Password']:
            with self.assertRaises(ValueError):self.auth(password)
        with self.assertRaises(ValueError):PasswordAuthentication({'AUTHENTICATION_ENABLED':'maybe'})
    def test_expiry_and_restart(self):
        a=self.auth()
        with patch('authentication.time.monotonic',return_value=100):token=a.login('MyPrivatePassword_123')
        with patch('authentication.time.monotonic',return_value=100+a.lifetime):self.assertFalse(a.authorized('Bearer '+token))
        token=a.login('MyPrivatePassword_123');self.assertFalse(self.auth().authorized('Bearer '+token))
    def test_disabled_explicit_and_legacy(self):
        self.assertFalse(PasswordAuthentication({}).configured)
        a=PasswordAuthentication({'AUTHENTICATION_ENABLED':'false'});self.assertTrue(a.authorized(''));self.assertEqual(a.login(''),'')

class PasswordApi(ApiTests):
    def setUp(self):
        self.env=patch.dict(os.environ,{'AUTHENTICATION_ENABLED':'true','AUTHENTICATION_PASSWORD':'MyPrivatePassword_123'});self.env.start()
        # The inherited fixture expects /api/state to be accessible while starting.
        self.token=None
        super().setUp()
    def request(self,path,data=None,key=True,origin=None):
        import urllib.request,urllib.error
        if key and path not in ('login','auth') and self.token is None:
            status,body,_=self.request('login',{'password':'MyPrivatePassword_123'},key=False)
            if status==200:self.token=json.loads(body)['token']
        headers={'Authorization':'Bearer '+self.token} if key and self.token else {}
        if origin:headers['Origin']=origin
        if data is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(self.url+'/api/'+path,headers=headers,data=json.dumps(data).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
    def tearDown(self):
        try:super().tearDown()
        finally:self.env.stop()
    def test_configuration_is_public_without_password(self):
        status,body,_=self.request('auth',key=False);self.assertEqual(status,200);data=json.loads(body)
        self.assertEqual(data,{'mode':'password','enabled':True});self.assertNotIn('MyPrivatePassword',body.decode())
    def test_login_logout_and_configured_password_priority(self):
        # A saved legacy access key must not override the password configured in Compose.
        (self.state/'access-key.json').write_text(json.dumps({'token':'obsolete-legacy-key'}))
        self.assertEqual(self.request('login',{'password':'obsolete-legacy-key'},key=False)[0],401)
        self.assertEqual(self.request('login',{'password':'wrong'},key=False)[0],401)
        self.assertEqual(self.request('login',{'password':'MyPrivatePassword_123'},key=False)[0],200)
        self.assertEqual(self.request('state')[0],200);self.assertEqual(self.request('logout',{})[0],200)
        self.assertEqual(self.request('state')[0],401)
    def test_cross_origin_login_rejected(self):
        self.assertEqual(self.request('login',{'password':'MyPrivatePassword_123'},key=False,origin='http://evil.invalid')[0],403)

# Do not rediscover the imported base class as an extra test suite.
del ApiTests
if __name__=='__main__':unittest.main()
