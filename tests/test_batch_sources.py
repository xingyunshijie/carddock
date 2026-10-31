import sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from core import Engine

class BatchSourcesTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
  self.a=self.root/'CARD_A';self.b=self.root/'CARD_B';self.target=self.root/'target'
  for p in (self.a,self.b,self.target):p.mkdir()
  (self.a/'a.JPG').write_bytes(b'camera-a');(self.b/'b.JPG').write_bytes(b'camera-b')
  self.engine=Engine(self.root/'state',[self.a,self.b],[self.target])
  self.engine.configure({'primary':str(self.target),'directory_template':'{source}'})
 def tearDown(self):
  deadline=time.monotonic()+8
  while self.engine.active and time.monotonic()<deadline:time.sleep(.01)
  self.engine.db.close();self.tmp.cleanup()
 def test_all_sources_are_registered_before_first_start_and_copy_in_order(self):
  started=[];original=self.engine.start_job
  def start(j):
   if not started:self.assertEqual(len(self.engine.jobs),2)
   started.append(j['source']);return original(j)
  with patch.object(self.engine,'start_job',side_effect=start):
   jobs=self.engine.submit_batch([str(self.a),str(self.b)])
   deadline=time.monotonic()+8
   while any(j['status'] in ('queued','running') for j in jobs) and time.monotonic()<deadline:time.sleep(.01)
  self.assertEqual(started,[str(self.a),str(self.b)])
  self.assertEqual([j['status'] for j in jobs],['completed','completed'])
  self.assertTrue((self.target/'CARD_A/JPG/a.JPG').is_file());self.assertTrue((self.target/'CARD_B/JPG/b.JPG').is_file())
 def test_invalid_second_source_does_not_start_or_leave_a_partial_queue(self):
  with patch.object(self.engine,'start_job') as start,self.assertRaises(ValueError):
   self.engine.submit_batch([str(self.a),str(self.root/'not-granted')])
  start.assert_not_called();self.assertFalse(self.engine.jobs);self.assertEqual(list(self.target.iterdir()),[])
 def test_duplicate_or_overlapping_sources_are_rejected(self):
  child=self.a/'nested';child.mkdir()
  for sources in ([str(self.a),str(self.a)],[str(self.a),str(child)],[],[1],str(self.a)):
   with self.subTest(sources=sources),self.assertRaises(ValueError):self.engine.submit_batch(sources)
  self.assertFalse(self.engine.jobs)
 def test_batch_options_are_frozen_when_settings_change(self):
  self.engine.configure({'project':'original','directory_template':'{project}/{source}'})
  with patch.object(self.engine,'start_job'):
   jobs=self.engine.submit_batch([str(self.a),str(self.b)])
  self.engine.configure({'project':'later'})
  self.assertTrue(all(j['options']['project']=='original' for j in jobs))
  self.assertEqual([j['options']['_resolved_folder'] for j in jobs],['original/CARD_A','original/CARD_B'])
 def test_failure_to_save_rolls_back_only_new_batch_records(self):
  original=self.engine.save_job;calls=[];self.engine.blocked_sources.add(str(self.a))
  def save(j):
   calls.append(j['id'])
   if len(calls)==2:raise OSError('synthetic save failure')
   original(j)
  with patch.object(self.engine,'save_job',side_effect=save),patch.object(self.engine,'start_job') as start,self.assertRaises(OSError):
   self.engine.submit_batch([str(self.a),str(self.b)])
  start.assert_not_called();self.assertEqual(self.engine.jobs,{})
  self.assertEqual(self.engine.db.execute('select count(*) from jobs').fetchone()[0],0)
  self.assertIn(str(self.a),self.engine.blocked_sources)
 def test_busy_requires_explicit_enqueue_and_does_not_start_parallel_copy(self):
  self.engine.active=True
  try:
   with self.assertRaises(ValueError):self.engine.submit_batch([str(self.a),str(self.b)])
   with patch.object(self.engine,'start_job') as start:
    jobs=self.engine.submit_batch([str(self.a),str(self.b)],enqueue=True)
   start.assert_not_called();self.assertTrue(all(j['status']=='queued' for j in jobs))
  finally:self.engine.active=False
