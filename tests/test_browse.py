import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from core import browse_directories, physical_overlap, Engine
class BrowseTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name).resolve()
        self.a=self.base/'NAS01'; self.b=self.base/'NAS02'
        self.a.mkdir(); self.b.mkdir(); self.roots=[self.a,self.b]
    def tearDown(self): self.tmp.cleanup()
    def test_manual_nas_root_is_not_auto_scan_root(self):
        auto=self.base/'external';auto.mkdir()
        e=Engine(self.base/'state',[auto],[self.b],manual_roots=[self.a])
        try:
            e.configure({'manual_sources':[str(self.a)]})
            with patch('core.mount_candidates',return_value=[]) as scan:
                devices=e.devices();scan.assert_called_once_with([auto])
                self.assertEqual(devices[0]['path'],str(self.a));self.assertFalse(devices[0]['external'])
            self.assertIn(str(self.a),browse_directories('',e.sources)['directories'])
        finally: e.db.close()
    def test_roots_and_capacity(self):
        d=browse_directories('',self.roots,{str(self.a):'存储区 1'})
        self.assertEqual(set(d['directories']),{str(self.a),str(self.b)})
        self.assertFalse(d['writable']); self.assertEqual(d['path'],'')
        a=next(e for e in d['entries'] if e['path']==str(self.a))
        self.assertEqual(a['name'],'存储区 1'); self.assertGreater(a['total'],0)
    def test_navigation_and_hidden_folders(self):
        sub=self.a/'旅拍 2026'; sub.mkdir()
        for n in ['.hidden','@thumbnail','lost+found']: (self.a/n).mkdir()
        (self.a/'escape').symlink_to(self.b,target_is_directory=True)
        d=browse_directories(str(self.a),self.roots)
        self.assertEqual(d['directories'],[str(sub)]); self.assertEqual(d['parent'],'')
        d=browse_directories(str(sub),self.roots)
        self.assertEqual(d['parent'],str(self.a)); self.assertEqual(d['entries'],[])
    def test_reject_outside_missing_and_symlinks(self):
        (self.a/'link').symlink_to(self.b,target_is_directory=True)
        for value in [str(self.base),str(self.a/'missing'),str(self.a/'link'),str(self.a/'..'/'NAS02'),'relative']:
            with self.assertRaises(ValueError): browse_directories(value,self.roots)
    def test_readonly_and_unavailable_root(self):
        with patch('core.os.access',return_value=False):
            self.assertFalse(browse_directories(str(self.a),self.roots)['writable'])
        self.b.rmdir()
        self.assertEqual(browse_directories('',self.roots)['directories'],[str(self.a)])
    def test_physical_alias_and_nested_overlap(self):
        nested=self.a/'nested'; nested.mkdir()
        alias=self.base/'alias'; alias.symlink_to(self.a,target_is_directory=True)
        self.assertTrue(physical_overlap(self.a,alias)); self.assertTrue(physical_overlap(alias,nested))
        self.assertFalse(physical_overlap(self.a,self.b))
if __name__=='__main__': unittest.main()
