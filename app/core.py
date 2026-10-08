import os, re, json, time, hashlib, sqlite3, threading, uuid, stat, subprocess
from pathlib import Path

RAW = set('arw cr2 cr3 nef nrw rw2 dng raf srw'.split())
VIDEO = set('mp4 mov mxf mts m2ts avi crm r3d braw insv arx ari'.split())
MEDIA = {'RAW': RAW, 'JPG': {'jpg','jpeg'}, '其他图片': set('png tif tiff heic hif'.split()), '视频': VIDEO, '声音': set('wav mp3 aac flac m4a aif aiff ogg'.split()), '视频代理': {'lrv'}}
BRANDS = ['Sony', 'Canon', 'Nikon', 'Panasonic', 'ARRI', 'DJI', '手动 / 其他']
def category(p):
    ext=p.suffix.lower()[1:]
    proxy_dirs={'proxy','proxies','sub','subclip','lowres'}
    if ext=='lrv' or (ext in VIDEO and (any(x.lower() in proxy_dirs for x in p.parts[:-1]) or re.search(r'(?:_proxy|_px|_s03)$',p.stem,re.I))): return '视频代理'
    return next((k for k,v in MEDIA.items() if ext in v), None)
def inside(p, root):
    try: p.relative_to(root); return True
    except ValueError: return False

def safe_path(value, roots, exists=True):
    p = Path(value)
    if not p.is_absolute() or any(x == '..' for x in p.parts): raise ValueError('必须使用绝对路径，禁止 ..')
    # Reject symlinks in every existing component, including destination directories.
    for parent in [p] + list(p.parents):
        if parent.is_symlink(): raise ValueError('不允许符号链接路径')
    p = p.resolve()
    if not any(inside(p, r) for r in roots): raise ValueError('路径超出允许的挂载目录')
    if exists and not p.is_dir(): raise ValueError('目录不存在或设备已拔出')
    return p

def browse_directories(value, roots, labels=None):
    """List only configured storage roots and their non-symlink directories."""
    labels = labels or {}
    entries = []
    candidates = roots if not value else safe_path(value, roots).iterdir()
    for d in candidates:
        try:
            if d.is_symlink() or not d.is_dir(): continue
            if value and (d.name.startswith(('.', '@')) or d.name in ('lost+found', '$RECYCLE.BIN', 'System Volume Information')): continue
            d = safe_path(str(d), roots)
            entry = {'path': str(d), 'name': labels.get(str(d), d.name), 'writable': os.access(d, os.W_OK | os.X_OK)}
            if not value:
                v = os.statvfs(d)
                entry.update(total=v.f_blocks*v.f_frsize, free=v.f_bavail*v.f_frsize)
            entries.append(entry)
        except (OSError, ValueError):
            continue
    entries.sort(key=lambda e: e['name'].casefold())
    p = safe_path(value, roots) if value else None
    parent = str(p.parent) if p and any(inside(p.parent, root) for root in roots) else ''
    return {'path': str(p) if p else '', 'parent': parent,
            'writable': bool(p and os.access(p, os.W_OK | os.X_OK)),
            'directories': [e['path'] for e in entries], 'entries': entries}

def physical_overlap(a, b):
    # Bind mounts may expose the same directory under unrelated path names.
    return any(a.samefile(p) for p in [b] + list(b.parents)) or any(b.samefile(p) for p in [a] + list(a.parents))

def files(root, media=False):
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink() and d not in ('$RECYCLE.BIN', 'System Volume Information'))
        for name in sorted(names):
            p = Path(base)/name
            if name.startswith('.') or p.is_symlink(): continue
            if stat.S_ISREG(p.stat().st_mode) and (not media or category(p)): yield p

