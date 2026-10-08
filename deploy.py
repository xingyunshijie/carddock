#!/usr/bin/env python3
"""Portable NAS Compose configuration and guarded lifecycle. Python 3.8+."""
import secrets
import argparse, ipaddress, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def run(args, capture=False):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None).stdout

def private_json(path, data):
    path=Path(path)
    if path.is_symlink(): raise ValueError('拒绝写入符号链接')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.carddock-')
    try:
        with os.fdopen(fd,'w') as f:
            os.fchmod(f.fileno(),0o600);json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def bind(source,target,readonly=False,propagation=None):
    b={'type':'bind','source':str(source),'target':target,'read_only':readonly,'bind':{'create_host_path':False}}
    if propagation:b['bind']['propagation']=propagation
    return b

def configuration(a):
    if a.uid<=0 or a.gid<=0:raise ValueError('容器须使用非 root UID/GID')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*',a.project):raise ValueError('项目名仅支持小写字母、数字、下划线和短横线')
    ipaddress.ip_address(a.bind)
    if not 1<=a.port<=65535 or not 1<=a.https_port<=65535:raise ValueError('端口须为 1–65535')
    if a.admin_host and a.https_port==a.port:raise ValueError('HTTP 和 HTTPS 端口不能相同')
    paths=[Path(p).expanduser().resolve() for p in [a.source,a.primary]+([a.backup] if a.backup else [])+[a.state]]
    for p in paths:
        if not p.is_dir():raise ValueError('目录不存在，请先创建并设置权限：'+str(p))
    for i,p in enumerate(paths):
        for q in paths[i+1:]:
            if p==q or p in q.parents or q in p.parents or p.samefile(q):raise ValueError('源、目标和状态目录不能相同或相互包含')
    source,primary=paths[:2];state=paths[-1]
    env={'ACCESS_TOKEN':secrets.token_urlsafe(32),'SOURCE_ROOTS':'/sources','TARGET_ROOTS':'/destinations/primary','STATE_DIR':'/state','HOST_MOUNTINFO':'/host/mountinfo'}
    volumes=[bind(source,'/sources',True,'rslave'),bind(primary,'/destinations/primary'),bind(state,'/state'),bind('/proc/1/mountinfo','/host/mountinfo',True),bind('/sys','/sys',True)]
    if a.backup:
        env['TARGET_ROOTS']+=':/destinations/backup';volumes.append(bind(paths[2],'/destinations/backup'))
    host='['+a.bind+']' if ':' in a.bind else a.bind
    ports=[f'{host}:{a.port}:8080']
    if a.admin_host:
        name=a.admin_host.strip('[]')
        try:ipaddress.ip_address(name)
        except ValueError:
            if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',name):raise ValueError('管理地址须为 IP 或主机名，不含协议和路径')
        authority='['+name+']' if ':' in name else name
        env.update(ADMIN_HTTPS_URL=f'https://{authority}:{a.https_port}',ADMIN_AUTH_SOCKET='/run/carddock-admin/auth.sock',TLS_CERT='/tls/server.crt',TLS_KEY='/tls/server.key')
        ports.append(f'{host}:{a.https_port}:8443')
        volumes.extend([bind('/etc/carddock/tls','/tls',True),bind('/run/carddock-admin','/run/carddock-admin',True)])
    service={'image':a.image or 'carddock:0.12.0-beta.1','restart':'unless-stopped','user':f'{a.uid}:{a.gid}','ports':ports,'environment':env,'volumes':volumes,'read_only':True,'tmpfs':['/tmp:size=64m'],'cap_drop':['ALL'],'security_opt':['no-new-privileges:true']}
    if not a.image:service['build']={'context':str(ROOT),'args':{'INSTALL_EXIFTOOL':'1'}}
    return {'name':a.project,'services':{'carddock':service}}

GUARD='''import json,os,urllib.request
from pathlib import Path
from key_store import KeyStore
key=KeyStore(Path(os.environ['STATE_DIR'])/'access-key.json',os.getenv('ACCESS_TOKEN','CardDock')).current()
r=urllib.request.Request('http://127.0.0.1:8080/api/state',headers={'Authorization':'Bearer '+key})
s=json.load(urllib.request.urlopen(r,timeout=10))
assert not s['active'] and not s['config']['auto'], '请保存手动模式，并等待当前任务结束后更新'
'''

