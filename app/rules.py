"""Shared NAS archive rules aligned with CardDock desktop build 21."""
import datetime, re
from pathlib import Path
RAW = set('arw cr2 cr3 crw nef nrw rw2 dng raf srw orf pef 3fr iiq'.split())
VIDEO = set('mp4 mov mxf mts m2ts avi crm r3d braw insv arx ari mkv nev'.split())
SIDECARS = set('xmp xml srt thm cpi mpl bim pp3 dop rmd'.split())
MEDIA = {'全景序列': set(), '延时摄影图片序列': set(), 'RAW': RAW, 'JPG': {'jpg','jpeg'}, '其他图片': set('png tif tiff heic hif heif webp avif insp'.split()), '视频': VIDEO, '声音': set('wav mp3 aac flac m4a aif aiff ogg'.split()), '视频代理': {'lrf','lrv'}}

def panorama(p):
    indices=[i for i,x in enumerate(p.parts[:-1]) if x.upper()=='PANORAMA']
    return Path('全景序列',*p.parts[indices[-1]+1:]) if indices else None

def timelapse(p):
    for x in list(p.parts[:-1])+[p.stem]:
        x=re.sub(r'[_\-\s]','',x.upper())
        if re.fullmatch(r'(HYPERLAPSE|TIMELAPSE|INTVL)(\d.*)?',x) or any(w in x for w in ('延时摄影','延時攝影','缩时摄影','縮時攝影')): return True
    return False

def proxy(p):
    return any(x.lower() in {'proxy','proxies','sub','subclip','lowres','视频代理'} for x in p.parts[:-1]) or bool(re.search(r'(_proxy|_px|_s03)$',p.stem,re.I))

def still(p):
    return next((k for k in ('RAW','JPG','其他图片') if p.suffix.lower()[1:] in MEDIA[k]),None)

def category(p):
    if panorama(p): return '全景序列'
    ext=p.suffix.lower()[1:]
    if ext in ('lrf','lrv') or ext in VIDEO and proxy(p): return '视频代理'
    fmt=still(p)
    if fmt: return '延时摄影图片序列' if timelapse(p) else fmt
    return next((k for k in ('视频','声音') if ext in MEDIA[k]),None)

def sony_thumbnail(p):
    return p.suffix.lower() in ('.jpg','.jpeg') and bool(re.search(r'(^|/)PRIVATE/M4ROOT/THMBNL/',p.as_posix(),re.I))

def protected(p):
    return bool(panorama(p)) or timelapse(p) or proxy(p) or p.suffix.lower() in ('.lrf','.lrv') or any(x.lower().endswith('.rdc') for x in p.parts[:-1])

def selected(p,c):
    cat=category(p)
    if sony_thumbnail(p): return False
    if c.get('media_only') and not cat: return False
    if c.get('exclude_proxies') and (cat=='视频代理' or p.suffix.lower()[1:] in SIDECARS and proxy(p)): return False
    exts={x.strip().lower().lstrip('.') for x in re.split(r'[,，\s]+',c.get('extensions','')) if x.strip()}
    if exts and p.suffix.lower()[1:] not in exts: return False
    date=datetime.datetime.fromtimestamp(p.stat().st_mtime).date().isoformat()
    if c.get('date_from') and date<c['date_from'] or c.get('date_to') and date>c['date_to']: return False
    return True

def component(s):
    if not isinstance(s,str) or s in ('.','..') or any(ch in s for ch in '/\\\0') or any(ord(ch)<32 for ch in s): raise ValueError('命名字段不能包含路径、控制符或 ..')
    return s.strip()

def folder(c,root,device='',at=None):
    template=c.get('directory_template','{source}')
    if not isinstance(template,str) or template.startswith('/') or '\\' in template: raise ValueError('目录模板无效，使用 / 分层')
    values={'date':(at or datetime.date.today()).strftime('%Y.%m.%d'),'project':c.get('project',''),'device':device,'camera':c.get('camera',''),'card':c.get('card',''),'source':root.name}
    for key in ('camera','card'):
        if not values[key]: template=template.replace(('机位' if key=='camera' else '卡号')+'{'+key+'}','')
    for key,value in values.items(): template=template.replace('{'+key+'}',component(value))
    if '\\' in template or '{' in template or '}' in template: raise ValueError('目录模板无效，使用 / 分层')
    parts=[component(x) for x in template.split('/') if x]
    if not parts or not any(parts): raise ValueError('归档目录不能为空')
    return Path(*[x for x in parts if x])

def layout(p,root,c,companions,sequence):
    rel=p.relative_to(root);cat=category(p);ext=p.suffix.lower()[1:]
    pano=panorama(p)
    if pano: return pano
    fmt=still(p) or companions.get(str(p.with_suffix('')).lower())
    if cat=='视频代理' or ext in SIDECARS and proxy(p): return Path('视频代理',p.name)
    if cat=='延时摄影图片序列' or ext in SIDECARS and timelapse(p):
        group=list(rel.parent.parts)
        if group and group[-1].upper() in ('RAW','JPG','JPEG'):group.pop()
        return Path('延时摄影图片序列',group[-1] if group else root.name,*([fmt] if fmt else []),p.name)
    if any(x.lower().endswith('.rdc') for x in p.parts[:-1]):return Path('视频',rel) if c.get('classify',True) else rel
    relative=rel if c.get('keep_parents') else Path(p.name)
    if fmt in ('RAW','JPG'): result=Path(fmt,relative)
    else:result=Path(cat or ('伴随文件' if ext in SIDECARS else '其他文件'),relative) if c.get('media_only') and c.get('classify',True) else rel if not c.get('media_only') else relative
    template=c.get('filename_template','')
    if template and not protected(p):
        name=template
        for key,value in {'original':p.stem,'sequence':str(sequence).zfill(4),'ext':p.suffix[1:]}.items():name=name.replace('{'+key+'}',value)
        if '{' in name or '}' in name:raise ValueError('文件名模板仅支持 original / sequence / ext')
        name=component(name)
        if not name:raise ValueError('文件名不能为空')
        if not name.lower().endswith(p.suffix.lower()):name+=p.suffix
        result=result.with_name(name)
    return result

def device_overview(info):
    return info.get('overview') or {'Sony':'索尼相机','Canon':'佳能相机','Nikon':'尼康相机','Panasonic':'松下相机','ARRI':'ARRI摄影机','DJI':'大疆设备（类型待确认）','GoPro':'GoPro运动相机','Insta360':'Insta360相机','Apple':'Apple手机'}.get(info.get('brand'),'')
