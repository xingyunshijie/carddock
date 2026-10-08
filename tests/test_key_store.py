import sys,tempfile,unittest,stat,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from key_store import KeyStore,AttemptLimiter,verify_admin
class KeyStoreTest(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'key.json';self.store=KeyStore(self.path)
    def tearDown(self):self.tmp.cleanup()
    def test_default_custom_random_and_restart(self):
        self.assertTrue(self.store.authorized('Bearer CardDock'))
        custom=self.store.rotate('custom','Custom_Key123','admin')
        self.assertFalse(self.store.authorized('Bearer CardDock'));self.assertTrue(self.store.authorized('Bearer '+custom))
        random=self.store.rotate('random',None,'admin');self.assertGreaterEqual(len(random),32)
        restarted=KeyStore(self.path,'OLD_ENV_TOKEN')
        self.assertTrue(restarted.authorized('Bearer '+random));self.assertFalse(restarted.authorized('Bearer '+custom));self.assertFalse(restarted.authorized('Bearer OLD_ENV_TOKEN'))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode),0o600)
    def test_write_failure_preserves_old(self):
        self.store.rotate('custom','Original_Key123','admin')
        with patch('key_store.os.replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.store.rotate('random',None,'admin')
        self.assertTrue(self.store.authorized('Bearer Original_Key123'))
    def test_invalid_and_same_key(self):
        for mode,key in [('bad','Something_123'),('custom','short'),('custom','a'*10+'\n'),('custom','CardDock')]:
            with self.assertRaises(ValueError):self.store.rotate(mode,key,'admin')
        self.assertTrue(self.store.authorized('Bearer CardDock'))
    def test_corrupt_file_never_falls_back(self):
        self.path.write_text('{}')
        with self.assertRaises(ValueError):self.store.authorized('Bearer CardDock')
    def test_rate_limit(self):
        l=AttemptLimiter()
        for _ in range(3):self.assertTrue(l.take('ip','user'))
        self.assertFalse(l.take('ip','another'));self.assertFalse(l.take('otherip','user'))
        l.success('ip','user');self.assertTrue(l.take('ip','user'))
    def test_missing_auth_service_and_invalid_credentials(self):
        self.assertFalse(verify_admin('bad/name','password','/missing'))
        with self.assertRaises(RuntimeError):verify_admin('admin','password','/missing')
