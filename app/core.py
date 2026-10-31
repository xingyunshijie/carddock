import os, re, json, time, hashlib, sqlite3, threading, uuid, stat, subprocess, errno, collections, struct
from pathlib import Path

from rules import RAW, VIDEO, MEDIA, SIDECARS, category, still, selected, layout, folder, protected, sony_thumbnail, device_overview
BRANDS = ['Sony', 'Canon', 'Nikon', 'Panasonic', 'ARRI', 'DJI', 'GoPro', 'Insta360', 'Apple', '手动 / 其他']
HASHES = ('quick','md5','sha256','xxh64','blake3')

def snapshot(p):
    if any(x.is_symlink() for x in [p]+list(p.parents)): raise ValueError('不允许符号链接路径')
    s=p.stat()
    if not stat.S_ISREG(s.st_mode): raise ValueError('不是普通文件：'+str(p))
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

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
            entry = {'path': str(d), 'name': labels.get(str(d), d.name), 'writable': os.access(d, os.W_OK | os.X_OK), 'readable': os.access(d, os.R_OK | os.X_OK)}
            if not value:
                try:
                    v = os.statvfs(d)
                    entry.update(total=v.f_blocks*v.f_frsize, free=v.f_bavail*v.f_frsize)
                except OSError:
                    pass
            entries.append(entry)
        except (OSError, ValueError):
            continue
    entries.sort(key=lambda e: e['name'].casefold())
    p = safe_path(value, roots) if value else None
    parent = str(p.parent) if p and any(inside(p.parent, root) for root in roots) else ''
    return {'path': str(p) if p else '', 'parent': parent,
            'writable': bool(p and os.access(p, os.W_OK | os.X_OK)),
            'directories': [e['path'] for e in entries], 'entries': entries}

def mount_location(path, lines):
    matches = []
    for line in lines:
        fields = line.split(' - ', 1)[0].split()
        if len(fields) < 6: continue
        decode = lambda v: re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1],8)), v)
        mount = Path(decode(fields[4]))
        if inside(path, mount):
            matches.append((len(mount.parts), fields[2], Path(decode(fields[3])) / path.relative_to(mount)))
    if not matches: return None
    _, device, location = max(matches, key=lambda v: v[0])
    return device, location

def physical_overlap(a, b):
    # Bind mounts may expose the same directory under unrelated path names.
    if any(a.samefile(p) for p in [b] + list(b.parents)) or any(b.samefile(p) for p in [a] + list(a.parents)): return True
    try:
        lines = Path('/proc/self/mountinfo').read_text().splitlines()
    except OSError:
        return False
    first, second = mount_location(a, lines), mount_location(b, lines)
    return bool(first and second and first[0] == second[0] and (inside(first[1],second[1]) or inside(second[1],first[1])))

def files(root, media=False):
    def fail(error):raise error
    for base, dirs, names in os.walk(root, followlinks=False,onerror=fail):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink() and d not in ('$RECYCLE.BIN', 'System Volume Information', 'lost+found'))
        for name in sorted(names):
            p = Path(base)/name
            if name.startswith('.') or p.is_symlink() or sony_thumbnail(p): continue
            if stat.S_ISREG(p.stat().st_mode) and (not media or category(p)): yield p