def detect(root):
    paths = []
    for base, dirs, names in os.walk(root):
        if len(Path(base).relative_to(root).parts) >= 3: dirs[:] = []
        dirs[:] = [d for d in dirs if not (Path(base)/d).is_symlink() and not d.startswith('.')]
        paths.extend(str((Path(base)/n).relative_to(root)).upper() for n in dirs + names[:50])
        if len(paths) > 500: break
    joined = '\n'.join(paths)
    patterns = [('Sony', r'PRIVATE/M4ROOT|AVF_INFO|\d{3}MSDCF'), ('Canon', r'CANON|CANONMSC'), ('Nikon', r'NIKON|NCFL|\d{3}NCD'), ('Panasonic', r'PANA|\d{3}.*_PANA'), ('ARRI', r'ARRI|\.ARI$|\.ARX$'), ('DJI', r'DJI|\d{3}MEDIA')]
    brand = next((b for b, pat in patterns if re.search(pat, joined, re.M)), '')
    model, evidence = '', '目录特征' if brand else '未识别，可手动指定'
    # ExifTool supports manufacturer/model fields across stills and several video containers.
    candidates = []
    for p in files(root, True):
        candidates.append(str(p))
        if len(candidates) == 5: break
    if candidates:
        try:
            data = json.loads(subprocess.check_output(['exiftool','-json','-Make','-Model','-CameraModelName', *candidates], timeout=15, stderr=subprocess.DEVNULL))
            for item in data:
                make = str(item.get('Make', ''))
                m = str(item.get('Model', item.get('CameraModelName', '')))
                found = next((b for b in BRANDS[:-1] if b.lower() in (make+' '+m).lower()), None)
                if found: brand, model, evidence = found, m, '媒体元数据'; break
        except (OSError, subprocess.SubprocessError, ValueError): pass
    return {'brand': brand, 'model': model, 'evidence': evidence}

def physical_disks(dev, visited=None):
    visited=set() if visited is None else visited
    dev=dev.resolve()
    if dev in visited: return set()
    visited.add(dev)
    if (dev/'partition').exists(): dev=dev.parent
    slaves=list((dev/'slaves').iterdir()) if (dev/'slaves').is_dir() else []
    if slaves: return set().union(*(physical_disks(s,visited) for s in slaves))
    return {dev}

def reader_info(dev):
    """Use topology evidence; a USB bus alone does not prove external placement."""
    dev=Path(dev).resolve()
    scsi=next((p for p in reversed(dev.parts) if re.fullmatch(r'\d+:\d+:\d+:\d+',p)), '')
    slot=scsi.split(':')[-1] if scsi else '0'
    for parent in [dev]+list(dev.parents):
        if (parent/'idVendor').exists() and (parent/'idProduct').exists():
            try: placement=(parent/'removable').read_text().strip()
            except OSError: placement='unknown'
            origin='internal' if placement=='fixed' else ('usb' if placement=='removable' else 'unknown')
            return {'reader_id':'usb:'+str(parent)+':slot'+slot,'transport':'USB','origin':origin,'origin_evidence':'USB 固定连接' if origin=='internal' else ('USB 可拔连接' if origin=='usb' else 'USB 总线无法确定内置或外置')}
    if any(p.startswith('mmc_host') for p in dev.parts):
        host=next((p for p in dev.parents if p.parent.name=='mmc_host'),dev.parent)
        return {'reader_id':'mmc:'+str(host),'transport':'MMC/SD','origin':'internal','origin_evidence':'原生 MMC/SD 控制器'}
    return {'reader_id':'device:'+str(dev.parent if (dev/'partition').exists() else dev),'transport':'未知','origin':'unknown','origin_evidence':'缺少可确定位置的硬件信息'}

