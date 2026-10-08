#!/usr/bin/env python3
"""Build a reproducible, explicit-allowlist installer archive without local secrets."""
import hashlib,re,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=['CardDock-help.html','VERSION','README.md','LICENSE','CHANGELOG.md','PORTABLE-INSTALL.md','Dockerfile','.dockerignore','.env.example','compose.yaml','compose.backup.yaml','deploy.py','access-key.py','update.sh','rollback.sh','setup.html','setup.js']
FOLDERS=['app','admin','docs','packaging','tests']
def build():
    version=(ROOT/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9.]+)?',version):raise ValueError('Invalid version')
    paths=[ROOT/p for p in FILES]
    for folder in FOLDERS:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css','.svg','.md','.sh','.service'))
    paths=sorted(set(p for p in paths if '__pycache__' not in p.parts))
    out=ROOT/'dist';out.mkdir(exist_ok=True);archive=out/f'carddock-{version}-install.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            if p.is_symlink():raise ValueError('No symlinks in release')
            info=zipfile.ZipInfo('carddock/'+str(p.relative_to(ROOT)),(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
            z.writestr(info,p.read_bytes())
    (out/'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    print(archive)
if __name__=='__main__':build()
