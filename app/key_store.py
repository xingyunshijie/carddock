import json,os,secrets,re,hmac,tempfile,threading,time,socket
from pathlib import Path

class KeyStore:
    def __init__(self,path,initial='CardDock'):
        self.path=Path(path);self.initial=initial;self.lock=threading.RLock()
    def current(self):
        with self.lock:
            if self.path.exists():
                data=json.loads(self.path.read_text())
                if not isinstance(data.get('token'),str) or not data['token']:raise ValueError('访问密钥配置损坏')
                return data['token']
            return self.initial
    def authorized(self,value):return hmac.compare_digest(value.encode(),('Bearer '+self.current()).encode())
    def rotate(self,mode,key,username):
        if mode not in ('custom','random'):raise ValueError('请选择修改方式')
        if mode=='random':key=secrets.token_urlsafe(32)
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',key):raise ValueError('新密钥须为 8–128 位字母、数字、下划线或短横线')
        with self.lock:
            if hmac.compare_digest(key,self.current()):raise ValueError('新密钥与当前密钥相同，请更换')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            fd,tmp=tempfile.mkstemp(prefix='.key-',dir=self.path.parent)
            try:
                with os.fdopen(fd,'w') as f:
                    os.fchmod(f.fileno(),0o600);json.dump({'token':key,'updated_by':username,'updated_at':time.time()},f);f.flush();os.fsync(f.fileno())
                os.replace(tmp,self.path)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
            return key

class AttemptLimiter:
    def __init__(self):self.lock=threading.Lock();self.attempts={}
    def take(self,ip,username):
        now=time.monotonic()
        with self.lock:
            self.attempts={k:[t for t in v if now-t<300] for k,v in self.attempts.items() if v and now-v[-1]<300}
            keys=['ip:'+ip,'user:'+username]
            if any(len(self.attempts.get(k,[]))>=3 for k in keys):return False
            for k in keys:self.attempts.setdefault(k,[]).append(now)
            return True
    def success(self,ip,username):
        with self.lock:
            for k in ['ip:'+ip,'user:'+username]:self.attempts.pop(k,None)

def verify_admin(username,password,socket_path):
    if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,64}',username):return False
    if not isinstance(password,str) or not password or len(password)>1024:return False
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(15);s.connect(socket_path)
            s.sendall(json.dumps({'username':username,'password':password}).encode()+b'\n')
            data=b''
            while not data.endswith(b'\n') and len(data)<1024:
                part=s.recv(1024)
                if not part:break
                data+=part
            return json.loads(data).get('ok') is True
    except (OSError,ValueError):raise RuntimeError('NAS 管理员验证服务不可用，请检查管理服务是否启动')
