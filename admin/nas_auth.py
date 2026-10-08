#!/usr/bin/env python3
"""Root-only local PAM verifier. No commands or key mutations are accepted."""
import ctypes as C,ctypes.util,grp,pwd,os,json,socketserver,time,threading
from pathlib import Path

CONFIG = {}

def load_config(path="/etc/carddock/admin.json"):
    global CONFIG
    target = Path(path)
    st = target.stat()
    if st.st_uid != 0 or st.st_mode & 0o022:
        raise ValueError("Authentication configuration must be root-owned and not group/world writable")
    config = json.loads(target.read_text())
    grp.getgrnam(config["admin_group"])
    grp.getgrgid(config["app_gid"])
    service = config["pam_service"]
    if not isinstance(service, str) or not service or "/" in service or not Path("/etc/pam.d", service).is_file():
        raise ValueError("Configured PAM service is unavailable")
    CONFIG = config
    return config

class Message(C.Structure):_fields_=[('style',C.c_int),('msg',C.c_char_p)]
class Response(C.Structure):_fields_=[('resp',C.c_void_p),('code',C.c_int)]
Callback=C.CFUNCTYPE(C.c_int,C.c_int,C.POINTER(C.POINTER(Message)),C.POINTER(C.POINTER(Response)),C.c_void_p)
class Conversation(C.Structure):_fields_=[('conv',Callback),('data',C.c_void_p)]

def administrator(username):
    try:
        user=pwd.getpwnam(username)
        return grp.getgrnam(CONFIG['admin_group']).gr_gid in os.getgrouplist(username,user.pw_gid)
    except (KeyError,OSError):return False

def authenticate(username,password):
    if not administrator(username):return False
    pam=C.CDLL(ctypes.util.find_library('pam') or 'libpam.so.0');libc=C.CDLL(None)
    libc.calloc.argtypes=[C.c_size_t,C.c_size_t];libc.calloc.restype=C.c_void_p
    libc.strdup.argtypes=[C.c_char_p];libc.strdup.restype=C.c_void_p
    libc.free.argtypes=[C.c_void_p]
    pam.pam_start.argtypes=[C.c_char_p,C.c_char_p,C.POINTER(Conversation),C.POINTER(C.c_void_p)]
    for name in ('pam_authenticate','pam_acct_mgmt','pam_end'):
        getattr(pam,name).argtypes=[C.c_void_p,C.c_int];getattr(pam,name).restype=C.c_int
    @Callback
    def converse(n,messages,out,data):
        if n<=0 or n>16:return 19
        memory=libc.calloc(n,C.sizeof(Response))
        if not memory:return 5
        responses=C.cast(memory,C.POINTER(Response))
        for i in range(n):
            style=messages[i].contents.style
            if style in (1,2):responses[i].resp=libc.strdup((password if style==1 else username).encode())
            elif style not in (3,4):
                for j in range(i):
                    if responses[j].resp:libc.free(responses[j].resp)
                libc.free(memory);return 19
        out[0]=responses;return 0
    handle=C.c_void_p();conv=Conversation(converse,None)
    status=pam.pam_start(CONFIG['pam_service'].encode(),username.encode(),C.byref(conv),C.byref(handle))
    if status:return False
    try:
        status=pam.pam_authenticate(handle,1)
        if status==0:status=pam.pam_acct_mgmt(handle,0)
        return status==0
    finally:pam.pam_end(handle,status)

lock=threading.Lock();attempts=[]
class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(15)
        try:
            data=json.loads(self.rfile.readline(8193));u=data.get('username');p=data.get('password')
            if not isinstance(u,str) or not isinstance(p,str) or not u or not p or '\x00' in u or '\x00' in p or len(u)>64 or len(p)>1024:raise ValueError()
            with lock:
                now=time.monotonic();attempts[:]=[t for t in attempts if now-t<60]
                if len(attempts)>=10:raise ValueError()
                attempts.append(now)
            ok=authenticate(u,p);p=None;data.clear()
            self.wfile.write(json.dumps({'ok':ok}).encode()+b'\n')
        except Exception:
            try:self.wfile.write(b'{"ok":false}\n')
            except OSError:pass

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit('Requires NAS administrator installation')
    load_config()
    path='/run/carddock-admin/auth.sock'
    if os.path.exists(path):os.unlink(path)
    with socketserver.UnixStreamServer(path,Handler) as server:
        os.chown(path,0,CONFIG['app_gid']);os.chmod(path,0o660);server.serve_forever()
