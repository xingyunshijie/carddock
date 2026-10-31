import os, json, threading, hmac, ssl, secrets, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs
from core import Engine, browse_directories
from reports import export
from rules import component
from core import safe_path
from key_store import KeyStore, AttemptLimiter, verify_admin
from authentication import PasswordAuthentication

engine=Engine(os.getenv('STATE_DIR','/state'),os.getenv('SOURCE_ROOTS','/sources').split(':'),os.getenv('TARGET_ROOTS','/destinations').split(':'),[p for p in os.getenv('MANUAL_SOURCE_ROOTS','').split(':') if p])
password_auth=PasswordAuthentication()
TOKEN=os.getenv('ACCESS_TOKEN','CardDock')
keys=KeyStore(engine.state/'access-key.json',TOKEN)
limiter=AttemptLimiter()
challenges={}
challenge_lock=threading.Lock()
admin_gate=threading.BoundedSemaphore(2)
STATIC=Path(__file__).parent/'static'
class Handler(BaseHTTPRequestHandler):
    def send(self,status,data,kind='application/json; charset=utf-8'):
        body=json.dumps(data,ensure_ascii=False).encode() if kind.startswith('application/json') else data
        self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'"); self.end_headers(); self.wfile.write(body)
    def authorized(self):
        header=self.headers.get('Authorization','')
        allowed=password_auth.authorized(header) if password_auth.configured else keys.authorized(header)
        if not allowed:self.send(401,{'error':'请登录' if password_auth.configured else '请输入访问密钥'});return False
        return True
    def do_GET(self):
        u=urlsplit(self.path); q=parse_qs(u.query)
        if u.path=='/api/auth':
            self.send(200,{'mode':'password' if password_auth.configured else 'legacy','enabled':password_auth.enabled if password_auth.configured else True});return
        if u.path=='/access-key':
            if not isinstance(self.connection,ssl.SSLSocket):
                target=os.getenv('ADMIN_HTTPS_URL','')
                if not target: self.send(200,(STATIC/'access-key-unavailable.html').read_bytes(),'text/html; charset=utf-8'); return
                self.send_response(303); self.send_header('Location',target+'/access-key'); self.send_header('Content-Length','0'); self.end_headers(); return
        if u.path=='/api/admin/challenge':
            if not isinstance(self.connection,ssl.SSLSocket): self.send(403,{'error':'密钥管理必须通过 HTTPS 访问'}); return
            with challenge_lock:
                now=time.monotonic()
                for k in list(challenges):
                    if now-challenges[k][1]>60: challenges.pop(k,None)
                if len(challenges)>=256: self.send(429,{'error':'请稍后再试'}); return
                nonce=secrets.token_urlsafe(32);challenges[nonce]=(self.client_address[0],now)
            self.send(200,{'nonce':nonce}); return
        if not u.path.startswith('/api/'):

            names={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/icon.svg':('icon.svg','image/svg+xml'),'/brand.png':('brand.png','image/png'),'/version':('version.html','text/html; charset=utf-8'),'/access-key':('access-key.html','text/html; charset=utf-8'),'/access-key.js':('access-key.js','text/javascript; charset=utf-8')}
            if u.path not in names: self.send(404,{'error':'Not found'}); return
            name,kind=names[u.path]; self.send(200,(STATIC/name).read_bytes(),kind); return
        if not self.authorized(): return
        try:
            if u.path=='/api/state':
                for job in list(engine.jobs.values()):
                    if job['status'] in ('running','paused','pausing','stopping'): engine.metrics(job)
                with engine.lock: data={'config':engine.config,'jobs':[{k:v for k,v in j.items() if k!='manifest'} for j in sorted(engine.jobs.values(),key=lambda j:j['created'],reverse=True)[:100]],'active':engine.active,'watch_status':engine.watch_status,'scan_error':engine.scan_error,'version':'1.0.0-nas.2','source_roots':[str(p) for p in engine.sources],'target_roots':[str(p) for p in engine.targets]}; self.send(200,data)
            elif u.path=='/api/report':
                ident=q.get('id',[''])[0]
                with engine.lock:
                    if ident not in engine.jobs: raise ValueError('任务不存在')
                    job=json.loads(json.dumps(engine.jobs[ident]))
                kind=q.get('format',['json'])[0]
                if kind=='json':self.send(200,job)
                else:
                    body,mime,_=export(job,kind);self.send(200,body,mime)
            elif u.path=='/api/presets':self.send(200,engine.presets())
            elif u.path=='/api/devices': self.send(200,engine.devices())
            elif u.path=='/api/preview': self.send(200,engine.preview(q.get('path',[''])[0]))
            elif u.path=='/api/browse':
                roots=engine.sources if q.get('kind',['target'])[0]=='source' else engine.targets
                path=q.get('path',[''])[0]
                labels=json.loads(os.getenv('TARGET_LABELS','{}'))
                self.send(200,browse_directories(path,roots,labels))
            else: self.send(404,{'error':'Not found'})
        except Exception as e: self.send(400,{'error':str(e)})
    def admin_reset(self):
        if not isinstance(self.connection,ssl.SSLSocket):
            self.close_connection=True; self.send(403,{'error':'密钥管理必须通过 HTTPS 访问'}); return
        if self.headers.get('Origin')!='https://'+self.headers.get('Host','') or self.headers.get('X-CardDock-Admin')!='1':
            self.close_connection=True; self.send(403,{'error':'请从密钥管理页面提交'}); return
        if not admin_gate.acquire(blocking=False): self.send(429,{'error':'请稍后再试'}); return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>8192: raise ValueError('请求无效')
            self.connection.settimeout(20)
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError('请求无效')
            username=data.get('username',''); password=data.get('password','')
            with challenge_lock: challenge=challenges.pop(data.get('nonce',''),None)
            if not challenge or challenge[0]!=self.client_address[0] or time.monotonic()-challenge[1]>60: raise ValueError('页面验证已过期，请重试')
            if not isinstance(username,str) or not isinstance(password,str): raise ValueError('请输入管理员账号与密码')
            if not limiter.take(self.client_address[0],username): self.send(429,{'error':'尝试次数过多，请 5 分钟后重试'}); return
            if not verify_admin(username,password,os.getenv('ADMIN_AUTH_SOCKET','/run/carddock-admin/auth.sock')):
                self.send(403,{'error':'管理员账号、密码或权限验证未通过'}); return
            password=None;data.pop('password',None)
            token=keys.rotate(data.get('mode'),data.get('key'),username)
            limiter.success(self.client_address[0],username)
            self.send(200,{'key':token,'message':'新密钥已生效，旧密钥已失效'})
        except (ValueError,TypeError): self.send(400,{'error':'请求或新密钥无效；自定义密钥需 8–128 位字母、数字、下划线或短横线'})
        except (OSError,RuntimeError): self.send(503,{'error':'管理员验证或密钥保存失败，原密钥保持有效，请检查 NAS 管理服务'})
        finally: admin_gate.release()
    def do_POST(self):
        if self.path=='/api/login':
            origin=self.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=self.headers.get('Host'):self.send(403,{'error':'跨域请求被拒绝'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=4096:raise ValueError('无效登录请求')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('无效登录请求')
                if not limiter.take(self.client_address[0],'login'):self.send(429,{'error':'登录尝试过多，请5分钟后再试'});return
                token=password_auth.login(data.get('password'))
                if token is None:self.send(401,{'error':'密码错误'});return
                limiter.success(self.client_address[0],'login');self.send(200,{'token':token});return
            except (ValueError,TypeError):self.send(400,{'error':'无效登录请求'});return
        if self.path=='/api/admin/reset': self.admin_reset(); return
        if not self.authorized(): return
        # Browser cross-origin posts are rejected, even if a proxy strips Authorization.
        origin=self.headers.get('Origin')
        if origin and urlsplit(origin).netloc!=self.headers.get('Host'): self.send(403,{'error':'跨域请求被拒绝'}); return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>65536: raise ValueError('请求过大')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise ValueError('请求必须为对象')
            if self.path=='/api/logout':
                password_auth.logout(self.headers.get('Authorization',''));self.send(200,{'ok':True})
            elif self.path=='/api/config': self.send(200,engine.configure(data))
            elif self.path=='/api/mkdir':
                parent=safe_path(data['parent'],engine.targets);name=component(data['name'])
                if not name:raise ValueError('请输入文件夹名')
                path=parent/name;engine.destination_path(path);path.mkdir(mode=0o755)
                self.send(201,{'path':str(path)})
            elif self.path=='/api/reader':
                engine.set_reader_origin(data['reader_id'],data['origin']); self.send(200,{'ok':True})
            elif self.path=='/api/control': self.send(200,engine.control(data['id'],data['action']))
            elif self.path=='/api/jobs':self.send(201,engine.submit(data['source'],enqueue=data.get('enqueue') is True))
            elif self.path=='/api/retry':self.send(201,engine.retry(data['id']))
            elif self.path=='/api/remove':self.send(200,engine.remove(data['id']))
            elif self.path=='/api/presets':self.send(200,engine.presets(data['name'],data.get('options'),data.get('delete') is True))
            elif self.path=='/api/queue/start':
                with engine.lock:
                    if engine.active:raise ValueError('已有任务运行中')
                    queued=sorted((j for j in engine.jobs.values() if j['status']=='queued'),key=lambda j:j['created'])
                    if queued:engine.start_job(queued[0])
                self.send(200,{'ok':True})
            else: self.send(404,{'error':'Not found'})
        except Exception as e: self.send(400,{'error':str(e)})
if __name__=='__main__':
    if not password_auth.configured and TOKEN=='replace-with-a-long-random-secret': raise SystemExit('请先运行 python3 access-key.py init 生成初始访问密钥')
    if not password_auth.configured and not TOKEN and os.getenv('ALLOW_NO_AUTH')!='1': raise SystemExit('请设置 ACCESS_TOKEN（本机开发可设置 ALLOW_NO_AUTH=1）')
    cert=os.getenv('TLS_CERT',''); private_key=os.getenv('TLS_KEY','')
    if cert and private_key:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert,private_key)
        secure=ThreadingHTTPServer(('0.0.0.0',int(os.getenv('HTTPS_PORT','8443'))),Handler)
        secure.socket=context.wrap_socket(secure.socket,server_side=True)
        threading.Thread(target=secure.serve_forever,daemon=True).start()
    threading.Thread(target=engine.monitor,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
