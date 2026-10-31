"""Offline reports. HTML is printable to PDF in the browser; MHL is basic 1.1."""
import html,json,datetime,socket,xml.etree.ElementTree as ET
from pathlib import Path
NOTE='仅任务全部完成且所选范围通过内容校验才表示该次范围一致。快速模式仅核对大小；跳过冲突不代表已备份。报告不构成格式化授权。'

def export(j,kind):
    records=j.get('manifest',[])
    if kind=='json':return json.dumps(j,ensure_ascii=False,indent=2).encode(),'application/json; charset=utf-8','json'
    if kind=='txt':
        lines=['CardDock 影像归仓 NAS V1.0 · 构建2',NOTE,'任务 '+j['id'],'状态 '+j['status'],'来源 '+j['source'],'规则 '+json.dumps(j['options'],ensure_ascii=False),'错误 '+j.get('error','')]
        for r in records:lines+=['','源 '+r['source'],'实际读取 '+r.get('read_source',''),'目标 '+r['destination'],r.get('action','')+' · '+str(r['bytes'])+' bytes',r.get('algorithm','')+' '+str(r.get('checksum') or '未完成内容校验')]
        return ('\n'.join(lines)+'\n').encode(),'text/plain; charset=utf-8','txt'
    if kind=='log':
        lines=[json.dumps({'at':j['created'],'event':'task-start','source':j['source']},ensure_ascii=False)]+[json.dumps(e,ensure_ascii=False) for e in j.get('events',[])]+[json.dumps({'event':'file','source':r['source'],'read_source':r.get('read_source'),'destination':r['destination'],'action':r['action'],'checksum':r.get('checksum')},ensure_ascii=False) for r in records]+[json.dumps({'at':j.get('finished'),'event':'task-end','status':j['status'],'error':j.get('error')},ensure_ascii=False)]
        return ('\n'.join(lines)+'\n').encode(),'text/plain; charset=utf-8','transfer.log'
    if kind=='checksums':
        lines=[r['checksum']+'  '+r['destination'].replace('\n','\\n').replace('\r','\\r') for r in records if r.get('checksum') and r.get('action')!='skipped-conflict']
        return ('# '+NOTE+'\n'+'\n'.join(lines)+'\n').encode(),'text/plain; charset=utf-8','checksums.txt'
    if kind=='mhl':
        if j['status']!='completed' or j['options']['verify'] not in ('md5','xxh64'):raise ValueError('基础MHL 1.1仅适用于完整成功的MD5或XXHash64任务；其他算法请导出校验清单')
        iso=lambda ts:datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat()
        date=iso(j.get('finished',j['created']))
        root=ET.Element('hashlist',version='1.1');ET.SubElement(root,'creationdate').text=date
        creator=ET.SubElement(root,'creatorinfo')
        for tag,value in {'username':str(__import__('os').getuid()),'hostname':socket.gethostname(),'tool':'CardDock NAS','source':j['source'],'startdate':iso(j['created']),'finishdate':date}.items():ET.SubElement(creator,tag).text=value
        for r in records:
            if not r.get('checksum') or r.get('action')=='skipped-conflict':raise ValueError('存在未校验条目，不能生成MHL')
            entry=ET.SubElement(root,'hash');ET.SubElement(entry,'file').text=r['destination'];ET.SubElement(entry,'size').text=str(r['bytes']);ET.SubElement(entry,'lastmodificationdate').text=iso(r['mtime_ns']/1e9);ET.SubElement(entry,'md5' if r['algorithm']=='md5' else 'xxhash64be').text=r['checksum'];ET.SubElement(entry,'hashdate').text=date
        return ET.tostring(root,encoding='utf-8',xml_declaration=True),'application/xml; charset=utf-8','mhl'
    if kind=='html':
        esc=lambda x:html.escape(str(x))
        rows=''.join('<tr>'+''.join('<td>'+esc(r.get(k,''))+'</td>' for k in ('source','destination','bytes','action','algorithm','checksum'))+'</tr>' for r in records)
        body='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>影像归仓校验报告</title><style>body{font:14px sans-serif;margin:32px;color:#173c2d}table{border-collapse:collapse;width:100%;font-size:11px}td,th{border:1px solid #ccd8d0;padding:8px;overflow-wrap:anywhere}h1{font-size:24px}@media print{body{margin:0}tr{break-inside:avoid}thead{display:table-header-group}}</style><h1>影像归仓 · NAS 校验报告</h1><p>'+esc(NOTE)+'</p><p>任务 '+esc(j['id'])+' · '+esc(j['status'])+'</p><p>错误：'+esc(j.get('error',''))+'</p><p>浏览器“打印 → 存储为 PDF”可保存此报告。</p><table><thead><tr><th>来源</th><th>目标</th><th>字节</th><th>操作</th><th>算法</th><th>摘要</th></tr></thead><tbody>'+rows+'</tbody></table></html>'
        return body.encode(),'text/html; charset=utf-8','html'
    raise ValueError('未知报告格式')

def save_reports(j,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for kind in ['json','txt','checksums','html','log']+(['mhl'] if j['status']=='completed' and j['options']['verify'] in ('md5','xxh64') else []):
        body,_,ext=export(j,kind);path=directory/(j['id']+'.'+ext);temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(body);temp.replace(path)
