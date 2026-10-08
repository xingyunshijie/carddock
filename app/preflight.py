"""Runs inside the same restricted container as the app; never writes sources."""
import json,os,re,tempfile
from pathlib import Path

def inspect():
    if os.geteuid()==0:raise ValueError('容器不能以 root 运行')
    roots=os.environ['SOURCE_ROOTS'].split(':')
    for root in roots:
        p=Path(root)
        if not p.is_dir() or not os.access(p,os.R_OK|os.X_OK):raise ValueError('源目录不可读取：'+root)
    lines=Path('/proc/self/mountinfo').read_text().splitlines()
    mounted=[]
    for line in lines:
        a,b=line.split(' - ',1);fields=a.split();target=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),fields[4])
        mounted.append((target,fields[5].split(',')))
    for root in roots:
        entries=[opts for target,opts in mounted if target==root or target.startswith(root.rstrip('/')+'/')]
        if not entries or any('ro' not in opts for opts in entries):raise ValueError('源目录或其子挂载不是只读；请调整 NAS 挂载权限后重试')
    host=Path(os.environ['HOST_MOUNTINFO'])
    if ' - ' not in host.read_text():raise ValueError('宿主挂载信息无效')
    if not Path('/sys/dev/block').is_dir():raise ValueError('无法访问块设备信息')
    for root in os.environ['TARGET_ROOTS'].split(':')+[os.environ['STATE_DIR']]:
        with tempfile.TemporaryFile(dir=root) as f:f.write(b'CardDock permission check');f.flush();os.fsync(f.fileno())
    if os.getenv('TLS_CERT'):
        import ssl,socket,stat
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(os.environ['TLS_CERT'],os.environ['TLS_KEY'])
        if not stat.S_ISSOCK(os.stat(os.environ['ADMIN_AUTH_SOCKET']).st_mode):raise ValueError('认证服务未启动')
        with socket.socket(socket.AF_UNIX) as s:s.settimeout(2);s.connect(os.environ['ADMIN_AUTH_SOCKET'])
    print('容器身份、目录读写、源挂载只读、设备信息及可选 TLS 检查通过。插拔新卡后须再次检查。')
if __name__=='__main__':inspect()
