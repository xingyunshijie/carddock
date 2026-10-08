import importlib.util,json,os,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('access_key',Path(__file__).resolve().parents[1]/'access-key.py')
k=importlib.util.module_from_spec(spec);spec.loader.exec_module(k)
class KeyTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=Path(self.tmp.name)/'.env'
    def tearDown(self): self.tmp.cleanup()
    def test_initial_random_private_and_idempotent(self):
        self.env.write_text('PUID=1000\nACCESS_TOKEN='+k.PLACEHOLDER+'\n')
        key=k.initialize(self.env);self.assertGreaterEqual(len(key),32)
        self.assertEqual(k.read_key(self.env.read_text()),key);self.assertIn('PUID=1000',self.env.read_text())
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode),0o600)
        self.assertIsNone(k.initialize(self.env));self.assertEqual(k.read_key(self.env.read_text()),key)
        other=Path(self.tmp.name)/'other';self.assertNotEqual(k.initialize(other),key)
    def test_reject_injection_duplicate_and_symlink(self):
        for key in ['short','a'*16+'\nX=1','a'*16+'$()']:
            with self.assertRaises(ValueError): k.with_key('',key)
        with self.assertRaises(ValueError): k.with_key('ACCESS_TOKEN=a\nACCESS_TOKEN=b\n','a'*32)
        real=Path(self.tmp.name)/'real';real.write_text('')
        self.env.symlink_to(real)
        with self.assertRaises(ValueError): k.initialize(self.env)
        self.assertEqual(real.read_text(),'')
    def test_nonadmin_cannot_reset(self):
        with patch.object(k.os,'geteuid',return_value=1000),patch.object(k,'command') as cmd:
            with self.assertRaises(PermissionError): k.reset(self.env)
            cmd.assert_not_called()
    def test_admin_cli_rotates_without_restart(self):
        new='new_key_for_tests_123456'
        with patch.object(k.os,'geteuid',return_value=0),patch.object(k,'command',return_value=json.dumps({'key':new})) as command:
            self.assertEqual(k.reset(self.env),new)
            args,data=command.call_args.args
            self.assertEqual(args[:4],['docker','exec','-i','carddock'])
            self.assertEqual(json.loads(data),{'mode':'random','key':None})
    def test_custom_confirmation_mismatch(self):
        with patch.object(k.os,'geteuid',return_value=0),patch.object(k.getpass,'getpass',side_effect=['test_key123','other_key123']),patch.object(k,'command') as cmd:
            with self.assertRaises(ValueError):k.reset(custom=True)
            cmd.assert_not_called()