def detect(root):
    paths = []
    for base, dirs, names in os.walk(root):
        if len(Path(base).relative_to(root).parts) >= 3: dirs[:] = []
        dirs[:] = [d for d in dirs if not (Path(base)/d).is_symlink() and not d.startswith('.')]
        paths.extend(str((Path(base)/n).relative_to(root)).upper() for n in dirs + names[:50])
        if len(paths) > 500: break
    joined = '\n'.join(paths)
    patterns=[('Sony',r'PRIVATE/M4ROOT|AVF_INFO|\d{3}MSDCF|\.ARW$'),('Canon',r'CANON|CANONMSC|\.CR[23W]$'),('Nikon',r'NIKON|NCFL|\d{3}NCD|\.NE[FWR]$|\.NRW$'),('Panasonic',r'PANA|\d{3}.*_PANA|\.RW2$'),('ARRI',r'ARRI|\.ARI$|\.ARX$'),('DJI',r'DJI|HYPERLAPSE|PANORAMA'),('GoPro',r'\d{3}GOPRO|GOPR\d{4}\.|G[HXPL]\d{6}\.'),('Insta360',r'\.INS[PV]$')]
    brands=[brand for brand,pattern in patterns if re.search(pattern,joined,re.M)]
    samples={}
    for p in files(root,True):
        if p.suffix.lower() not in samples:samples[p.suffix.lower()]=str(p)
        if len(samples)>=8:break
    metadata=[]
    from metadata import camera_tags
    for value in samples.values():
        try:
            item=camera_tags(Path(value))
            if item:metadata.append(item)
        except (OSError,ValueError,struct.error):pass
    # Optional ExifTool augments video/HEIC/CR3 recognition in the build-from-source image.
    if samples:
        try:metadata.extend(json.loads(subprocess.check_output(['exiftool','-json','-Make','-Model','-CameraModelName',*samples.values()],timeout=15,stderr=subprocess.DEVNULL)))
        except (OSError,subprocess.SubprocessError,ValueError):pass
    models=[];overviews=[];confirmed=False
    for item in metadata:
        model=str(item.get('Model',item.get('CameraModelName','')));text=str(item.get('Make',''))+' '+model
        brand=next((b for b in BRANDS[:-1] if b.lower() in text.lower()),None)
        if not brand:continue
        confirmed=True
        if brand not in brands:brands.append(brand)
        if model and model not in models:models.append(model)
        overview=device_overview({'brand':brand})
        if brand=='DJI' and re.search(r'FC[0-9]|MAVIC|MINI [0-9]|AIR [0-9]|PHANTOM',model,re.I):overview='大疆航拍相机'
        elif brand=='DJI' and 'pocket' in model.lower():overview='大疆Pocket相机'
        elif brand=='DJI' and 'action' in model.lower():overview='大疆Action相机'
        if overview and overview not in overviews:overviews.append(overview)
    for brand in brands:
        overview=device_overview({'brand':brand})
        if brand=='DJI' and any(x.startswith('大疆') for x in overviews):continue
        if overview and overview not in overviews:overviews.append(overview)
    return {'brand':brands[0] if brands else '', 'brands':brands,'model':' + '.join(models),'overview':'+'.join(overviews),'evidence':('媒体元数据与目录/格式抽样' if confirmed else '目录/格式推测' if brands else '未识别，可手动指定'),'inferred':not confirmed}


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
        self.config = {'setup_complete': False, 'auto': False, 'media_only': False, 'keep_parents': True, 'verify': 'sha256', 'primary': '', 'backups': [], 'brand': '', 'model': '', 'manual_sources': [], 'classify': True, 'exclude_proxies': False, 'directory_template': '{source}', 'filename_template': '', 'project': '', 'camera': '', 'card': '', 'extensions': '', 'date_from': '', 'date_to': '', 'conflict': 'keepBoth', 'backup_from_primary': True}
        if (self.state/'config.json').exists():
            saved = json.loads((self.state/'config.json').read_text())
            self.config.update(saved)
            if 'setup_complete' not in saved: self.config['setup_complete'] = True
        self.db = sqlite3.connect(str(self.state/'history.sqlite'), check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT)')
        for ident, data in self.db.execute('SELECT id,data FROM jobs ORDER BY rowid DESC LIMIT 100'):
            j = json.loads(data)
            if j['status'] in ('queued','running','pausing','paused','stopping'): j.update(status='interrupted', error='服务重启中断；重新提交将复核已完成文件', safe_to_remove=False)
            self.jobs[ident] = j
    def initialize_primary(self, name):
        """Choose a default only for a fresh installation, never for an upgrade."""
        if not name or (self.state/'config.json').exists(): return
        if name in ('.','..') or Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('默认归档文件夹必须是单个名称')
        if not self.targets: raise ValueError('没有可用的默认共享目录')
        target = safe_path(str(self.targets[0]/name), self.targets, exists=False)
        target.mkdir(exist_ok=True)
        self.configure({'primary':str(target), 'manual_sources':[str(self.auto_sources[0])] if self.auto_sources else []})
    def save_job(self,j):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)',(j['id'],json.dumps(j,ensure_ascii=False))); self.db.commit()
    def configure(self, data):
        with self.lock:
            c = dict(self.config); c.update({k:v for k,v in data.items() if k in c})
            if c['verify'] not in HASHES: raise ValueError('无效校验方式')
            for k in ('setup_complete','auto','media_only','keep_parents','classify','exclude_proxies','backup_from_primary'):
                if not isinstance(c[k],bool): raise ValueError('无效开关')
            if not isinstance(c['backups'],list) or not isinstance(c['manual_sources'],list): raise ValueError('无效目录列表')
            if len(c['backups'])>8: raise ValueError('最多支持八个备份目录')
            self.validate_options(c)
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
            if j['status']=='queued' and action=='stop':
                j.update(status='cancelled',phase='已移出待执行队列',safe_to_remove=False,io_released=True);self.save_job(j);return j
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
        samples=ctl.setdefault('samples',collections.deque())
        samples.append((now,j.get('transferred_bytes',0)))
        while len(samples)>2 and now-samples[0][0]>8:samples.popleft()
        rate=(samples[-1][1]-samples[0][1])/max(.001,now-samples[0][0])
        j['realtime_bps']=rate if j.get('stage')=='copy' else 0
        remaining=max(0,j.get('bytes_total',0)-j.get('transferred_bytes',0))
        j['eta_seconds']=remaining/rate if rate>0 and j.get('stage')=='copy' else None
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
            if not selected(p,self.config):continue
            s=p.stat().st_size; total+=s; n+=1; cat=category(p)
            if cat: counts[cat]+=1
            if len(rows)<200: rows.append({'path':str(p.relative_to(root)),'size':s,'category':cat or '其他'})
        return {'path':str(root),'count':n,'bytes':total,'counts':counts,'files':rows,'camera':detect(root)}
    def submit(self, source, options=None, enqueue=False):
        with self.lock:
            if self.active and not enqueue: raise ValueError('已有任务执行中，请加入队列')
            c=json.loads(json.dumps(self.config)); c.update(options or {})
            root=safe_path(source,self.sources); primary=safe_path(c['primary'],self.targets)
            if not isinstance(c['backups'],list) or len(c['backups'])>8: raise ValueError('最多支持八个备份目录')
            self.validate_options(c)
            backups=[safe_path(p,self.targets) for p in c['backups']]
            paths=[root,primary]+backups
            for i,a in enumerate(paths):
                for b in paths[i+1:]:
                    if inside(a,b) or inside(b,a) or physical_overlap(a,b): raise ValueError('源目录、主文件夹和备份目录不能相同或互相包含')
            if c['verify'] not in HASHES: raise ValueError('无效校验方式')
            if not c.get('_resolved_folder'):c['_resolved_folder']=str(folder(c,root,device_overview(detect(root))))
            ident=uuid.uuid4().hex[:12]
            j={'id':ident,'source':str(root),'status':'queued','phase':'等待','created':time.time(),'done':0,'total':0,'bytes_done':0,'bytes_total':0,'destinations':{},'manifest':[],'copied':0,'skipped':0,'safe_to_remove':False,'primary_verified':False,'error':'','options':c,'source_identity': [root.stat().st_dev, root.stat().st_ino], 'target_identities': {str(t):[t.stat().st_dev,t.stat().st_ino] for t in [primary]+backups}}
            self.blocked_sources.discard(str(root))
            self.controls[ident]={'stop':threading.Event(),'pause':threading.Event(),'started':time.monotonic(),'paused_seconds':0}
            j.update(transferred_bytes=0,speed_bps=0,io_released=False)
            self.jobs[ident]=j; self.save_job(j)
            if not self.active: self.start_job(j)
            return j
    def hash(self,p,algorithm):
        if algorithm=='xxh64':
            import xxhash
            h=xxhash.xxh64()
        elif algorithm=='blake3':
            from blake3 import blake3
            h=blake3()
        else: h=hashlib.new(algorithm)
        with open(p,'rb') as f:
            while True:
                self.checkpoint(); chunk=f.read(4*1024*1024)
                if not chunk: break
                h.update(chunk)
        return h.hexdigest()
    def equal(self,a,b,mode):
        if not b.is_file() or b.is_symlink() or a.stat().st_size != b.stat().st_size: return False
        return mode=='quick' or self.hash(a,mode)==self.hash(b,mode)
    def validate_options(self,c):
        if c.get('verify') not in HASHES: raise ValueError('无效校验方式')
        if c.get('verify') in ('xxh64','blake3'):
            try: __import__('xxhash' if c['verify']=='xxh64' else 'blake3')
            except ImportError: raise ValueError('缺少校验依赖，请安装完整新版安装包')
        if c.get('conflict','keepBoth') not in ('keepBoth','skip','overwrite'): raise ValueError('无效冲突方式')
        for key in ('directory_template','filename_template','project','camera','card','extensions','date_from','date_to'):
            if not isinstance(c.get(key,''),str) or len(c.get(key,''))>512: raise ValueError('无效命名或筛选字段')
        import datetime
        for key in ('date_from','date_to'):
            if c.get(key): datetime.date.fromisoformat(c[key])
        if c.get('date_from') and c.get('date_to') and c['date_from']>c['date_to']:raise ValueError('开始日期不能晚于结束日期')
        folder(c,Path('/source'),device_overview({'brand':c.get('brand','')}))
        for key in ('auto','media_only','keep_parents','classify','exclude_proxies','backup_from_primary'):
            if not isinstance(c.get(key),bool):raise ValueError('无效开关：'+key)

    def start_job(self,j):
        self.active=True
        threading.Thread(target=self.run,args=(j,Path(j['source']),Path(j['options']['primary']),[Path(p) for p in j['options']['backups']],j['options']),daemon=True).start()

    def retry(self,ident):
        with self.lock:
            j=self.jobs.get(ident)
            if not j or j['status'] in ('running','queued','paused','pausing','stopping'):raise ValueError('此任务不能重试')
            return self.submit(j['source'],j['options'],enqueue=True)

    def remove(self,ident):
        with self.lock:
            j=self.jobs.get(ident)
            if not j:raise ValueError('任务不存在')
            if j['status'] in ('running','paused','pausing','stopping'):raise ValueError('请先停止正在运行的任务')
            self.db.execute('DELETE FROM jobs WHERE id=?',(ident,));self.db.commit()
            self.jobs.pop(ident,None);self.controls.pop(ident,None)
            return {'ok':True}

    def presets(self,name=None,options=None,delete=False):
        path=self.state/'presets.json'
        with self.lock:
            data=json.loads(path.read_text()) if path.exists() else {}
            if name is not None:
                if not isinstance(name,str) or not name.strip() or len(name)>80:raise ValueError('请输入80字以内预设名')
                if delete:data.pop(name,None)
                else:
                    c=json.loads(json.dumps(self.config));c.update({k:v for k,v in (options or {}).items() if k in c});self.validate_options(c)
                    # Automatic import is never armed merely by applying a preset.
                    c['auto']=False;data[name]=c
                tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));os.replace(tmp,path)
            return data

    def update_progress(self,j,stage,done,total,byte_done=0,byte_total=0,current=''):
        if j.get('stage')!=stage:
            j.setdefault('events',[]).append({'at':time.time(),'stage':stage,'phase':j['phase']})
        j.update(stage=stage,stage_done=done,stage_total=total,current_file=current,
                 stage_fraction=min(1,byte_done/byte_total) if byte_total else (done/total if total else 0))
        self.metrics(j)

    def destination_path(self,path):
        safe_path(str(path.parent),self.targets,False)
        protected_roots=[self.state,Path(os.getenv('APP_RELEASE_ROOT','/opt/carddock'))]
        for base in protected_roots:
            if base.exists() and any(parent.exists() and parent.samefile(base) for parent in [path]+list(path.parents)):
                raise ValueError('归档路径不能写入程序或状态目录')

    def copy(self,src,dst,mode,j):
        """Write only; the stage verifies every pending file after all writes finish."""
        self.destination_path(dst);dst.parent.mkdir(parents=True,exist_ok=True)
        before=snapshot(src);overwrite=None
        reserved=self.local.reserved
        conflict=j['options'].get('conflict','keepBoth')
        if dst.exists() or dst.is_symlink() or str(dst) in reserved:
            if dst.is_symlink():raise ValueError('目标不允许符号链接')
            if str(dst) not in reserved and self.equal(src,dst,mode if mode!='quick' else 'sha256'):
                if snapshot(src)!=before:raise ValueError('源文件在复核期间发生变化')
                j['skipped']+=1;reserved.add(str(dst));return dst
            if conflict=='skip':
                j['conflict_skipped']=j.get('conflict_skipped',0)+1;return None
            if conflict=='overwrite':
                if str(dst) in reserved:raise ValueError('多个源文件映射到同一目标，禁止覆盖')
                overwrite=snapshot(dst)
            else:
                if protected(src):raise ValueError('全景、延时、代理或RED容器存在同名不同内容文件，请使用新归档目录：'+str(dst))
                suffix=self.hash(src,'sha256')[:16];dst=dst.with_name(dst.stem+'__'+suffix+dst.suffix)
                if str(dst) in reserved:raise ValueError('多个源文件映射到同一路径，请保留父目录')
                if dst.exists() or dst.is_symlink():
                    if self.equal(src,dst,'sha256'):
                        if snapshot(src)!=before:raise ValueError('源文件发生变化')
                        j['skipped']+=1;reserved.add(str(dst));return dst
                    raise ValueError('冲突目标已存在且内容不同：'+str(dst))
        reserved.add(str(dst))
        temp=dst.with_name('.'+dst.name+'.'+j['id']+'.partial')
        # Register before opening so cancellation or any write failure cleans this task's file.
        self.local.pending.append({'source':src,'output':dst,'temp':temp,'snapshot':before,'overwrite':overwrite})
        with open(src,'rb') as r,open(temp,'xb') as w:
            while True:
                self.checkpoint();chunk=r.read(4*1024*1024)
                if not chunk:break
                w.write(chunk);j['transferred_bytes']+=len(chunk);self.metrics(j)
                j['stage_fraction']=min(1,(self.local.written+min(w.tell(),before[2]))/max(1,self.local.stage_bytes))
            w.flush();os.fsync(w.fileno())
        if snapshot(src)!=before or temp.stat().st_size!=before[2]:raise ValueError('源文件在复制期间发生变化')
        os.utime(temp,ns=(src.stat().st_atime_ns,before[3]))
        return dst

    def publish(self,item,j):
        src,dst=item['temp'],item['output']
        try:os.link(src,dst)
        except OSError as e:
            if e.errno not in (errno.EPERM,errno.EOPNOTSUPP,errno.ENOSYS,errno.EXDEV):raise
            # Filesystems without hardlinks still refuse overwrites atomically at creation.
            fd=os.open(str(dst),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o644)
            with os.fdopen(fd,'wb') as out,open(src,'rb') as reader:
                while True:
                    self.checkpoint();chunk=reader.read(4*1024*1024)
                    if not chunk:break
                    out.write(chunk);j['transferred_bytes']+=len(chunk)
                out.flush();os.fsync(out.fileno())
            os.utime(dst,ns=(src.stat().st_atime_ns,src.stat().st_mtime_ns))
        src.unlink()

    def run(self,j,root,primary,backups,c):
        self.local.job=j;self.local.pending=[]
        published={};ready=[]
        try:
            self.checkpoint();j.update(status='running',phase='扫描媒体',safe_to_remove=False,primary_verified=False);self.save_job(j)
            if list((root.stat().st_dev,root.stat().st_ino))!=j.get('source_identity'):raise ValueError('源目录或存储卷身份已变化，请重新选源')
            for dest in [primary]+backups:
                safe_path(str(dest),self.targets)
                if [dest.stat().st_dev,dest.stat().st_ino]!=j['target_identities'][str(dest)]:raise ValueError('目标目录或存储卷身份已变化')
            identities={p:(p.stat().st_dev,p.stat().st_ino) for p in [primary]+backups}
            def target_check(dest):
                safe_path(str(dest),self.targets)
                if (dest.stat().st_dev,dest.stat().st_ino)!=identities[dest]:raise ValueError('目标挂载发生变化：'+str(dest))
            manifest=[];companions={};sequences={}
            for p in files(root):
                self.checkpoint()
                if not selected(p,c):continue
                snap=snapshot(p);manifest.append((p,p.relative_to(root),snap))
                if still(p):
                    key=str(p.with_suffix('')).lower()
                    if key not in companions or still(p)=='RAW':companions[key]=still(p)
            if not manifest:raise ValueError('没有符合筛选的可拷贝文件')
            info=detect(root);j['device']=info
            values=dict(c)
            # Keep the namespace frozen with the task for a predictable retry.
            namespace=Path(c.get('_resolved_folder') or str(folder(c,root,device_overview(info))))
            c['_resolved_folder']=str(namespace)
            plans=[]
            for p,rel,snap in manifest:
                key=str(p.with_suffix('')).lower()
                if key not in sequences:sequences[key]=len(sequences)+1
                plans.append({'source':p,'relative':namespace/layout(p,root,c,companions,sequences[key]),'snapshot':snap,'original':str(rel),'expected':None})
            count=len(plans);size=sum(x['snapshot'][2] for x in plans)
            j.update(total=count*(1+len(backups)),bytes_total=size*(1+len(backups)),copy_done=0,done=0,bytes_done=0)
            j['destinations']={str(p):'pending' for p in [primary]+backups}
            def stage(plans,dest,label):
                self.local.pending=[];self.local.reserved=set();self.local.written=0;self.local.stage_bytes=size
                tasks=[];skipped=0;skip_bytes=0;output=[]
                j['destinations'][str(dest)]='running';j['phase']=label+' · 拷贝阶段'
                self.update_progress(j,'copy',0,len(plans),current='');self.save_job(j)
                for plan in plans:
                    self.checkpoint();target_check(dest)
                    if snapshot(plan['source'])!=plan['snapshot']:raise ValueError('源文件或主拷贝发生变化：'+str(plan['source']))
                    before_pending=len(self.local.pending)
                    self.local.current_expected=plan['expected']
                    out=self.copy(plan['source'],dest/plan['relative'],c['verify'],j)
                    if snapshot(plan['source'])!=plan['snapshot']:raise ValueError('源文件在复制期间发生变化')
                    new=len(self.local.pending)>before_pending
                    item=self.local.pending[-1] if new else None
                    tasks.append((plan,out,item));self.local.written+=plan['snapshot'][2];j['copy_done']+=1
                    if not new:skipped+=1;skip_bytes+=plan['snapshot'][2]
                    self.update_progress(j,'copy',len(tasks),len(plans),self.local.written,size,plan['original']);self.save_job(j)
                # No fresh-file content hashing before this boundary.
                j['phase']=label+' · '+('大小复核阶段' if c['verify']=='quick' else '校验阶段')
                self.update_progress(j,'size' if c['verify']=='quick' else 'verify',0,len(tasks),0,size);self.save_job(j)
                verified_bytes=0
                for i,(plan,out,item) in enumerate(tasks):
                    self.checkpoint();target_check(dest);src=plan['source'];snap=plan['snapshot'];checksum=None;sha=None
                    if snapshot(src)!=snap:raise ValueError('校验前源文件或主拷贝已变化')
                    action='skipped-conflict' if out is None else ('copied' if item else 'skipped-identical')
                    if out is not None:
                        actual=item['temp'] if item else out
                        if c['verify']!='quick':
                            checksum=self.hash(src,c['verify']);sha=checksum if c['verify']=='sha256' else self.hash(src,'sha256')
                            if plan['expected'] and sha!=plan['expected']:raise ValueError('主拷贝与原始已验证指纹不一致')
                            if self.hash(actual,c['verify'])!=checksum:raise ValueError('内容校验失败：'+str(out))
                        elif actual.stat().st_size!=snap[2]:raise ValueError('大小复核失败')
                        if snapshot(src)!=snap:raise ValueError('校验期间源文件或主拷贝已变化')
                        if item:
                            self.checkpoint();self.destination_path(out)
                            if item['overwrite'] is not None:
                                if snapshot(out)!=item['overwrite']:raise ValueError('覆盖前目标发生变化')
                                os.replace(item['temp'],out)
                            else:self.publish(item,j)
                            fd=os.open(str(out.parent),os.O_RDONLY)
                            try:os.fsync(fd)
                            finally:os.close(fd)
                            if c['verify']!='quick' and self.hash(out,c['verify'])!=checksum:raise ValueError('最终目标内容校验失败')
                            j['copied']+=1
                        if snapshot(src)!=snap or out.stat().st_size!=snap[2]:raise ValueError('发布后文件发生变化')
                        published[out]=(snapshot(out),sha)
                        output.append({'source':out,'relative':out.relative_to(dest),'snapshot':snapshot(out),'original':plan['original'],'expected':sha})
                    record={'source':plan['original'],'read_source':str(src),'destination':str(out) if out else str(dest/plan['relative']),'bytes':snap[2],'sha256':sha,'checksum':checksum,'algorithm':c['verify'],'mtime_ns':snap[3],'action':action}
                    j['manifest'].append(record);j['done']+=1;j['bytes_done']+=snap[2];verified_bytes+=snap[2]
                    self.update_progress(j,'size' if c['verify']=='quick' else 'verify',i+1,len(tasks),verified_bytes,size,plan['original']);self.save_job(j)
                return output
            ready=stage(plans,primary,'存储卡 → 主拷贝')
            current=[(str(p.relative_to(root)),snapshot(p)) for p in files(root) if selected(p,c)]
            if current!=[(str(rel),snap) for _,rel,snap in manifest]:raise ValueError('存储卡文件清单发生变化，请重新导入')
            for p,(_snap,sha) in list(published.items()):
                if snapshot(p)[:3]!=_snap[:3] or sha and self.hash(p,'sha256')!=sha:raise ValueError('主拷贝最终复核失败')
            if len(ready)!=len(plans) and backups:raise ValueError('主拷贝存在跳过冲突，停止备份传播')
            ready=[dict(item,snapshot=snapshot(item['source'])) for item in ready]
            target_check(primary);j['destinations'][str(primary)]='verified' if len(ready)==len(plans) else 'skipped-conflict'
            j.update(primary_verified=len(ready)==len(plans),phase='主文件夹校验完成，准备备份');self.save_job(j)
            for i,backup in enumerate(backups):
                target_check(primary);target_check(backup)
                # Relay uses only this job's verified manifest. Direct mode reads the frozen source plan.
                result=stage(ready if c.get('backup_from_primary',True) else plans,backup,'主拷贝 → 备份 '+str(i+1) if c.get('backup_from_primary',True) else '存储卡 → 备份 '+str(i+1))
                j['destinations'][str(backup)]='verified' if len(result)==len(plans) else 'skipped-conflict'
            for dest in identities:target_check(dest)
            for out,(baseline,sha) in published.items():
                now=snapshot(out)
                if now[:3]!=baseline[:3]:raise ValueError('最终目标对象或大小变化')
                if sha and self.hash(out,'sha256')!=sha:raise ValueError('最终目标内容变化')
            conflicts=j.get('conflict_skipped',0)>0
            subset=c.get('media_only') or c.get('exclude_proxies') or c.get('extensions') or c.get('date_from') or c.get('date_to')
            j.update(status='completed-with-skips' if conflicts else 'completed',stage='done',stage_fraction=1,selected_scope_verified=not conflicts and c['verify']!='quick',safe_to_remove=not conflicts and not subset and c['verify']!='quick',phase='完成（存在跳过冲突）' if conflicts else '主文件夹与备份文件夹均已校验完成' if backups else '主文件夹拷贝与校验完成（未设置备份）')
        except TaskCancelled:
            j.update(status='stopping',phase='正在终止，等待文件句柄关闭',error='',safe_to_remove=False)
            for dest,status in j['destinations'].items():
                if status=='running':j['destinations'][dest]='cancelled'
        except Exception as e:
            if j.get('primary_verified'):
                try:
                    for path,(baseline,sha) in published.items():
                        if inside(path,primary) and (snapshot(path)[:3]!=baseline[:3] or sha and self.hash(path,'sha256')!=sha):
                            j['primary_verified']=False;j['destinations'][str(primary)]='failed';break
                except Exception:
                    j['primary_verified']=False;j['destinations'][str(primary)]='failed'
            j.update(status='failed',error=str(e),phase='任务失败',safe_to_remove=False)
            for dest,status in j['destinations'].items():
                if status=='running':j['destinations'][dest]='failed'
        finally:
            for item in getattr(self.local,'pending',[]):
                try:item['temp'].unlink(missing_ok=True)
                except OSError:pass
            try:
                with self.io_lock:
                    if self.controls[j['id']]['stop'].is_set() and j['status']!='failed':j.update(status='cancelled',phase='已终止 · 拷贝未全部完成',safe_to_remove=False)
                    j['io_released']=True;self.metrics(j);j['finished']=time.time();self.save_job(j)
                    try:
                        from reports import save_reports
                        save_reports(j,self.state/'reports')
                    except Exception as e:j['report_error']=str(e);self.save_job(j)
            finally:
                self.local.job=None
                with self.lock:
                    self.active=False
                    queued=sorted((x for x in self.jobs.values() if x['status']=='queued'),key=lambda x:x['created'])
                    if queued and j['status']!='cancelled':self.start_job(queued[0])
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