def mount_candidates(roots, mountinfo='/proc/self/mountinfo', sysroot='/sys'):
    result = []
    try: lines = Path(mountinfo).read_text().splitlines()
    except OSError: return []
    system_lines=list(lines)
    host_info=os.getenv('HOST_MOUNTINFO','')
    if host_info:
        try: system_lines+=Path(host_info).read_text().splitlines()
        except OSError: raise ValueError('无法读取宿主机挂载表，自动发现已停止')
    for line in lines:
        left, right = line.split(' - ', 1); a, b = left.split(), right.split()
        raw = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1],8)), a[4]); p = Path(raw)
        if not any(inside(p,r) for r in roots) or a[3] != '/': continue
        if b[0] in {'iso9660','udf','squashfs','overlay','tmpfs','proc','sysfs','nfs','cifs'}: continue
        dev = (Path(sysroot)/'dev/block'/a[2]).resolve()
        if not dev.exists() or any(x.startswith(('loop','ram','dm-','md')) for x in dev.parts): continue
        removable = any((q/'removable').exists() and (q/'removable').read_text().strip() == '1' for q in [dev,dev.parent])
        external = 'usb' in str(dev).lower() or removable or any(x.startswith('mmc') for x in dev.parts)
        if not external: continue
        # Exclude physical disks that also host system mounts, even if transported over USB.
        disk = dev.parent if (dev/'partition').exists() else dev
        system = False
        for other in system_lines:
            fields = other.split(' - ',1)[0].split()
            if fields[4] in ('/','/boot','/boot/efi','/usr','/var','/etc'):
                od = (Path(sysroot)/'dev/block'/fields[2]).resolve()
                if physical_disks(disk) & physical_disks(od): system = True
        if not system and p.is_dir(): result.append({'path': str(p), 'identity': a[0]+':'+a[2], 'name': p.name, 'external': True, **reader_info(dev)})
    return result

class TaskCancelled(Exception):
    pass

