"""Bounded EXIF Make/Model reader for JPEG and classic TIFF-based still formats."""
import struct

def camera_tags(path):
    with open(path,'rb') as f:data=f.read(1024*1024)
    if data.startswith(b'\xff\xd8'):
        pos=2;tiff=None
        while pos+4<=len(data):
            if data[pos]!=255:break
            marker=data[pos+1];pos+=2
            if marker in (0xda,0xd9):break
            length=int.from_bytes(data[pos:pos+2],'big')
            if length<2 or pos+length>len(data):break
            segment=data[pos+2:pos+length]
            if marker==0xe1 and segment.startswith(b'Exif\0\0'):tiff=segment[6:];break
            pos+=length
        if tiff is None:return {}
        data=tiff
    if len(data)<8 or data[:2] not in (b'II',b'MM'):return {}
    endian='<' if data[:2]==b'II' else '>'
    def num(offset,fmt):
        size=struct.calcsize(fmt)
        if offset<0 or offset+size>len(data):raise ValueError('truncated EXIF')
        return struct.unpack_from(endian+fmt,data,offset)[0]
    if num(2,'H')!=42:return {}
    offset=num(4,'I');count=min(num(offset,'H'),1024);result={}
    for i in range(count):
        p=offset+2+i*12;tag=num(p,'H');kind=num(p+2,'H');length=num(p+4,'I')
        if tag not in (0x10f,0x110) or kind!=2 or length<1 or length>1024:continue
        start=p+8 if length<=4 else num(p+8,'I')
        if start+length>len(data):continue
        result['Make' if tag==0x10f else 'Model']=data[start:start+length].split(b'\0',1)[0].decode('utf-8','replace').strip()
    return result
