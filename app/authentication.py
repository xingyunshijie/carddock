"""Single-user Compose password authentication, with expiring per-tab bearer sessions."""
import hashlib,hmac,os,secrets,threading,time

class PasswordAuthentication:
    def __init__(self,environment=None):
        env=os.environ if environment is None else environment
        self.configured='AUTHENTICATION_ENABLED' in env or 'AUTHENTICATION_PASSWORD' in env
        value=env.get('AUTHENTICATION_ENABLED','true').lower().strip()
        if self.configured and value not in ('true','false'):raise ValueError('AUTHENTICATION_ENABLED 必须为 true 或 false')
        self.enabled=value!='false';self.lock=threading.RLock();self.sessions={};self.lifetime=12*60*60
        password=env.get('AUTHENTICATION_PASSWORD','')
        if self.configured and self.enabled:
            if len(password)<12 or len(password)>256 or password.startswith('CHANGE_ME') or password in ('改成你自己的密码','请修改为你自己的登录密码'):
                raise ValueError('请将 AUTHENTICATION_PASSWORD 改成自己的12–256位登录密码，不能使用示例占位值')
        self.digest=hashlib.sha256(password.encode('utf-8')).digest()
    def login(self,password):
        if not self.configured:raise ValueError('此实例沿用旧版访问认证')
        if not self.enabled:return ''
        if not isinstance(password,str) or len(password)>256:return None
        if not hmac.compare_digest(hashlib.sha256(password.encode('utf-8')).digest(),self.digest):return None
        with self.lock:
            now=time.monotonic();self.sessions={k:v for k,v in self.sessions.items() if now-v<self.lifetime}
            if len(self.sessions)>=256:self.sessions.pop(next(iter(self.sessions)))
            token=secrets.token_urlsafe(32);self.sessions[token]=now;return token
    def authorized(self,header):
        if not self.enabled:return True
        if not isinstance(header,str) or not header.startswith('Bearer '):return False
        token=header[7:]
        with self.lock:
            when=self.sessions.get(token)
            if when is None:return False
            if time.monotonic()-when>=self.lifetime:self.sessions.pop(token,None);return False
            return True
    def logout(self,header):
        with self.lock:self.sessions.pop(header[7:] if header.startswith('Bearer ') else '',None)
