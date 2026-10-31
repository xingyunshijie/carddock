"""Initialize only fresh app folders, then run every command without root."""
import os
import stat
import sys
from pathlib import Path

if os.geteuid() == 0:
    uid, gid = int(os.getenv('PUID', '1000')), int(os.getenv('PGID', '1000'))
    if uid <= 0 or gid <= 0:
        raise SystemExit('PUID 和 PGID 必须是非 root 身份')
    # Do not recursively change an existing share or existing application state.
    for value in [os.getenv('STATE_DIR', '/state')] + os.getenv('TARGET_ROOTS', '/storage').split(':'):
        p = Path(value)
        if p.is_symlink():
            raise SystemExit('拒绝初始化符号链接目录')
        info = p.stat()
        if stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not any(p.iterdir()):
            os.chown(p, uid, gid)
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
if not sys.argv[1:]:
    raise SystemExit('缺少启动命令')
os.execvp(sys.argv[1], sys.argv[1:])
