#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Initialize a unique key, or rotate it using NAS administrator privileges."""
import argparse, getpass, json, os, re, secrets, subprocess, tempfile
from pathlib import Path

PLACEHOLDER = 'replace-with-a-long-random-secret'
def read_key(text):
    values = re.findall(r'^ACCESS_TOKEN=(.*)$', text, re.M)
    if len(values) > 1: raise ValueError('ACCESS_TOKEN 重复，请先检查 .env')
    return values[0].strip().strip('\"\'') if values else ''
def with_key(text, key):
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', key):
        raise ValueError('密钥须为 8–128 位字母、数字、下划线或短横线')
    read_key(text)
    lines=text.splitlines(); lines=[line for line in lines if not line.startswith('ACCESS_TOKEN=')]
    return '\n'.join(lines)+('\n' if lines else '')+'ACCESS_TOKEN='+key+'\n'
def write_private(path, text):
    if path.is_symlink(): raise ValueError('密钥文件不能是符号链接')
    previous=path.stat() if path.exists() else None
    fd, tmp=tempfile.mkstemp(prefix='.carddock-key-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w') as f:
            os.fchmod(f.fileno(),0o600)
            if previous and os.geteuid()==0: os.fchown(f.fileno(),previous.st_uid,previous.st_gid)
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def initialize(path):
    text=path.read_text() if path.exists() else ''
    if read_key(text) not in ('',PLACEHOLDER): return None
    key=secrets.token_urlsafe(32); write_private(path,with_key(text,key)); return key

def command(args, input=None):
    env=dict(os.environ); env.pop('ACCESS_TOKEN',None)
    p=subprocess.run(args,input=input,text=True,capture_output=True,env=env)
    if p.returncode: raise RuntimeError('Docker 命令失败，请在 NAS 管理界面检查 CardDock 状态')
    return p.stdout

def reset(path=None, custom=False, compose_file=None):
    if os.geteuid()!=0: raise PermissionError('重置访问密钥需要 NAS 管理员权限，请使用 sudo')
    key=None
    if custom:
        key=getpass.getpass('输入新访问密钥（至少 8 位）：')
        if key!=getpass.getpass('再次输入新密钥：'): raise ValueError('两次输入不一致')
        with_key('',key)
    code='import os,json,sys;from pathlib import Path;from key_store import KeyStore;d=json.load(sys.stdin);s=KeyStore(Path(os.environ["STATE_DIR"])/"access-key.json",os.getenv("ACCESS_TOKEN","CardDock"));old=s.current();new=s.rotate(d["mode"],d["key"],"NAS administrator terminal");assert not s.authorized("Bearer "+old);assert s.authorized("Bearer "+new);print(json.dumps({"key":new}))'
    prefix=['docker','compose','-f',str(Path(compose_file).resolve()),'exec','-T','carddock'] if compose_file else ['docker','exec','-i','carddock']
    result=json.loads(command(prefix+['python','-c',code],json.dumps({'mode':'custom' if custom else 'random','key':key})))
    return result['key']

def main():
    parser=argparse.ArgumentParser(description='CardDock 访问密钥管理')
    parser.add_argument('action',choices=['init','reset']); parser.add_argument('--env-file',type=Path,default=Path('.env'))
    parser.add_argument('--compose-file',type=Path,help='通用部署的 Compose 配置文件')
    parser.add_argument('--custom',action='store_true',help='由管理员交互输入新密钥')
    args=parser.parse_args()
    try:
        key=initialize(args.env_file) if args.action=='init' else reset(args.env_file,args.custom,args.compose_file)
        print('已有访问密钥，保持不变。' if key is None else '访问密钥（请保存）：\n'+key)
        if args.action=='reset': print('旧密钥已失效，请在浏览器重新连接。')
    except (ValueError,OSError,RuntimeError,KeyError) as e: parser.exit(1,str(e)+'\n')
if __name__=='__main__': main()
