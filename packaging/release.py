#!/usr/bin/env python3
"""Build the public installer from this repository; never package runtime state."""
import hashlib,json,pathlib,re,zipfile
root=pathlib.Path(__file__).resolve().parents[1];version=(root/'VERSION').read_text().strip()
legacy=re.fullmatch(r'1\.0\.0-nas\.(\d+)',version)
if legacy:
 folder='carddock-nas-1.0-b'+legacy[1]
else:
 match=re.fullmatch(r'([1-9]\d*)\.(\d+)\.(\d+)',version)
 if not match:raise SystemExit('Unexpected NAS version')
 display=match[1]+'.'+match[2]+('.'+match[3] if match[3]!='0' else '')
 folder='carddock-nas-'+display
dist=root/'dist';dist.mkdir(exist_ok=True)
archive=dist/(folder+'-install.zip')
selected=[]
for p in root.rglob('*'):
 rel=p.relative_to(root)
 if any(x in ('.git','.github','dist','state','data','archive','inbox','__pycache__') for x in rel.parts):continue
 if p.is_symlink():raise SystemExit('Refuse symlink: '+str(rel))
 if p.is_file() and p.name not in ('.env','.DS_Store') and p.suffix not in ('.pyc','.pem','.key','.sqlite','.sqlite3'):selected.append(p)
checks=[]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted(selected):
  rel=p.relative_to(root).as_posix();z.write(p,folder+'/'+rel);checks.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+rel)
 z.writestr(folder+'/state/',b'');z.writestr(folder+'/SHA256SUMS.txt','\n'.join(checks)+'\n')
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
for source,name in [('NAS安装说明.html','CardDock-NAS-install.html'),('NAS安装说明.md','CardDock-NAS-install.md'),('compose.project.yaml','compose.project.yaml'),('compose.version.yaml','compose.version.yaml')]:
 (dist/name).write_bytes((root/source).read_bytes())
(dist/'nas-shares.py').write_bytes((root/'nas-shares.py').read_bytes())
assets=[archive,dist/'nas-shares.py',dist/'CardDock-NAS-install.html',dist/'CardDock-NAS-install.md',dist/'compose.project.yaml',dist/'compose.version.yaml']
(dist/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in assets))
print(json.dumps({'version':version,'installer':archive.name,'bytes':archive.stat().st_size,'files':len(selected)},ensure_ascii=False))
