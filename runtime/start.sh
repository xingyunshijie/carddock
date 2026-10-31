#!/bin/sh
# Run the uploaded release with the official Python image. No registry publication needed.
set -eu
RELEASE_ROOT=/opt/carddock
if [ ! -r "$RELEASE_ROOT/app/server.py" ] || [ ! -r "$RELEASE_ROOT/requirements.lock" ]; then
  echo '安装目录映射错误：请将完整解压目录映射到 /opt/carddock。' >&2; exit 1
fi
python -m pip install --no-index --no-deps --only-binary=:all: --find-links "$RELEASE_ROOT/wheelhouse" --require-hashes -r "$RELEASE_ROOT/requirements.lock" --target /opt/carddock-deps --no-compile --no-cache-dir --disable-pip-version-check
export PYTHONPATH=/opt/carddock-deps:/opt/carddock/app
export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Bundled IANA zone data also supplies libc local dates without changing host timezone.
if [ -f /opt/carddock-deps/tzdata/zoneinfo/Asia/Shanghai ]; then
  export TZ=:/opt/carddock-deps/tzdata/zoneinfo/Asia/Shanghai
fi
python - <<'PY'
from authentication import PasswordAuthentication
import os,re
from pathlib import Path
from key_store import KeyStore
auth=PasswordAuthentication()
import xxhash
from blake3 import blake3
assert xxhash.xxh64(b'abc').hexdigest()=='44bc2cf5ad770999'
assert blake3(b'abc').hexdigest()=='6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85'
if not auth.configured:
    state=Path(os.environ.get('STATE_DIR','/state'));key=KeyStore(state/'access-key.json',os.environ.get('ACCESS_TOKEN','')).current()
    legacy=(state/'config.json').is_file() and (state/'history.sqlite').is_file()
    if not (state/'access-key.json').exists() and (not key or key.startswith('CHANGE_ME') or not legacy and not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',key)):
        raise SystemExit('请在 Docker 项目中设置 AUTHENTICATION_ENABLED=true 和自己的 AUTHENTICATION_PASSWORD')
print('影像归仓 NAS 1.5.2 · 登录认证与校验依赖已就绪')
PY
python "$RELEASE_ROOT/app/preflight.py"
exec python "$RELEASE_ROOT/app/server.py"
