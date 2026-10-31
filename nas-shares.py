#!/usr/bin/env python3
"""Discover this NAS's configured shares and grant them to CardDock explicitly."""
import argparse
import configparser
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

CONFIGS = ('/etc/samba/smbshare.conf', '/etc/config/smb.conf', '/usr/syno/etc/smb.conf',
           '/etc/samba/smb.share.conf', '/etc/samba/smb.conf', '/etc/smb4.conf', '/usr/local/etc/smb4.conf')
BLOCKED = tuple(Path(p) for p in ('/etc', '/proc', '/sys', '/dev', '/root', '/run', '/usr', '/boot', '/var/lib/docker'))


def discover(configs):
    found = {}
    for filename in configs:
        p = Path(filename)
        if not p.is_file():
            continue
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read(p, encoding='utf-8')
        for name in parser.sections():
            if name.lower() in ('global', 'homes', 'printers', 'print$', 'ipc$'):
                continue
            value = parser[name].get('path', '').strip().strip('"')
            if not value.startswith('/') or '%' in value or parser[name].get('printable', 'no').lower() in ('yes', 'true'):
                continue
            source = Path(value).resolve()
            if source == Path('/') or any(source == b or b in source.parents for b in BLOCKED):
                raise ValueError('共享定义指向系统目录，拒绝开放：' + name)
            if not source.is_dir():
                raise ValueError('共享目录不可访问：' + name)
            if name in found and found[name] != source:
                raise ValueError('共享名称存在多个不同路径，请用 --config 指定有效配置：' + name)
            found[name] = source
    if not found:
        raise ValueError('没有识别到共享文件夹；请用 --config 指定此 NAS 的有效 Samba 共享配置。不会扫描或开放整台系统盘。')
    return found


def base_configuration():
    return {'services': {'carddock': {
        'image': 'ghcr.io/xingyunshijie/carddock:latest', 'container_name': 'carddock',
        'restart': 'unless-stopped', 'ports': ['18080:8080'],
        'environment': {'TZ': 'Asia/Shanghai', 'AUTHENTICATION_ENABLED': 'true',
                        'AUTHENTICATION_PASSWORD': '改成你自己的密码'},
        'volumes': ['./data:/state', './archive:/storage', './inbox:/sources:ro',
                    '/proc/1/mountinfo:/host/mountinfo:ro', '/sys:/sys:ro'],
        'read_only': True, 'tmpfs': ['/tmp:size=128m,mode=1777'],
        'security_opt': ['no-new-privileges:true']}}}


def configuration(base, shares, directory=None):
    result = json.loads(json.dumps(base))
    service = result['services']['carddock']
    if service.get('image', '').split(':')[0] == 'ghcr.io/xingyunshijie/carddock':
        service['image'] = 'ghcr.io/xingyunshijie/carddock:latest'
    env = service.setdefault('environment', {})
    if not isinstance(env, dict):
        raise ValueError('基础配置需要使用键值形式的 environment')
    labels = json.loads(env.get('TARGET_LABELS', '{}'))
    labels['/storage'] = '默认存储位置'
    volumes = service.setdefault('volumes', [])
    def target(v):
        return v.get('target', '') if isinstance(v, dict) else v.split(':')[1]
    service['volumes'] = [v for v in volumes if not target(v).startswith('/shares/')]
    reader_mounts = [v for v in service['volumes'] if isinstance(v, dict) and v.get('target','').startswith('/readers/') and v.get('read_only')]
    for name, source in sorted(shares.items(), key=lambda v: v[0].casefold()):
        # Some NAS systems advertise inserted cards as temporary Samba shares.
        # Keep those under source-only mounts instead of granting writable targets.
        reader = next((v for v in reader_mounts if source == Path(v['source']) or Path(v['source']) in source.parents), None)
        if reader:
            suffix = source.relative_to(Path(reader['source'])).as_posix()
            labels[reader['target'] + ('/' + suffix if suffix != '.' else '')] = name
            continue
        key = name if re.fullmatch(r'[^/\\:\x00-\x1f]+', name) and not name.startswith(('.', '@')) else 'share-' + hashlib.sha256(name.encode()).hexdigest()[:12]
        destination = '/shares/' + key
        labels[destination] = name
        service['volumes'].append({'type': 'bind', 'source': str(source), 'target': destination,
                                  'bind': {'create_host_path': False}})
    env['NAS_SHARED_ROOT'] = '/shares'
    env['TARGET_LABELS'] = json.dumps(labels, ensure_ascii=False)
    paths = {}
    directory = Path(directory or Path.cwd())
    for volume in service['volumes']:
        if isinstance(volume, dict):
            if volume.get('type') != 'bind': continue
            source, target = volume['source'], volume['target']
        else:
            source, target = volume.split(':')[:2]
            if not source.startswith(('/', '.')): continue
        paths[target] = str((directory / source).resolve())
    env['HOST_PATH_MAP'] = json.dumps(paths, ensure_ascii=False)
    return result


