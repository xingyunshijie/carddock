#!/usr/bin/env python3
"""Render the self-contained manual from the distributed Markdown source."""
from pathlib import Path
from html import escape
root=Path(__file__).resolve().parents[1]
source=(root/'docs/HELP.md').read_text()
parts=[]
for line in source.splitlines():
    if not line:continue
    if line.startswith('# '):parts.append('<h1>'+escape(line[2:])+'</h1>')
    elif line.startswith('## '):parts.append('<h2>'+escape(line[3:])+'</h2>')
    else:parts.append('<p>'+escape(line)+'</p>')
body='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>影像归仓 · 安装与使用帮助</title><link rel="stylesheet" href="/style.css"><main class="release"><a href="/">← 返回影像归仓</a><article>'+''.join(parts)+'</article></main></html>'
(root/'app/static/help.html').write_text(body)

standalone=body.replace('<link rel="stylesheet" href="/style.css">','<style>'+(root/'app/static/style.css').read_text()+'</style>').replace('<a href="/">← 返回影像归仓</a>','<a href="https://github.com/xingyunshijie/carddock">影像归仓官方仓库</a>')
(root/'CardDock-help.html').write_text(standalone)
