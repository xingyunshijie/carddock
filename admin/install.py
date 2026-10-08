#!/usr/bin/env python3
"""Install the optional, explicitly configured Linux PAM/systemd adapter."""
import argparse
import ctypes.util
import grp
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def certificate_san(host):
    try:
        return 'IP:' + str(ipaddress.ip_address(host))
    except ValueError:
        if len(host) > 253 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host):
            raise ValueError('Host must be an IP address or DNS name, without scheme or port')
        if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in host.split('.')):
            raise ValueError('Invalid DNS hostname')
        return 'DNS:' + host


def owned(path, mode, gid=0):
    os.chown(path, 0, gid)
    os.chmod(path, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-gid', required=True, type=int, help='Existing host group ID used by the application container')
    parser.add_argument('--admin-group', required=True, help='Existing host group authorized to reset keys (no implicit root bypass)')
    parser.add_argument('--pam-service', required=True, help='Existing /etc/pam.d service supporting password and account checks')
    parser.add_argument('--host', action='append', required=True, help='NAS DNS name or IP; repeat for each certificate SAN')
    parser.add_argument('--replace-certificate', action='store_true', help='Explicitly replace an existing TLS certificate and key')
    parser.add_argument('--no-start', action='store_true', help='Install files without enabling or starting the service')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        parser.error('Run as root on a Linux host with PAM and systemd')
    for program in ('systemctl', 'openssl'):
        if not shutil.which(program):
            parser.error(f'Required program missing: {program}')
    if not Path('/run/systemd/system').is_dir() or not ctypes.util.find_library('pam'):
        parser.error('An active systemd host and libpam are required; install this adapter on the NAS host, not inside the application container')
    try:
        grp.getgrgid(args.app_gid)
        grp.getgrnam(args.admin_group)
        sans = [certificate_san(host) for host in args.host]
    except (KeyError, ValueError) as exc:
        parser.error(str(exc))
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', args.pam_service) or not Path('/etc/pam.d', args.pam_service).is_file():
        parser.error('Select an existing PAM service under /etc/pam.d')
    source = Path(__file__).resolve().parent
    lib = Path('/usr/local/lib/carddock-admin')
    config = Path('/etc/carddock')
    tls = config / 'tls'
    for directory, mode, gid in ((lib, 0o755, 0), (config, 0o755, 0), (tls, 0o750, args.app_gid)):
        directory.mkdir(parents=True, exist_ok=True)
        owned(directory, mode, gid)
    key, cert = tls / 'server.key', tls / 'server.crt'
    if key.exists() != cert.exists() and not args.replace_certificate:
        parser.error('Incomplete TLS pair; supply a complete pair or explicitly use --replace-certificate')
    if not key.exists() or args.replace_certificate:
        with tempfile.TemporaryDirectory(dir=tls) as temporary:
            tmp = Path(temporary)
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-sha256', '-nodes', '-days', '825',
                            '-keyout', str(tmp / 'server.key'), '-out', str(tmp / 'server.crt'),
                            '-subj', '/CN=CardDock NAS', '-addext', 'subjectAltName=' + ','.join(sans)], check=True)
            for name in ('server.key', 'server.crt'):
                os.replace(tmp / name, tls / name)
    else:
        print('Keeping existing TLS certificate. Use --replace-certificate to apply different hosts.')
    owned(key, 0o640, args.app_gid)
    owned(cert, 0o644, args.app_gid)
    shutil.copyfile(source / 'nas_auth.py', lib / 'nas_auth.py')
    owned(lib / 'nas_auth.py', 0o644)
    settings = config / 'admin.json'
    settings.write_text(json.dumps({'app_gid': args.app_gid, 'admin_group': args.admin_group, 'pam_service': args.pam_service}, indent=2) + '\n')
    owned(settings, 0o600)
    unit = (source / 'carddock-admin.service').read_text().replace('@APP_GID@', str(args.app_gid)).replace('@PYTHON@', sys.executable)
    target = Path('/etc/systemd/system/carddock-admin.service')
    target.write_text(unit)
    owned(target, 0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    if not args.no_start:
        subprocess.run(['systemctl', 'enable', 'carddock-admin.service'], check=True)
        subprocess.run(['systemctl', 'restart', 'carddock-admin.service'], check=True)
        subprocess.run(['systemctl', 'is-active', '--quiet', 'carddock-admin.service'], check=True)
    print('Adapter installed. Socket: /run/carddock-admin/auth.sock; TLS: /etc/carddock/tls')


if __name__ == '__main__':
    main()