def discover_readers(explicit=(), mountinfo='/proc/self/mountinfo', sysroot='/sys'):
    """Grant USB mount parents, never /mnt, a storage pool or the host root."""
    known = [Path(p) for p in ('/mnt/@usb', '/share/external', '/media', '/run/media', '/mnt/usb', '/mnt/USB')]
    known += list(Path('/').glob('volumeUSB*'))
    roots = [p.resolve() for p in known if p.is_dir() and not p.is_symlink()]
    for value in explicit:
        p = Path(value)
        if not p.is_absolute() or p.is_symlink() or not p.is_dir():
            raise ValueError('读卡器父目录不存在或无效：' + str(value))
        p = p.resolve()
        if len(p.parts) < 3 or any(p == b or b in p.parents for b in BLOCKED):
            raise ValueError('不能将系统或存储池根目录作为读卡器父目录')
        roots.append(p)
    # Nonstandard NAS: map only mounted physical removable media itself.
    def disks(dev, seen=None):
        seen = set() if seen is None else seen
        dev = dev.resolve()
        if dev in seen: return set()
        seen.add(dev)
        if (dev/'partition').exists(): dev = dev.parent
        slaves = list((dev/'slaves').iterdir()) if (dev/'slaves').is_dir() else []
        return set().union(*(disks(p, seen) for p in slaves)) if slaves else {dev}
    try: lines = Path(mountinfo).read_text().splitlines()
    except OSError: lines = []
    system = set()
    for line in lines:
        fields = line.split(' - ', 1)[0].split()
        if fields[4] in ('/', '/boot', '/boot/efi', '/usr', '/var', '/etc'):
            system |= disks(Path(sysroot)/'dev/block'/fields[2])
    for line in lines:
        left, right = line.split(' - ', 1)
        fields = left.split()
        if fields[3] != '/' or right.split()[0] in ('tmpfs','overlay','proc','sysfs','nfs','cifs','iso9660','udf'): continue
        dev = (Path(sysroot)/'dev/block'/fields[2]).resolve()
        if not dev.exists() or any(p.startswith(('loop','ram','dm-','md')) for p in dev.parts): continue
        removable = any((p/'removable').is_file() and (p/'removable').read_text().strip() == '1' for p in (dev,dev.parent))
        if not ('usb' in str(dev).lower() or removable or any(p.startswith('mmc') for p in dev.parts)): continue
        if disks(dev) & system: continue
        path = Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1],8)), fields[4])).resolve()
        if path.is_dir() and len(path.parts) >= 3 and not any(path == r or r in path.parents for r in roots):
            roots.append(path)
    return sorted(set(roots), key=str)


def reader_configuration(base, roots):
    result = json.loads(json.dumps(base))
    service = result['services']['carddock']
    env = service.setdefault('environment', {})
    volumes = service.setdefault('volumes', [])
    labels = json.loads(env.get('TARGET_LABELS', '{}'))
    sources = [p for p in env.get('SOURCE_ROOTS', '/sources').split(':') if p]
    for root in roots:
        destination = '/readers/' + hashlib.sha256(str(root).encode()).hexdigest()[:12]
        if not any((v.get('target') if isinstance(v, dict) else v.split(':')[1]) == destination for v in volumes):
            volumes.append({'type': 'bind', 'source': str(root), 'target': destination,
                            'read_only': True, 'bind': {'create_host_path': False, 'propagation': 'rslave'}})
        if destination not in sources: sources.append(destination)
        labels[destination] = '读卡器与外接存储 · ' + root.name
    env['SOURCE_ROOTS'] = ':'.join(sources)
    env['TARGET_LABELS'] = json.dumps(labels, ensure_ascii=False)
    return result


