import json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from core import Engine
from rules import folder

class NamingPreviewTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
  self.source=self.root/'CARD';self.target=self.root/'target'
  self.source.mkdir();self.target.mkdir();(self.source/'a.JPG').write_bytes(b'synthetic')
  self.engine=Engine(self.root/'state',[self.source],[self.target])
  self.engine.configure({'primary':str(self.target),'manual_sources':[str(self.source)]})
 def tearDown(self):
  deadline=time.monotonic()+5
  while self.engine.active and time.monotonic()<deadline:time.sleep(.01)
  self.engine.db.close();self.tmp.cleanup()
 def metadata(self,overview='大疆航拍相机'):
  return {'path':str(self.source),'overview':overview,'brand':'DJI','model':'FC3582','external':True}
 def test_preview_uses_copy_rules_and_does_not_save_or_create_directories(self):
  original=(self.engine.state/'config.json').read_bytes()
  options={'directory_template':'{date}{project}{device}机位{camera}卡号{card}','project':'晨曦','camera':'1','card':'01'}
  with patch.object(self.engine,'devices',return_value=[self.metadata()]),patch('core.detect',return_value=self.metadata()):
   preview=self.engine.naming_preview(str(self.source),options)
   self.assertEqual(preview['namespace'],str(folder({**self.engine.config,**options},self.source,'大疆航拍相机')))
   self.assertEqual((self.engine.state/'config.json').read_bytes(),original)
   self.assertEqual(list(self.target.iterdir()),[]);self.assertEqual(self.engine.jobs,{})
   task=self.engine.submit(str(self.source),options)
   self.assertEqual(task['options']['_resolved_folder'],preview['namespace'])
 def test_empty_fields_unknown_and_mixed_devices(self):
  template='{date}/{project}/机位{camera}/卡号{card}/{device}/{source}'
  with patch.object(self.engine,'devices',return_value=[self.metadata('')]):
   result=self.engine.naming_preview(str(self.source),{'directory_template':template})
   # A recognized brand falls back to its generic overview; an unknown card omits it.
   self.assertIn('大疆设备',result['namespace'])
  with patch.object(self.engine,'devices',return_value=[{'path':str(self.source),'brand':''}]):
   result=self.engine.naming_preview(str(self.source),{'directory_template':template})
   self.assertNotIn('机位',result['namespace']);self.assertNotIn('卡号',result['namespace']);self.assertNotIn('//',result['namespace'])
   self.assertTrue(result['namespace'].endswith('/CARD'))
  with patch.object(self.engine,'devices',return_value=[self.metadata('索尼相机+大疆航拍相机')]):
   result=self.engine.naming_preview(str(self.source),{'directory_template':'{device}/{source}'})
   self.assertIn('索尼相机+大疆航拍相机',result['namespace'])
 def test_empty_leading_optional_field_does_not_become_absolute(self):
  self.assertEqual(str(folder({'directory_template':'{project}/{source}'},self.source)),'CARD')
  with self.assertRaises(ValueError):folder({'directory_template':'/{source}'},self.source)
 def test_rejects_ungranted_source_and_unsafe_template(self):
  with self.assertRaises(ValueError):self.engine.naming_preview(str(self.root),{})
  for template in ('../escape','/absolute','{unknown}','safe/../../escape'):
   with self.subTest(template=template),self.assertRaises(ValueError):self.engine.naming_preview(str(self.source),{'directory_template':template})
  with self.assertRaises(ValueError):self.engine.naming_preview(str(self.source),[])
 def test_namespace_only_request_does_not_modify_other_settings(self):
  before=dict(self.engine.config)
  with patch.object(self.engine,'devices',return_value=[self.metadata()]):
   self.engine.naming_preview(str(self.source),{'directory_template':'{source}','auto':True,'primary':'/elsewhere','backups':['/other']})
  self.assertEqual(self.engine.config,before)
