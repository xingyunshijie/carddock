#!/bin/sh
set -eu
python - <<'CHECK'
from authentication import PasswordAuthentication
import os
if not PasswordAuthentication().configured and not os.path.isfile('/state/access-key.json'):
    raise SystemExit('请在 Docker 项目中设置 AUTHENTICATION_ENABLED=true 和自己的 AUTHENTICATION_PASSWORD')
CHECK
python /app/preflight.py
exec python /app/server.py
