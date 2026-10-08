import argparse,importlib.util,json,os,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('deploy',Path(__file__).resolve().parents[1]/'deploy.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
class DeploymentTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        for n in ('card root','primary','backup','state'):(self.root/n).mkdir()
        self.a=argparse.Namespace(source=str(self.root/'card root'),primary=str(self.root/'primary'),backup=None,state=str(self.root/'state'),uid=1000,gid=100,bind='0.0.0.0',port=8080,project='carddock',image=None,admin_host=None,https_port=8443)
    def tearDown(self):self.tmp.cleanup()
    def test_primary_only_no_backup_mount_or_requirement(self):
        s=d.configuration(self.a)['services']['carddock'];self.assertEqual(s['environment']['TARGET_ROOTS'],'/destinations/primary')
        self.assertNotIn('/destinations/backup',[v['target'] for v in s['volumes']]);self.assertEqual(s['user'],'1000:100')
        self.assertTrue(s['volumes'][0]['read_only']);self.assertEqual(s['volumes'][0]['bind']['propagation'],'rslave')
        self.assertNotIn('privileged',s);self.assertNotIn('ADMIN_HTTPS_URL',s['environment'])
    def test_backup_and_tls_are_explicit(self):
        self.a.backup=str(self.root/'backup');self.a.admin_host='2001:db8::1';self.a.image='example/carddock:0.11'
        s=d.configuration(self.a)['services']['carddock'];self.assertNotIn('build',s)
        self.assertEqual(s['environment']['ADMIN_HTTPS_URL'],'https://[2001:db8::1]:8443')
        self.assertIn('/destinations/backup',s['environment']['TARGET_ROOTS'])
    def test_reject_alias_overlap_missing_root_and_bad_host(self):
        for attr,value in [('primary',self.a.source),('state',self.a.primary),('uid',0),('gid',0),('port',65536),('admin_host','https://bad/path'),('source','/does-not-exist')]:
            old=getattr(self.a,attr);setattr(self.a,attr,value)
            with self.assertRaises(ValueError):d.configuration(self.a)
            setattr(self.a,attr,old)
        alias=self.root/'alias';alias.symlink_to(self.root/'primary');self.a.state=str(alias)
        with self.assertRaises(ValueError):d.configuration(self.a)
    def test_private_config_and_no_secret_in_image(self):
        f=self.root/'config.json';d.private_json(f,d.configuration(self.a));self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o600)
        self.assertGreaterEqual(len(json.loads(f.read_text())['services']['carddock']['environment']['ACCESS_TOKEN']),32)
    def invoke(self,action):
        with patch('sys.argv',['deploy.py','--file',str(self.root/'compose.json'),action]):d.main()
    def test_start_checks_before_container_start(self):
        d.private_json(self.root/'compose.json',d.configuration(self.a));events=[]
        with patch.object(d,'running',return_value=''),patch.object(d,'compose',side_effect=lambda *a,**k:events.append(a[1])),patch.object(d,'check',side_effect=lambda p:events.append('preflight')),patch.object(d,'ready'):
            self.invoke('start')
        self.assertLess(events.index('preflight'),events.index('up'));self.assertTrue((self.root/'deployed.json').exists())
    def test_failed_preflight_never_replaces_container(self):
        d.private_json(self.root/'compose.json',d.configuration(self.a))
        with patch.object(d,'running',return_value=''),patch.object(d,'compose') as c,patch.object(d,'check',side_effect=ValueError('readonly failure')):
            with self.assertRaises(ValueError):self.invoke('start')
            self.assertNotIn('up',[call.args[1] for call in c.call_args_list])
    def test_active_import_blocks_update(self):
        data=d.configuration(self.a)
        for n in ('compose.json','deployed.json'):d.private_json(self.root/n,data)
        with patch.object(d,'running',return_value='abc'),patch.object(d,'guard',side_effect=ValueError('active')),patch.object(d,'run') as r:
            with self.assertRaises(ValueError):self.invoke('update')
            r.assert_not_called()
    def test_update_keeps_original_config_for_rollback(self):
        old=d.configuration(self.a);d.private_json(self.root/'deployed.json',old);old['services']['carddock'].pop('build');old['services']['carddock']['image']='carddock:0.12';d.private_json(self.root/'compose.json',old)
        with patch.object(d,'running',return_value='abc'),patch.object(d,'guard'),patch.object(d,'run',return_value='sha256:old'),patch.object(d,'compose'),patch.object(d,'check'),patch.object(d,'ready'):
            self.invoke('update')
        saved=json.loads((self.root/'rollback.json').read_text());self.assertEqual(saved['services']['carddock']['volumes'],old['services']['carddock']['volumes']);self.assertIn('rollback-',saved['services']['carddock']['image'])
    def test_update_rejects_target_migration(self):
        d.private_json(self.root/'deployed.json',d.configuration(self.a));self.a.primary=str(self.root/'backup');d.private_json(self.root/'compose.json',d.configuration(self.a))
        with patch.object(d,'running',return_value='abc'),patch.object(d,'run') as r:
            with self.assertRaises(ValueError):self.invoke('update')
            r.assert_not_called()
