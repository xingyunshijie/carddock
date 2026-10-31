#!/usr/bin/env python3
"""Copy the tested public image to an owner-authorized registry, without rebuilding."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'ghcr.io/xingyunshijie/carddock'


def validate_image(value):
    pattern = r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?/(?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)*[a-z0-9]+(?:[._-][a-z0-9]+)*'
    if not re.fullmatch(pattern, value) or '.' not in value.split('/')[0]:
        raise ValueError('CN_IMAGE 应为控制台提供的完整仓库地址，不含协议、版本或密码')
    if value.split('/')[0] == 'ghcr.io':
        raise ValueError('国内仓库不能仍然填写 ghcr.io')
    return value


def manifest_info(raw):
    manifest = json.loads(raw)
    platforms = {(x.get('platform', {}).get('os'), x.get('platform', {}).get('architecture'))
                 for x in manifest.get('manifests', [])}
    if not {('linux', 'amd64'), ('linux', 'arm64')} <= platforms:
        raise ValueError('镜像必须同时包含 linux/amd64 和 linux/arm64')
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def run(args, **kwargs):
    return subprocess.run(['skopeo', *args], check=True, **kwargs)


def inspect(image):
    return run(['inspect', '--no-creds', '--retry-times', '3', '--raw', 'docker://' + image],
               stdout=subprocess.PIPE).stdout


def sync(image, output, root=ROOT):
    image = validate_image(image)
    version = (root / 'VERSION').read_text().strip()
    if not re.fullmatch(r'1\.0\.0-nas\.\d+', version):
        raise ValueError('拒绝同步未知版本格式')
    user, password = os.getenv('CN_REGISTRY_USERNAME'), os.getenv('CN_REGISTRY_PASSWORD')
    if not user or not password:
        raise ValueError('请先在 GitHub Secrets 设置 CN_REGISTRY_USERNAME 和 CN_REGISTRY_PASSWORD')
    template = (root / 'compose.project.yaml').read_text()
    old = SOURCE + ':' + version
    if template.count(old) != 1:
        raise ValueError('安装配置与当前发布版本不一致')
    raw = inspect(old)
    digest = manifest_info(raw)
    destination = image + ':' + version
    with tempfile.TemporaryDirectory(prefix='carddock-registry-') as temp:
        auth = Path(temp) / 'auth.json'
        run(['login', '--authfile', str(auth), '--username', user, '--password-stdin',
             image.split('/')[0]], input=(password + '\n').encode(), stdout=subprocess.DEVNULL)
        password = None
        run(['copy', '--all', '--preserve-digests', '--retry-times', '3', '--authfile', str(auth),
             'docker://' + SOURCE + '@' + digest, 'docker://' + destination])
        # Do not use the publisher's credentials for this check.
        target_raw = inspect(destination)
        if manifest_info(target_raw) != digest:
            raise ValueError('国内镜像与已测试镜像摘要不一致，停止生成安装配置')
        # Check that both per-platform manifests are publicly accessible too.
        for item in json.loads(target_raw)['manifests']:
            platform = item.get('platform', {})
            if platform.get('os') == 'linux' and platform.get('architecture') in ('amd64', 'arm64'):
                inspect(image + '@' + item['digest'])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    config = output / 'compose.cn.yaml'
    config.write_text(template.replace(old, destination))
    receipt = output / 'registry-verification.json'
    receipt.write_text(json.dumps({'version': version, 'image': destination, 'source': old,
                                  'digest': digest, 'anonymous_manifest_access': True,
                                  'platforms': ['linux/amd64', 'linux/arm64']}, indent=2) + '\n')
    (output / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
        for p in (config, receipt)))
    print('国内镜像同步和免登录清单检查通过：' + destination)
    print('注意：还需在国内 NAS 实测完整拉取；清单检查不代表所有网络均可访问。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default=os.getenv('CN_IMAGE', ''))
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/domestic')
    args = parser.parse_args()
    try:
        sync(args.image, args.output)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
