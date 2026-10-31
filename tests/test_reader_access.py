import importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from core import Engine,mount_candidates
spec=importlib.util.spec_from_file_location('reader_installer',ROOT/'nas-shares.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class ReaderAccessTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.usb=self.root/'reader';self.card=self.usb/'SD card';self.card.mkdir(parents=True)
        self.sys=self.root/'sys';self.dev=self.sys/'devices/usb1/block/sda';(self.dev/'sda1').mkdir(parents=True)
        (self.dev/'sda1/partition').write_text('1');(self.dev/'removable').write_text('1')
        links=self.sys/'dev/block';links.mkdir(parents=True);(links/'8:1').symlink_to(self.dev/'sda1')
        self.mount=self.root/'mountinfo';escaped=str(self.card).replace(' ',r'\040')
        self.mount.write_text(f'23 1 8:1 / {escaped} ro - exfat /dev/sda1 rw\n')
    def tearDown(self):self.tmp.cleanup()
    def test_nonstandard_nas_mounted_card_is_granted_without_whole_disk_root(self):
        with patch.dict(os.environ,{'HOST_MOUNTINFO':''}):
            roots=installer.discover_readers(mountinfo=self.mount,sysroot=self.sys)
        self.assertIn(self.card,roots);self.assertNotIn(self.usb,roots);self.assertNotIn(Path('/'),roots)
    def test_explicit_reader_parent_uses_readonly_propagation_and_real_path(self):
        base=installer.base_configuration();base['services']['carddock']['environment']['AUTHENTICATION_PASSWORD']='keep-existing'
        result=installer.reader_configuration(base,[self.usb]);result=installer.reader_configuration(result,[self.usb])
        service=installer.configuration(result,{'Archive':self.root})['services']['carddock']
        mounts=[v for v in service['volumes'] if isinstance(v,dict) and v['target'].startswith('/readers/')]
        self.assertEqual(len(mounts),1);m=mounts[0]
        self.assertTrue(m['read_only']);self.assertEqual(m['bind'],{'create_host_path':False,'propagation':'rslave'})
        self.assertEqual(m['source'],str(self.usb));self.assertIn(m['target'],service['environment']['SOURCE_ROOTS'].split(':'))
        self.assertEqual(json.loads(service['environment']['HOST_PATH_MAP'])[m['target']],str(self.usb))
        self.assertEqual(service['environment']['AUTHENTICATION_PASSWORD'],'keep-existing')
        self.assertNotIn('privileged',service);self.assertNotIn('cap_add',service)
    def test_temporary_samba_card_share_remains_source_only(self):
        base=installer.reader_configuration(installer.base_configuration(),[self.usb])
        service=installer.configuration(base,{'SD_Card':self.card,'Photos':self.root})['services']['carddock']
        self.assertNotIn('/shares/SD_Card',[v.get('target') for v in service['volumes'] if isinstance(v,dict)])
        self.assertIn('SD_Card',json.loads(service['environment']['TARGET_LABELS']).values())
    def test_reader_parent_rejects_system_roots(self):
        for value in ('/','/mnt','/proc','/etc','relative'):
            with self.assertRaises(ValueError):installer.discover_readers([value],mountinfo=self.mount,sysroot=self.sys)
    def test_hotplug_changes_are_visible_without_restarting_engine(self):
        with patch.dict(os.environ,{'HOST_MOUNTINFO':''}):
            self.assertEqual(mount_candidates([self.usb],str(self.mount),str(self.sys))[0]['path'],str(self.card))
            self.mount.write_text('');self.assertEqual(mount_candidates([self.usb],str(self.mount),str(self.sys)),[])
            self.mount.write_text(f'42 1 8:1 / {str(self.card).replace(" ",chr(92)+"040")} ro - exfat /dev/sda1 rw\n')
            self.assertEqual(len(mount_candidates([self.usb],str(self.mount),str(self.sys))),1)
    def test_system_disk_is_never_a_source(self):
        self.mount.write_text(self.mount.read_text()+'24 1 8:1 / /boot ro - vfat /dev/sda1 rw\n')
        with patch.dict(os.environ,{'HOST_MOUNTINFO':''}):
            roots=installer.discover_readers(mountinfo=self.mount,sysroot=self.sys)
        self.assertNotIn(self.card,roots)
    def test_ejecting_one_card_does_not_hide_the_other(self):
        other=self.root/'other';other.mkdir();target=self.root/'target';target.mkdir()
        engine=Engine(self.root/'state',[self.usb,other],[target])
        cards=[{'path':str(p),'identity':str(i),'name':p.name,'external':False} for i,p in enumerate((self.card,other))]
        try:
            with patch('core.mount_candidates',return_value=cards),patch('core.detect',side_effect=[FileNotFoundError('ejected'),{'brand':'DJI','model':'','evidence':'test'}]):
                self.assertEqual([d['path'] for d in engine.devices()],[str(other)])
        finally:engine.db.close()