def compose(path,*args,capture=False):return run(['docker','compose','-f',str(path),*args],capture)
def running(path):return compose(path,'ps','-q','carddock',capture=True).strip()
def guard(path):compose(path,'exec','-T','carddock','python','-c',GUARD)
def check(path):
    compose(path,'config','--quiet')
    compose(path,'run','--rm','--no-deps','--entrypoint','python','carddock','/app/preflight.py')
def ready(path):
    for _ in range(30):
        try:
            compose(path,'exec','-T','carddock','python','-c',"import urllib.request;assert urllib.request.urlopen('http://127.0.0.1:8080/',timeout=2).status==200")
            return
        except subprocess.CalledProcessError:time.sleep(1)
    raise RuntimeError('健康检查未通过；请查看 Docker 日志，可用 rollback 恢复')

def main():
    p=argparse.ArgumentParser(description='影像归仓通用 NAS 安装工具')
    p.add_argument('--file',type=Path,default=ROOT/'deployment/compose.json')
    sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('configure')
    for name in ('source','primary','state'):c.add_argument('--'+name,required=True)
    c.add_argument('--backup');c.add_argument('--uid',type=int,required=True);c.add_argument('--gid',type=int,required=True)
    c.add_argument('--bind',default='0.0.0.0');c.add_argument('--port',type=int,default=8080);c.add_argument('--project',default='carddock');c.add_argument('--image');c.add_argument('--admin-host');c.add_argument('--https-port',type=int,default=8443)
    for name in ('check','start','update','rollback'):sub.add_parser(name)
    a=p.parse_args();path=a.file.resolve()
    if a.action=='configure':
        if path.exists():raise ValueError('部署配置已存在；请备份后手动编辑，避免覆盖现有设置')
        private_json(path,configuration(a));print('配置已生成：'+str(path));print('随机访问密钥已保存在配置文件的 ACCESS_TOKEN 中，请妥善保存。');return
    data=json.loads(path.read_text());backup=path.with_name('rollback.json');deployed=path.with_name('deployed.json')
    if a.action=='check':check(path);return
    if a.action=='rollback':
        old=json.loads(backup.read_text())
        if old.get('name')!=data.get('name'):raise ValueError('回退项目不匹配')
        if running(path):guard(path)
        compose(backup,'up','-d','--no-build','--pull','never','carddock');ready(backup);private_json(path,old);private_json(deployed,old);return
    cid=running(path)
    if a.action=='start' and cid:raise ValueError('服务正在运行，请使用 update')
    if a.action=='update' and not cid:raise ValueError('未找到运行中的服务，请检查项目名和配置')
    if cid:
        if not deployed.exists():raise ValueError('缺少已部署配置快照；旧版安装请按迁移文档处理')
        previous=json.loads(deployed.read_text())
        before=json.loads(json.dumps(previous));after=json.loads(json.dumps(data))
        for config in (before,after):
            config['services']['carddock'].pop('build',None);config['services']['carddock'].pop('image',None)
        if before!=after:raise ValueError('update 仅更新镜像；目录、端口或身份变更请先备份并单独迁移')
        guard(path)
        oldid=run(['docker','inspect','--format','{{.Image}}',cid],True).strip()
        tag=data['name']+':rollback-'+str(int(time.time()))
        run(['docker','image','tag',oldid,tag])
        old=json.loads(json.dumps(previous));old['services']['carddock'].pop('build',None);old['services']['carddock']['image']=tag
        private_json(backup,old)
    if 'build' in data['services']['carddock']:compose(path,'build','carddock')
    else:compose(path,'pull','--policy','missing','carddock')
    check(path)
    if cid:guard(path)
    compose(path,'up','-d','--no-build','--pull','never','carddock');ready(path);private_json(deployed,data)
    print('影像归仓已启动；首次在网页选择主文件夹并保存。已有设置和密钥保留。')
if __name__=='__main__':
    try:main()
    except (ValueError,OSError,RuntimeError,subprocess.CalledProcessError) as e:sys.exit(str(e))