class Engine:
    def __init__(self, state, sources, targets, manual_roots=()):
        self.state = Path(state); self.state.mkdir(parents=True, exist_ok=True)
        self.auto_sources = [Path(p).resolve() for p in sources]
        self.sources = list(dict.fromkeys(self.auto_sources+[Path(p).resolve() for p in manual_roots])); self.targets = [Path(p).resolve() for p in targets]
        self.local = threading.local(); self.io_lock = threading.RLock(); self.blocked_sources = set(); self.controls = {}
        self.readers = json.loads((self.state/'readers.json').read_text()) if (self.state/'readers.json').exists() else {}
        self.lock = threading.RLock(); self.jobs = {}; self.active = False; self.seen = set(); self.cache = {}; self.scan_error = ''; self.arrivals = {}; self.watch_status = '等待设置自动导入'
        self.config = {'auto': False, 'media_only': True, 'keep_parents': True, 'verify': 'sha256', 'primary': '', 'backups': [], 'brand': '', 'model': '', 'manual_sources': []}
        if (self.state/'config.json').exists(): self.config.update(json.loads((self.state/'config.json').read_text()))
        self.db = sqlite3.connect(str(self.state/'history.sqlite'), check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT)')
        for ident, data in self.db.execute('SELECT id,data FROM jobs ORDER BY rowid DESC LIMIT 100'):
            j = json.loads(data)
            if j['status'] in ('queued','running','pausing','paused','stopping'): j.update(status='interrupted', error='服务重启中断；重新提交将复核已完成文件', safe_to_remove=False)
            self.jobs[ident] = j
    def save_job(self,j):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)',(j['id'],json.dumps(j,ensure_ascii=False))); self.db.commit()
    def configure(self, data):
        with self.lock:
            c = dict(self.config); c.update({k:v for k,v in data.items() if k in c})
            if c['verify'] not in ('quick','md5','sha256'): raise ValueError('无效校验方式')
            for k in ('auto','media_only','keep_parents'):
                if not isinstance(c[k],bool): raise ValueError('无效开关')
            if not isinstance(c['backups'],list) or not isinstance(c['manual_sources'],list): raise ValueError('无效目录列表')
            if len(c['backups'])>1: raise ValueError('支持一个数据拷贝主文件夹和一个可选备份文件夹')
            for p in c['manual_sources']: safe_path(p,self.sources)
            for p in [c['primary']]+c['backups']:
                if p: safe_path(p,self.targets)
            if c['auto'] and not c['primary']: raise ValueError('启用自动导入前请选择数据拷贝主文件夹')
            temp = self.state/'config.tmp'; temp.write_text(json.dumps(c,ensure_ascii=False,indent=2)); os.replace(temp,self.state/'config.json'); self.config=c
            return c
    def control(self, ident, action):
        with self.lock:
            if action not in ('pause','resume','stop'): raise ValueError('无效任务操作')
            j=self.jobs.get(ident); ctl=self.controls.get(ident)
            if not j or not ctl or j['status'] not in ('queued','running','pausing','paused','stopping'): raise ValueError('任务已经结束')
            if j['status']=='stopping': return j
            if action=='stop':
                # Stop auto-start as well, so another card cannot begin while the user ejects.
                c=dict(self.config); c['auto']=False
                temp=self.state/'config.tmp'; temp.write_text(json.dumps(c,ensure_ascii=False)); os.replace(temp,self.state/'config.json'); self.config=c
                self.blocked_sources.add(j['source']); ctl['stop'].set(); ctl['pause'].clear()
                j.update(status='stopping',phase='正在终止，等待文件句柄关闭')
            elif action=='pause': ctl['pause'].set(); j['status']='pausing'
            else:
                ctl['pause'].clear()
                if j['status']=='pausing': j['status']='running'
            self.save_job(j); return j
    def checkpoint(self):
        j=getattr(self.local,'job',None)
        if not j: return
        ctl=self.controls[j['id']]
        if ctl['stop'].is_set(): raise TaskCancelled()
        if ctl['pause'].is_set():
            started=time.monotonic(); ctl['pause_started']=started; phase=j['phase']
            with self.lock:
                if ctl['stop'].is_set(): raise TaskCancelled()
                j.update(status='paused',phase='已暂停 · 继续或终止任务'); self.save_job(j)
            while ctl['pause'].is_set():
                if ctl['stop'].wait(.1): raise TaskCancelled()
            ctl['paused_seconds']+=time.monotonic()-started; ctl.pop('pause_started',None)
            if ctl['stop'].is_set(): raise TaskCancelled()
            with self.lock: j.update(status='running',phase=phase)
        if ctl['stop'].is_set(): raise TaskCancelled()
    def metrics(self,j):
        ctl=self.controls.get(j['id'])
        if not ctl: return
        now=time.monotonic(); waiting=now-ctl['pause_started'] if 'pause_started' in ctl else 0
        elapsed=max(.001,now-ctl['started']-ctl['paused_seconds']-waiting)
        j['elapsed_seconds']=round(elapsed,1)
        j['speed_bps']=j.get('transferred_bytes',0)/elapsed
    def save_readers(self):
        temp=self.state/'readers.tmp'; temp.write_text(json.dumps(self.readers,ensure_ascii=False,indent=2)); os.replace(temp,self.state/'readers.json')
    def set_reader_origin(self, ident, origin):
        if origin not in ('auto','internal','usb'): raise ValueError('无效读卡器来源')
        with self.lock:
            if ident not in self.readers: raise ValueError('读卡器尚未发现')
            self.readers[ident]['origin_override']=origin; self.save_readers()
    def name_reader(self,d):
        if not d['external']:
            d.update(display_name='手动目录 · '+d['name'],reader_id='',origin='manual'); return
        ident=d['reader_id']
        with self.lock:
            if ident not in self.readers:
                self.readers[ident]={'number':max((r['number'] for r in self.readers.values()),default=0)+1,'origin_override':'auto'}; self.save_readers()
            saved=self.readers[ident]; override=saved.get('origin_override','auto')
            if override!='auto': d.update(origin=override,origin_evidence='用户指定，按读卡器接口记忆')
            label={'internal':'NAS内置读卡器','usb':'USB外置读卡器','unknown':'读卡器（位置待确认）'}[d['origin']]
            d.update(display_name=label+' · SD-'+str(saved['number']).zfill(2),origin_override=override)
    def devices(self):
        with self.io_lock: return self._devices()
    def _devices(self):
        cards = mount_candidates(self.auto_sources)
        for p in self.config['manual_sources']:
            if Path(p).is_dir() and not any(d['path']==p for d in cards): cards.append({'path':p,'identity':'manual:'+p,'name':Path(p).name,'external':False})
        for d in cards:
            self.name_reader(d)
            key=d['identity']
            if key not in self.cache:
                self.cache[key]={'brand':'','model':'','evidence':'任务已终止，等待拔卡或手动重新开始'} if d['path'] in self.blocked_sources else detect(Path(d['path']))
            d.update(self.cache[key]); v=os.statvfs(d['path']); d.update(total=v.f_blocks*v.f_frsize,free=v.f_bavail*v.f_frsize)
        return cards
    def preview(self,value):
        with self.io_lock:
            if any(inside(Path(value).resolve(),Path(p)) for p in self.blocked_sources): raise ValueError('此卡已停止访问；重新开始任务后可预览')
            return self._preview(value)
    def _preview(self,value):
        root=safe_path(value,self.sources); counts={k:0 for k in MEDIA}; total=0; rows=[]; n=0
        for p in files(root):
            s=p.stat().st_size; total+=s; n+=1; cat=category(p)
            if cat: counts[cat]+=1
            if len(rows)<200: rows.append({'path':str(p.relative_to(root)),'size':s,'category':cat or '其他'})
        return {'path':str(root),'count':n,'bytes':total,'counts':counts,'files':rows,'camera':detect(root)}
    def submit(self, source, options=None):
        with self.lock:
            if self.active: raise ValueError('已有任务执行中，请等待完成')
            c=dict(self.config); c.update(options or {})
            root=safe_path(source,self.sources); primary=safe_path(c['primary'],self.targets)
            if not isinstance(c['backups'],list) or len(c['backups'])>1: raise ValueError('最多选择一个数据拷贝备份文件夹')
            backups=[safe_path(p,self.targets) for p in c['backups']]
            paths=[root,primary]+backups
            for i,a in enumerate(paths):
                for b in paths[i+1:]:
                    if inside(a,b) or inside(b,a) or physical_overlap(a,b): raise ValueError('源目录、主文件夹和备份目录不能相同或互相包含')
            if c['verify'] not in ('quick','md5','sha256'): raise ValueError('无效校验方式')
            ident=uuid.uuid4().hex[:12]
            j={'id':ident,'source':str(root),'status':'queued','phase':'等待','created':time.time(),'done':0,'total':0,'bytes_done':0,'bytes_total':0,'destinations':{},'manifest':[],'copied':0,'skipped':0,'safe_to_remove':False,'error':'','options':c}
            self.blocked_sources.discard(str(root))
            self.controls[ident]={'stop':threading.Event(),'pause':threading.Event(),'started':time.monotonic(),'paused_seconds':0}
            j.update(transferred_bytes=0,speed_bps=0,io_released=False)
            self.jobs[ident]=j; self.save_job(j); self.active=True
            threading.Thread(target=self.run,args=(j,root,primary,backups,c),daemon=True).start(); return j
    def hash(self,p,algorithm):
        h=hashlib.new(algorithm)
        with open(p,'rb') as f:
            while True:
                self.checkpoint(); chunk=f.read(4*1024*1024)
                if not chunk: break
                h.update(chunk)
        return h.hexdigest()
    def equal(self,a,b,mode):
        if not b.is_file() or b.is_symlink() or a.stat().st_size != b.stat().st_size: return False
        return mode=='quick' or self.hash(a,mode)==self.hash(b,mode)
    def copy(self,src,dst,mode,j):
        safe_path(str(dst.parent),self.targets,False); dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.exists() or dst.is_symlink():
            # Existing content is always hashed: quick mode must not silently skip same-size different files.
            if self.equal(src,dst,mode if mode!='quick' else 'sha256'): j['skipped']+=1; return dst
            suffix=self.hash(src,'sha256')[:16]; dst=dst.with_name(dst.stem+'__'+suffix+dst.suffix)
            if dst.exists() or dst.is_symlink():
                if self.equal(src,dst,'sha256'): j['skipped']+=1; return dst
                raise ValueError('冲突目标已存在且内容不同：'+str(dst))
        before=src.stat(); temp=dst.with_name('.'+dst.name+'.'+j['id']+'.partial')
        try:
            with open(src,'rb') as r, open(temp,'xb') as w:
                while True:
                    self.checkpoint(); chunk=r.read(4*1024*1024)
                    if not chunk: break
                    w.write(chunk); j['transferred_bytes']=j.get('transferred_bytes',0)+len(chunk); self.metrics(j)
                w.flush(); os.fsync(w.fileno())
            after=src.stat()
            if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino): raise ValueError('源文件在复制期间发生变化')
            if not self.equal(src,temp,mode): raise ValueError('校验失败：'+str(src))
            os.utime(temp,ns=(before.st_atime_ns,before.st_mtime_ns))
            # Hard link publishes atomically and refuses to overwrite a concurrently created file.
            self.checkpoint()
            os.link(temp,dst); temp.unlink()
            fd=os.open(str(dst.parent),os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
            j['copied']+=1; return dst
        finally:
            if temp.exists(): temp.unlink()
    def run(self,j,root,primary,backups,c):
        self.local.job=j
        try:
            self.checkpoint()
            j.update(status='running',phase='扫描媒体'); self.save_job(j)
            source_device=root.stat().st_dev
            destination_devices={p:p.stat().st_dev for p in [primary]+backups}
            manifest=[]
            for p in files(root,c['media_only']):
                self.checkpoint(); manifest.append((p,p.relative_to(root),p.stat().st_size))
            j['destinations']={str(p):'pending' for p in [primary]+backups}
            if not manifest: raise ValueError('没有可拷贝文件')
            j.update(total=len(manifest)*(1+len(backups)),bytes_total=sum(s for _,_,s in manifest)*(1+len(backups)))
            # Stable source namespace prevents unrelated cards from clobbering one another; conflicts remain content-safe.
            namespace=re.sub(r'[^\w.-]','_',root.name) or 'Card'
            ready=[]; j['phase']='主文件夹拷贝与校验'; j['destinations'][str(primary)]='running'
            for p,rel,size in manifest:
                self.checkpoint()
                if root.stat().st_dev!=source_device or primary.stat().st_dev!=destination_devices[primary]: raise ValueError('源卡或主文件夹挂载发生变化')
                if c['media_only']: rel=Path(category(p))/(rel if c['keep_parents'] else Path(rel.name))
                fingerprint=self.hash(p,'sha256') if c['verify']!='quick' else None
                source_stat=p.stat()
                out=self.copy(p,primary/namespace/rel,c['verify'],j)
                if fingerprint and self.hash(out,'sha256')!=fingerprint: raise ValueError('主文件夹与源指纹不一致')
                ready.append((out,out.relative_to(primary),size,fingerprint))
                j['manifest'].append({'source':str(p.relative_to(root)),'destination':str(out.relative_to(primary)),'bytes':size,'sha256':fingerprint,'mtime_ns':source_stat.st_mtime_ns})
                j['done']+=1; j['bytes_done']+=size; self.save_job(j)
            # Recheck full source manifest before declaring that every selected source file is on primary.
            current=[(str(p.relative_to(root)),p.stat().st_size,p.stat().st_mtime_ns) for p in files(root,c['media_only'])]
            if current != [(m['source'],m['bytes'],m['mtime_ns']) for m in j['manifest']]: raise ValueError('存储卡内容发生变化，请重新导入')
            for p,rel,size,fingerprint in ready:
                if not p.is_file() or p.stat().st_size!=size or (fingerprint and self.hash(p,'sha256')!=fingerprint): raise ValueError('主文件夹最终复核失败：'+str(p))
            if primary.stat().st_dev!=destination_devices[primary]: raise ValueError('主文件夹挂载发生变化')
            j['destinations'][str(primary)]='verified'
            j.update(safe_to_remove=True,phase='主文件夹校验完成，可拔卡'); self.save_job(j)
            for index,backup in enumerate(backups):
                j['phase']='从主文件夹复制到备份 '+str(index+1); j['destinations'][str(backup)]='running'; self.save_job(j)
                for p,rel,size,fingerprint in ready:
                    if primary.stat().st_dev!=destination_devices[primary]:
                        j['safe_to_remove']=False; j['destinations'][str(primary)]='failed'; raise ValueError('主文件夹挂载发生变化')
                    if backup.stat().st_dev!=destination_devices[backup]: raise ValueError('备份文件夹挂载发生变化')
                    if fingerprint and self.hash(p,'sha256')!=fingerprint:
                        j['safe_to_remove']=False; j['destinations'][str(primary)]='failed'; raise ValueError('主文件夹文件在备份前发生变化：'+str(p))
                    out=self.copy(p,backup/rel,c['verify'],j)
                    if fingerprint and self.hash(out,'sha256')!=fingerprint: raise ValueError('备份与原始指纹不一致：'+str(out))
                    j['done']+=1; j['bytes_done']+=size; self.save_job(j)
                j['destinations'][str(backup)]='verified'
            self.checkpoint()
            j.update(status='completed',phase='主文件夹与备份文件夹均已校验完成' if backups else '主文件夹拷贝与校验完成（未设置备份）')
        except TaskCancelled:
            j.update(status='stopping',phase='正在终止，等待文件句柄关闭',error='')
            for dest,status in j['destinations'].items():
                if status=='running': j['destinations'][dest]='cancelled'
        except Exception as e:
            j.update(status='failed',error=str(e),phase='任务失败')
            for dest,status in j['destinations'].items():
                if status=='running': j['destinations'][dest]='failed'
        finally:
            try:
                # Wait for an existing metadata scan/preview to release its file handles.
                with self.io_lock:
                    if self.controls[j['id']]['stop'].is_set() and j['status']!='failed':
                        j.update(status='cancelled',phase='已终止 · 拷贝未全部完成')
                    j['io_released']=True
                    self.metrics(j); j['finished']=time.time(); self.save_job(j)
            finally:
                self.local.job=None
                with self.lock: self.active=False
    def monitor_once(self):
        devices=self.devices(); present={d['identity'] for d in devices}
        self.blocked_sources.intersection_update({d['path'] for d in devices})
        self.seen.intersection_update(present)
        self.cache={k:v for k,v in self.cache.items() if k in present}
        self.arrivals={k:v for k,v in self.arrivals.items() if k in present}
        for d in devices:
            self.arrivals[d['identity']]=self.arrivals.get(d['identity'],0)+1
        if not self.config['auto']:
            self.watch_status='自动导入已暂停'; return
        if self.active:
            self.watch_status='正在导入；新接入的卡片将在当前任务完成后处理'; return
        self.watch_status='等待插卡 · 自动识别与导入'
        for d in devices:
            ident=d['identity']
            if ident in self.seen or d['path'] in self.blocked_sources: continue
            if self.arrivals[ident]<2:
                self.watch_status='检测到存储设备，等待挂载稳定'; continue
            if not (d['brand'] or d['path'] in self.config['manual_sources']):
                self.watch_status='发现未识别设备，请手动指定媒体目录'; continue
            self.submit(d['path']); self.seen.add(ident)
            self.watch_status='已自动开始导入：'+d['name']; break
    def monitor(self):
        while True:
            try:
                self.monitor_once(); self.scan_error=''
            except Exception as e:
                self.scan_error=str(e); self.watch_status='自动导入等待处理：'+str(e)
            time.sleep(2)
