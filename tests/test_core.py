import unittest, tempfile, sys, time, json, threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from core import Engine, category, safe_path, mount_candidates, detect, reader_info
class IngestTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()
        self.src=self.root/'sources'/'CARD'; self.a=self.root/'dest'/'primary'; self.b=self.root/'dest'/'backup'; self.c=self.root/'dest'/'backup2'
        for p in (self.src,self.a,self.b,self.c): p.mkdir(parents=True)
        self.e=Engine(self.root/'state',[self.src.parent],[self.a,self.b,self.c]); self.e.configure({'primary':str(self.a),'backups':[str(self.b)]})
    def tearDown(self): self.e.db.close(); self.tmp.cleanup()
    def run_job(self):
        j=self.e.submit(str(self.src))
        deadline=time.time()+10
        while self.e.active and time.time()<deadline: time.sleep(.01)
        self.assertFalse(self.e.active); return j
    def test_primary_only_modes_and_duplicate(self):
        self.e.configure({'backups':[]})
        for mode in ('quick','md5','sha256'):
            self.e.configure({'verify':mode}); (self.src/(mode+'.jpg')).write_bytes(b'original-'+mode.encode())
            j=self.run_job(); self.assertEqual(j['status'],'completed'); self.assertTrue(j['safe_to_remove'])
            self.assertEqual(j['destinations'],{str(self.a):'verified'})
            self.assertEqual(j['done'],j['total']); self.assertEqual(j['bytes_done'],j['bytes_total'])
            self.assertIn('未设置备份',j['phase']); self.assertEqual(list(self.b.rglob('*')),[])
            self.assertEqual((self.a/'CARD/JPG'/(mode+'.jpg')).read_bytes(),b'original-'+mode.encode())
        j=self.run_job(); self.assertEqual(j['copied'],0); self.assertEqual(j['skipped'],3)
    def test_primary_only_auto_and_persistence(self):
        self.e.configure({'backups':[],'auto':True}); (self.src/'auto.jpg').write_bytes(b'auto-media')
        self.e.devices=lambda:[{'identity':'card','brand':'Sony','name':'card','path':str(self.src)}]
        self.e.monitor_once(); self.assertFalse(self.e.jobs); self.e.monitor_once()
        deadline=time.time()+10
        while self.e.active and time.time()<deadline: time.sleep(.01)
        self.assertFalse(self.e.active); self.assertEqual(next(iter(self.e.jobs.values()))['status'],'completed')
        restarted=Engine(self.root/'state',self.e.sources,self.e.targets)
        try: self.assertTrue(restarted.config['auto']); self.assertEqual(restarted.config['backups'],[])
        finally: restarted.db.close()
    def test_optional_backup_can_be_added_after_primary_only(self):
        (self.src/'x.jpg').write_bytes(b'media'); self.e.configure({'backups':[]}); self.run_job()
        self.e.configure({'backups':[str(self.b)]}); j=self.run_job()
        self.assertEqual(j['status'],'completed'); self.assertEqual(j['skipped'],1); self.assertEqual(j['copied'],1)
        self.assertEqual((self.b/'CARD/JPG/x.jpg').read_bytes(),b'media')
    def test_primary_only_failure_not_safe(self):
        self.e.configure({'backups':[]}); (self.src/'x.jpg').write_bytes(b'media')
        self.e.copy=lambda *args: (_ for _ in ()).throw(OSError('disk full'))
        j=self.run_job(); self.assertEqual(j['status'],'failed'); self.assertFalse(j['safe_to_remove'])
    def test_auto_still_requires_primary(self):
        with self.assertRaises(ValueError): self.e.configure({'auto':True,'primary':'','backups':[]})
    def test_two_copies_and_duplicate_repair(self):
        (self.src/'a.ARW').write_bytes(b'raw-data'); (self.src/'b.JPG').write_bytes(b'photo')
        (self.src/'c.LRV').write_bytes(b'proxy'); (self.src/'skip.txt').write_text('skip')
        j=self.run_job(); self.assertEqual(j['status'],'completed'); self.assertEqual(j['copied'],6); self.assertTrue(j['safe_to_remove'])
        self.assertTrue(all(s=='verified' for s in j['destinations'].values()))
        for dest in (self.a,self.b): self.assertEqual((dest/'CARD/RAW/a.ARW').read_bytes(),b'raw-data')
        j=self.run_job(); self.assertEqual(j['skipped'],6)
        (self.b/'CARD/RAW/a.ARW').unlink(); j=self.run_job(); self.assertEqual(j['copied'],1)
    def test_conflict_preserves_original(self):
        f=self.src/'a.jpg'; f.write_bytes(b'111'); self.run_job(); f.write_bytes(b'222'); j=self.run_job()
        self.assertEqual(j['status'],'completed'); self.assertEqual((self.a/'CARD/JPG/a.jpg').read_bytes(),b'111'); self.assertEqual(len(list((self.a/'CARD/JPG').glob('*.jpg'))),2)
    def test_modes(self):
        for mode in ('quick','md5','sha256'):
            self.e.configure({'verify':mode}); (self.src/(mode+'.wav')).write_bytes(b'audio'); self.assertEqual(self.run_job()['status'],'completed')
    def test_failure_before_primary_not_safe(self):
        (self.src/'x.jpg').write_bytes(b'x'); self.e.copy=lambda *args: (_ for _ in ()).throw(OSError('disk full'))
        j=self.run_job(); self.assertEqual(j['status'],'failed'); self.assertFalse(j['safe_to_remove']); self.assertEqual(j['destinations'][str(self.b)],'pending')
    def test_backup_failure_keeps_primary(self):
        (self.src/'x.jpg').write_bytes(b'x'); orig=self.e.copy
        def copy(src,dst,*args):
            if str(dst).startswith(str(self.b)): raise OSError('backup unavailable')
            return orig(src,dst,*args)
        self.e.copy=copy; j=self.run_job(); self.assertTrue(j['safe_to_remove']); self.assertEqual(j['status'],'failed'); self.assertEqual(j['destinations'][str(self.b)],'failed')
    def test_source_removed_after_primary(self):
        f=self.src/'x.jpg'; f.write_bytes(b'x'); orig=self.e.save_job
        def save(j):
            if j['safe_to_remove'] and f.exists(): f.unlink()
            orig(j)
        self.e.save_job=save; self.assertEqual(self.run_job()['status'],'completed')
    def test_symlinks_and_overlap(self):
        outside=self.root/'outside'; outside.mkdir(); (self.src/'link').symlink_to(outside)
        with self.assertRaises(ValueError): safe_path(str(self.src/'link'),[self.src])
        with self.assertRaises(ValueError): safe_path(str(self.src/'../other'),[self.src])
        self.e.targets.append(self.src)
        self.e.configure({'primary':str(self.src)})
        with self.assertRaises(ValueError): self.e.submit(str(self.src))
    def test_classification(self):
        for p,c in [('DCIM/a.ARW','RAW'),('a.JPG','JPG'),('a.mov','视频'),('a.WAV','声音'),('PRIVATE/M4ROOT/SUB/C0001S03.MP4','视频代理'),('a.lrv','视频代理')]: self.assertEqual(category(Path(p)),c)
    def test_brand_signatures(self):
        for folder,brand in [('PRIVATE/M4ROOT','Sony'),('DCIM/100CANON','Canon'),('DCIM/100NIKON','Nikon'),('DCIM/100_PANA','Panasonic'),('ARRI','ARRI'),('DCIM/DJI_001','DJI')]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d); (root/folder).mkdir(parents=True); self.assertEqual(detect(root)['brand'],brand)
    def wait_until(self, predicate):
        deadline=time.monotonic()+5
        while not predicate() and time.monotonic()<deadline: time.sleep(.01)
        self.assertTrue(predicate())
    def controlled_copy(self, terminate=False):
        (self.src/'large.mov').write_bytes(b'X'*(12*1024*1024))
        reached=threading.Event(); release=threading.Event(); checkpoint=self.e.checkpoint
        def barrier():
            job=getattr(self.e.local,'job',None)
            if job and job.get('transferred_bytes',0)>=4*1024*1024 and not reached.is_set():
                reached.set(); release.wait(5)
            checkpoint()
        self.e.checkpoint=barrier
        j=self.e.submit(str(self.src)); self.assertTrue(reached.wait(5))
        self.e.control(j['id'],'pause'); release.set(); self.wait_until(lambda:j['status']=='paused')
        transferred=j['transferred_bytes']; time.sleep(.1); self.assertEqual(j['transferred_bytes'],transferred)
        self.assertGreater(j['speed_bps'],0); self.assertTrue(self.e.active)
        self.e.control(j['id'],'stop' if terminate else 'resume')
        self.wait_until(lambda:not self.e.active)
        return j
    def test_pause_resume_mid_file(self):
        j=self.controlled_copy(); self.assertEqual(j['status'],'completed'); self.assertEqual(j['transferred_bytes'],24*1024*1024)
        self.assertGreater(self.e.controls[j['id']]['paused_seconds'],.08)
    def test_stop_while_paused_cleans_partial_and_disarms_auto(self):
        j=self.controlled_copy(True); self.assertEqual(j['status'],'cancelled'); self.assertTrue(j['io_released']); self.assertFalse(j['safe_to_remove'])
        self.assertFalse(self.e.config['auto']); self.assertEqual(list(self.a.rglob('*.partial')),[]); self.assertEqual(list(self.a.rglob('*.mov')),[])
        with self.assertRaises(ValueError): self.e.preview(str(self.src))
        self.assertEqual(self.run_job()['status'],'completed')
    def test_stop_during_hash_and_terminal_controls(self):
        (self.src/'x.jpg').write_bytes(b'photo')
        original=self.e.hash
        def hashing(p,mode):
            self.e.control(self.e.local.job['id'],'stop'); return original(p,mode)
        self.e.hash=hashing; j=self.run_job(); self.assertEqual(j['status'],'cancelled'); self.assertTrue(j['io_released'])
        with self.assertRaises(ValueError): self.e.control(j['id'],'resume')
    def test_auto_insert_reinsert_and_queue(self):
        self.e.configure({'auto':True}); cards=[]; calls=[]
        self.e.devices=lambda:list(cards)
        self.e.submit=lambda path:calls.append(path)
        a={'identity':'one','brand':'Sony','name':'A','path':str(self.src)}
        b={'identity':'two','brand':'Canon','name':'B','path':str(self.src.parent/'B')}
        self.e.monitor_once(); self.assertEqual(calls,[])
        cards.append(a); self.e.monitor_once(); self.assertEqual(calls,[])
        self.e.monitor_once(); self.assertEqual(calls,[a['path']])
        self.e.monitor_once(); self.assertEqual(len(calls),1)
        self.e.active=True; cards.append(b); self.e.monitor_once(); self.e.monitor_once(); self.assertEqual(len(calls),1)
        self.e.active=False; self.e.monitor_once(); self.assertEqual(calls[-1],b['path'])
        cards.clear(); self.e.monitor_once(); cards.append(a); self.e.monitor_once(); self.e.monitor_once(); self.assertEqual(len(calls),3)
    def test_auto_pause_unknown_and_restart(self):
        self.e.configure({'auto':True})
        restarted=Engine(self.root/'state',self.e.sources,self.e.targets)
        try: self.assertTrue(restarted.config['auto'])
        finally: restarted.db.close()
        calls=[]; self.e.submit=lambda p:calls.append(p)
        self.e.devices=lambda:[{'identity':'unknown','brand':'','name':'unknown','path':'/unknown'}]
        self.e.monitor_once(); self.e.monitor_once(); self.assertEqual(calls,[])
        self.e.devices=lambda:[{'identity':'card','brand':'Sony','name':'card','path':str(self.src)}]
        self.e.configure({'auto':False}); self.e.monitor_once(); self.e.monitor_once(); self.assertEqual(calls,[])
        self.e.configure({'auto':True}); self.e.monitor_once(); self.assertEqual(calls,[str(self.src)])
    def test_primary_tampering_blocks_backup(self):
        (self.src/'x.jpg').write_bytes(b'good'); orig=self.e.save_job; altered=[False]
        def save(j):
            if j['safe_to_remove'] and not altered[0]:
                altered[0]=True; (self.a/'CARD/JPG/x.jpg').write_bytes(b'evil')
            orig(j)
        self.e.save_job=save; j=self.run_job(); self.assertEqual(j['status'],'failed'); self.assertFalse((self.b/'CARD/JPG/x.jpg').exists()); self.assertFalse(j['safe_to_remove'])
    def test_modified_source_blocks_safe_signal(self):
        p=self.src/'x.jpg'; p.write_bytes(b'good'); orig=self.e.copy
        def copy(*args):
            result=orig(*args); p.write_bytes(b'changed'); return result
        self.e.copy=copy; j=self.run_job(); self.assertEqual(j['status'],'failed'); self.assertFalse(j['safe_to_remove'])
    def test_system_raid_members_are_filtered(self):
        sysroot=self.root/'sys'; disk=sysroot/'devices/usb1/block/sda'; (disk/'sda1').mkdir(parents=True); (disk/'sda1/partition').write_text('1'); (disk/'removable').write_text('1')
        md=sysroot/'devices/virtual/block/md0'; (md/'slaves').mkdir(parents=True); (md/'slaves/sda1').symlink_to(disk/'sda1')
        links=sysroot/'dev/block'; links.mkdir(parents=True); (links/'8:1').symlink_to(disk/'sda1'); (links/'9:0').symlink_to(md)
        mount=self.root/'mountinfo'; mount.write_text(f'22 1 8:1 / {self.src} rw - exfat /dev/sda1 rw\n23 1 9:0 / / rw - ext4 /dev/md0 rw\n')
        self.assertEqual(mount_candidates([self.src.parent],str(mount),str(sysroot)),[])
    def test_reject_more_than_one_backup(self):
        with self.assertRaises(ValueError): self.e.configure({'backups':[str(self.b),str(self.c)]})
    def test_empty_does_not_signal_safe(self):
        j=self.run_job(); self.assertEqual(j['status'],'failed'); self.assertFalse(j['safe_to_remove'])
    def test_quick_duplicate_uses_hash(self):
        self.e.configure({'verify':'quick'}); (self.src/'x.jpg').write_bytes(b'aaa'); self.run_job(); (self.src/'x.jpg').write_bytes(b'bbb'); j=self.run_job(); self.assertEqual(j['copied'],2)
    def test_discovery_filters_virtual_and_system(self):
        sysroot=self.root/'sys'; dev=sysroot/'devices/usb1/block/sda'; (dev/'sda1').mkdir(parents=True); (dev/'sda1/partition').write_text('1'); (dev/'removable').write_text('1'); links=sysroot/'dev/block'; links.mkdir(parents=True); (links/'8:1').symlink_to(dev/'sda1')
        mount=self.root/'mountinfo'; mount.write_text(f'22 1 8:1 / {self.src} rw - exfat /dev/sda1 rw\n')
        self.assertEqual(len(mount_candidates([self.src.parent],str(mount),str(sysroot))),1)
        mount.write_text(mount.read_text()+f'23 1 8:1 / /boot rw - ext4 /dev/sda1 rw\n'); self.assertEqual(mount_candidates([self.src.parent],str(mount),str(sysroot)),[])
        mount.write_text(f'22 1 8:1 / {self.src} rw - iso9660 /dev/sda1 rw\n'); self.assertEqual(mount_candidates([self.src.parent],str(mount),str(sysroot)),[])
    def test_reader_topology_evidence(self):
        usb=self.root/'sys/devices/usb1/1-2'; disk=usb/'1-2:1.0/host4/target4:0:0/4:0:0:1/block/sde/sde1'
        disk.mkdir(parents=True)
        (usb/'idVendor').write_text('1234'); (usb/'idProduct').write_text('5678')
        info=reader_info(disk); self.assertEqual(info['origin'],'unknown'); self.assertTrue(info['reader_id'].endswith(':slot1'))
        for value,expected in [('fixed','internal'),('removable','usb'),('unknown','unknown')]:
            (usb/'removable').write_text(value); self.assertEqual(reader_info(disk)['origin'],expected)
        mmc=self.root/'sys/devices/pci/mmc_host/mmc0/mmc0:0001/block/mmcblk0'; mmc.mkdir(parents=True)
        self.assertEqual(reader_info(mmc)['origin'],'internal')
    def test_reader_names_persist_and_override(self):
        def device(key): return dict(external=True,reader_id=key,origin='unknown',name='sde1')
        first=device('usb:port1'); self.e.name_reader(first); self.assertTrue(first['display_name'].endswith('SD-01'))
        self.e.set_reader_origin('usb:port1','internal')
        second=device('usb:port2'); self.e.name_reader(second); self.assertTrue(second['display_name'].endswith('SD-02'))
        restarted=Engine(self.root/'state',[self.src.parent],[self.a,self.b])
        try:
            first=device('usb:port1'); restarted.name_reader(first)
            self.assertEqual(first['display_name'],'NAS内置读卡器 · SD-01')
            restarted.set_reader_origin('usb:port1','auto'); first=device('usb:port1'); restarted.name_reader(first)
            self.assertEqual(first['origin'],'unknown')
        finally: restarted.db.close()
        manual=dict(external=False,name='test'); self.e.name_reader(manual); self.assertEqual(manual['display_name'],'手动目录 · test')
        with self.assertRaises(ValueError): self.e.set_reader_origin('usb:port1','invalid')
if __name__=='__main__': unittest.main()