def installation_identity(base, uid, gid):
    service = base['services']['carddock']
    if uid > 0 and gid > 0 and service.get('user') in (None, '', '0', '0:0', 'root'):
        env = service.setdefault('environment', {})
        env.setdefault('PUID', str(uid))
        env.setdefault('PGID', str(gid))
    return base


def write_private(path, data):
    if path.is_symlink():
        raise ValueError('拒绝写入符号链接')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.carddock-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            os.fchmod(f.fileno(), 0o600)
            # The input is already resolved; prevent a second Compose interpolation.
            def literal(value):
                if isinstance(value, str): return value.replace('$', '$$')
                if isinstance(value, list): return [literal(v) for v in value]
                if isinstance(value, dict): return {k: literal(v) for k,v in value.items()}
                return value
            json.dump(literal(data), f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', action='append', help='有效的 NAS Samba 配置，可重复')
    p.add_argument('--reader-root', action='append', default=[], help='此 NAS 的外接存储父目录，可重复；自动识别常见路径')
    p.add_argument('--base', type=Path, help='保留现有项目的端口、密码和目录映射')
    p.add_argument('--output', type=Path, default=Path('compose.shared.yaml'))
    p.add_argument('--apply', action='store_true', help='检查后部署项目；须先完成所有传输')
    p.add_argument('--project', default='carddock')
    a = p.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', a.project):
        raise ValueError('项目名称无效')
    shares = discover(a.config or [x for x in CONFIGS if Path(x).is_file()])
    base = base_configuration()
    uid = int(os.getenv('SUDO_UID', str(os.getuid())))
    gid = int(os.getenv('SUDO_GID', str(os.getgid())))
    if a.base:
        base = json.loads(subprocess.check_output(['docker', 'compose', '-p', a.project, '-f', str(a.base.resolve()), 'config', '--format', 'json'], text=True))
    elif a.apply:
        password = getpass.getpass('设置影像归仓登录密码（8–256位）：')
        if not 8 <= len(password) <= 256 or password in ('改成你自己的密码', '请修改为你自己的登录密码') or password.startswith('CHANGE_ME'):
            raise ValueError('密码长度或占位值不符合要求')
        if getpass.getpass('再次输入登录密码：') != password:
            raise ValueError('两次输入不一致')
        base['services']['carddock']['environment']['AUTHENTICATION_PASSWORD'] = password
    base = installation_identity(base, uid, gid)
    output = a.output.resolve()
    if output.exists():
        raise ValueError('输出配置已存在；请使用新的 --output 文件名，避免覆盖旧配置')
    readers = discover_readers(a.reader_root)
    write_private(output, configuration(reader_configuration(base, readers), shares, output.parent))
    print('读卡器访问位置：' + ('、'.join(str(p) for p in readers) if readers else '未发现；连接读卡器后重新运行，或用 --reader-root 指定父目录'))
    print('已识别并生成共享目录映射：' + '、'.join(shares))
    print('配置文件：' + str(output))
    if a.apply:
        cmd = ['docker', 'compose', '-p', a.project, '-f', str(output)]
        subprocess.run(cmd + ['config', '--quiet'], check=True)
        cid = subprocess.check_output(cmd + ['ps', '-q', 'carddock'], text=True).strip()
        if cid:
            guard = '''import json,sqlite3
from pathlib import Path
p=Path('/state/config.json')
c=json.loads(p.read_text()) if p.exists() else {}
assert not c.get('auto'), '请先关闭自动导入并保存设置'
db=sqlite3.connect('file:/state/history.sqlite?mode=ro',uri=True)
assert not any(json.loads(r[0])['status'] in ('queued','running','paused','pausing','stopping') for r in db.execute('select data from jobs')), '请先完成或终止所有任务'
'''
            subprocess.run(['docker', 'exec', cid, 'python', '-c', guard], check=True)
        subprocess.run(cmd + ['pull', 'carddock'], check=True)
        subprocess.run(cmd + ['up', '-d', 'carddock'], check=True)
        print('项目已提交启动；请检查容器健康状态后访问网页。')
    else:
        print('尚未部署。新安装需填写自己的至少8位登录密码；已有项目保留原凭据。')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, configparser.Error, subprocess.CalledProcessError) as e:
        raise SystemExit(str(e))
