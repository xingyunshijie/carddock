import errno,json,sys,tempfile,time,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from core import Engine,category,selected,snapshot
from rules import folder,layout,protected
from reports import export

class DesktopParity(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.src=self.root/'source';self.a=self.root/'primary';self.b=self.root/'backup';self.state=self.root/'state'
        for p in [self.src,self.a,self.b]:p.mkdir()
        self.e=Engine(self.state,[self.src],[self.a,self.b])
        self.e.configure({'primary':str(self.a),'backups':[str(self.b)],'media_only':False,'keep_parents':False,'directory_template':'{source}'})
    def tearDown(self):
        self.wait();self.e.db.close();self.temp.cleanup()
    def put(self,path,data=b'x'):
        p=self.src/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p
    def wait(self):
        deadline=time.monotonic()+10
        while self.e.active and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(self.e.active)
    def run_job(self,source=None,options=None):
        j=self.e.submit(str(source or self.src),options);self.wait();return j
    def success(self,j):self.assertEqual(j['status'],'completed',j.get('error'))
    def test_panorama_roots_metadata_and_no_format_split(self):
        for group in ['001_0061','001_0053']:
            for name in ['DJI_0001.DNG','DJI_0001.JPG','DJI_0001.XMP','metadata.json','nested/frame.JPG']:self.put('DCIM/PANORAMA/'+group+'/'+name,(group+name).encode())
        self.put('DCIM/normal.JPG',b'normal')
        for selected_root in [self.src,self.src/'DCIM/PANORAMA',self.src/'DCIM/PANORAMA/001_0061']:
            for media in [False,True]:
                with self.subTest(root=str(selected_root),media=media):
                    j=self.run_job(selected_root,{'media_only':media,'filename_template':'renamed_{sequence}','directory_template':'run'+str(len(self.e.jobs))})
                    self.success(j)
                    for dest in [self.a,self.b]:
                        base=dest/j['options']['_resolved_folder']/'全景序列/001_0061'
                        for name in ['DJI_0001.DNG','DJI_0001.JPG','DJI_0001.XMP','metadata.json','nested/frame.JPG']:self.assertTrue((base/name).exists(),str(base/name))
                        self.assertFalse((base/'RAW').exists());self.assertFalse((base/'JPG').exists())
                    self.assertEqual(category(self.src/'panorama/group/a.dng'),'全景序列')
                    self.assertEqual(category(self.src/'DCIM/PANORAMA.JPG'),'JPG')
    def test_timelapse_proxies_sidecars_sony_and_red(self):
        for name in ['F.DNG','F.JPG','F.XMP']:self.put('DCIM/HYPERLAPSE/001_0003/'+name)
        for name in ['DJI_001.LRF','DJI_001.XMP']:self.put('DCIM/Proxy/'+name)
        self.put('PRIVATE/M4ROOT/THMBNL/thumbnail.JPG');self.put('PRIVATE/M4ROOT/THMBNL/info.XML')
        self.put('DCIM/100MEDIA/normal.JPG');self.put('RED/A.RDC/a.R3D');self.put('RED/A.RDC/metadata.RMD')
        j=self.run_job();self.success(j);base=self.a/'source'
        self.assertTrue((base/'延时摄影图片序列/001_0003/RAW/F.DNG').exists())
        self.assertTrue((base/'延时摄影图片序列/001_0003/RAW/F.XMP').exists())
        self.assertTrue((base/'延时摄影图片序列/001_0003/JPG/F.JPG').exists())
        self.assertTrue((base/'视频代理/DJI_001.LRF').exists());self.assertTrue((base/'视频代理/DJI_001.XMP').exists())
        self.assertFalse(list(base.rglob('thumbnail.JPG')));self.assertTrue(list(base.rglob('info.XML')))
        self.assertTrue((base/'视频/RED/A.RDC/a.R3D').exists());self.assertTrue((base/'视频/RED/A.RDC/metadata.RMD').exists())
        j=self.run_job(options={'exclude_proxies':True,'directory_template':'exclude'});self.success(j)
        self.assertFalse((self.a/'exclude/视频代理').exists());self.assertFalse(j['safe_to_remove'])
    def test_first_copy_all_files_then_verify_and_counts(self):
        for name in ['a.MP4','b.MP4','empty.MP4']:self.put(name,b'' if name.startswith('empty') else name.encode())
        updates=[];events=[];save=self.e.save_job;hash_file=self.e.hash
        def record(j):
            updates.append((j.get('stage'),j.get('stage_done'),j.get('stage_total')));save(j)
        def hashing(p,mode):
            if self.e.local.job.get('stage')=='copy':events.append('premature hash')
            return hash_file(p,mode)
        self.e.save_job=record;self.e.hash=hashing;j=self.run_job();self.success(j)
        self.assertFalse(events);self.assertIn(('copy',1,3),updates);self.assertIn(('copy',3,3),updates)
        self.assertIn(('verify',0,3),updates);self.assertIn(('verify',3,3),updates)
        self.assertTrue(all(done<=total for stage,done,total in updates if done is not None))
    def test_retries_and_relay_read_provenance(self):
        self.put('a.DNG',b'original');self.put('a.JPG',b'jpeg')
        j=self.run_job();self.success(j)
        backup=[r for r in j['manifest'] if r['destination'].startswith(str(self.b))]
        self.assertTrue(all(r['read_source'].startswith(str(self.a)) for r in backup))
        (self.a/'unrelated.txt').write_text('skip');self.assertFalse((self.b/'unrelated.txt').exists())
        again=self.run_job();self.success(again);self.assertEqual(again['copied'],0);self.assertEqual(again['skipped'],4)
        (self.b/'source/RAW/a.DNG').unlink();repaired=self.run_job();self.success(repaired);self.assertEqual(repaired['copied'],1)
    def test_all_hashes_and_vectors(self):
        p=self.put('abc.JPG',b'abc')
        expected={'sha256':'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad','md5':'900150983cd24fb0d6963f7d28e17f72','xxh64':'44bc2cf5ad770999','blake3':'6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85'}
        for algorithm,value in expected.items():
            self.assertEqual(self.e.hash(p,algorithm),value)
            j=self.run_job(options={'verify':algorithm,'directory_template':algorithm});self.success(j)
            self.assertTrue(j['selected_scope_verified']);self.assertTrue(j['safe_to_remove'])
        j=self.run_job(options={'verify':'quick','directory_template':'quick'});self.success(j)
        self.assertFalse(j['selected_scope_verified']);self.assertFalse(j['safe_to_remove'])
        self.assertTrue(all(r['checksum'] is None for r in j['manifest']))
    def test_official_blake3_boundary_vectors(self):
        from blake3 import blake3
        vectors=json.loads((Path(__file__).parent/'fixtures/blake3-vectors.json').read_text())['cases']
        for v in vectors:
            data=bytes(i%251 for i in range(v['length']));h=blake3()
            for i in range(0,len(data),137):h.update(data[i:i+137])
            self.assertEqual(h.hexdigest(),v['hash'])
    def test_templates_pairing_filters_presets(self):
        for name in ['photo.DNG','photo.JPG','photo.XMP']:self.put(name,name.encode())
        self.put('movie.MP4')
        c={'project':'晨曦','camera':'A','card':'01','directory_template':'{date}{project}{device}机位{camera}卡号{card}','filename_template':'{original}_{sequence}.{ext}'}
        j=self.run_job(options=c);self.success(j);base=self.a/j['options']['_resolved_folder']
        self.assertTrue((base/'RAW/photo_0002.DNG').exists() or (base/'RAW/photo_0001.DNG').exists())
        names={p.stem for p in base.rglob('photo*')};self.assertEqual(len(names),1)
        j=self.run_job(options={'extensions':'JPG','directory_template':'filtered'});self.success(j)
        self.assertEqual(j['total'],2);self.assertFalse(j['safe_to_remove'])
        self.e.presets('工作流',c);restarted=Engine(self.state,[self.src],[self.a,self.b])
        try:self.assertEqual(restarted.presets()['工作流']['project'],'晨曦');self.assertFalse(restarted.presets()['工作流']['auto'])
        finally:restarted.db.close()
        with self.assertRaises(ValueError):self.e.configure({'directory_template':'../bad'})
        with self.assertRaises(ValueError):self.e.configure({'date_from':'2026-11-01','date_to':'2026-01-01'})
    def test_conflict_protection_skip_and_overwrite(self):
        p=self.put('PANORAMA/001_0061/frame.JPG',b'original');j=self.run_job();self.success(j)
        p.write_bytes(b'changed!');j=self.run_job();self.assertEqual(j['status'],'failed');self.assertFalse(j['safe_to_remove'])
        j=self.run_job(options={'conflict':'skip'});self.assertEqual(j['status'],'failed');self.assertFalse(j['safe_to_remove'])
        j=self.run_job(options={'conflict':'overwrite'});self.success(j)
        self.assertEqual((self.a/'source/全景序列/001_0061/frame.JPG').read_bytes(),b'changed!')
    def test_target_timestamp_refresh_vs_tamper(self):
        self.put('a.JPG',b'good');save=self.e.save_job;changed=[False]
        def mutate(j):
            if j.get('primary_verified') and not changed[0]:changed[0]=True;(self.a/'source/JPG/a.JPG').write_bytes(b'evil')
            save(j)
        self.e.save_job=mutate;j=self.run_job();self.assertEqual(j['status'],'failed');self.assertFalse(j['safe_to_remove']);self.assertFalse(j['primary_verified'])
    def test_exclusive_fallback_preserves_content(self):
        self.put('photo.JPG',b'fallback')
        with patch('core.os.link',side_effect=OSError(errno.EOPNOTSUPP,'unsupported')):j=self.run_job()
        self.success(j);self.assertEqual((self.b/'source/JPG/photo.JPG').read_bytes(),b'fallback')
    def test_queue_freezes_rules_removal_and_retry(self):
        self.put('one.JPG',b'one');entered=threading.Event();release=threading.Event();original=self.e.copy
        def block(*args):
            if not entered.is_set():entered.set();release.wait(5)
            return original(*args)
        self.e.copy=block
        first=self.e.submit(str(self.src));self.assertTrue(entered.wait(5))
        second=self.e.submit(str(self.src),{'directory_template':'queued'},enqueue=True)
        self.e.configure({'directory_template':'changed'})
        third=self.e.submit(str(self.src),enqueue=True);self.e.remove(third['id'])
        with self.assertRaises(ValueError):self.e.remove(first['id'])
        release.set();self.wait();self.success(first);self.success(second)
        self.assertTrue((self.a/'queued/JPG/one.JPG').exists());self.assertFalse((self.a/'changed').exists())
        retried=self.e.retry(second['id']);self.wait();self.success(retried);self.assertEqual(retried['copied'],0)
        self.e.remove(second['id']);self.assertTrue((self.a/'queued/JPG/one.JPG').exists())
    def test_reports_mhl_xml_escape_and_no_incomplete_mhl(self):
        self.put('photo&1.JPG',b'metadata');j=self.run_job(options={'verify':'md5'});self.success(j)
        for kind in ['json','txt','html','checksums','mhl']:
            body,mime,ext=export(j,kind);self.assertTrue(body)
            self.assertTrue((self.state/'reports'/(j['id']+'.'+ext)).exists())
        self.assertIn(b'&amp;',export(j,'mhl')[0]);self.assertIn(b'&amp;',export(j,'html')[0])
        broken=dict(j,status='failed')
        with self.assertRaises(ValueError):export(broken,'mhl')
    def test_safe_signal_only_after_all_targets_full_content(self):
        self.put('a.JPG',b'a');self.put('notes.txt',b'notes')
        seen=[];orig=self.e.save_job
        def save(j):seen.append((j['status'],j.get('safe_to_remove')));orig(j)
        self.e.save_job=save;j=self.run_job();self.success(j)
        self.assertTrue(j['safe_to_remove']);self.assertTrue(all(not value for status,value in seen if status!='completed'))
        j=self.run_job(options={'media_only':True,'directory_template':'subset'});self.success(j);self.assertFalse(j['safe_to_remove'])

if __name__=='__main__':unittest.main()
