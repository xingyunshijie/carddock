import tempfile,sys,struct,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from metadata import camera_tags
from core import detect

def tiff(make,model):
    values=[make.encode()+b'\0',model.encode()+b'\0'];offset=8+2+2*12+4
    entries=[];tail=b''
    for tag,value in zip([0x10f,0x110],values):
        ref=value.ljust(4,b'\0') if len(value)<=4 else struct.pack('<I',offset+len(tail))
        entries.append(struct.pack('<HHI',tag,2,len(value))+ref)
        if len(value)>4:tail+=value
    return b'II'+struct.pack('<HI',42,8)+struct.pack('<H',2)+b''.join(entries)+b'\0'*4+tail

class MetadataTests(unittest.TestCase):
    def test_tiff_jpeg_mixed_and_dji_model(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/'DJI_0001.DNG';raw.write_bytes(tiff('DJI','FC9287'))
            sony=root/'photo.JPG';data=b'Exif\0\0'+tiff('Sony','ILCE-7RM5');sony.write_bytes(b'\xff\xd8\xff\xe1'+struct.pack('>H',len(data)+2)+data+b'\xff\xd9')
            self.assertEqual(camera_tags(raw)['Model'],'FC9287');self.assertEqual(camera_tags(sony)['Make'],'Sony')
            with patch('core.subprocess.check_output',side_effect=FileNotFoundError):info=detect(root)
            self.assertIn('大疆航拍相机',info['overview']);self.assertIn('索尼相机',info['overview']);self.assertNotIn('FC9287',info['overview'])
            self.assertFalse(info['inferred'])
    def test_truncated_and_generic_dji_no_flight_guess(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'DJI_0001.JPG';p.write_bytes(b'bad')
            self.assertEqual(camera_tags(p),{})
            with patch('core.subprocess.check_output',side_effect=FileNotFoundError):info=detect(Path(d))
            self.assertIn('类型待确认',info['overview']);self.assertTrue(info['inferred'])

if __name__=='__main__':unittest.main()
