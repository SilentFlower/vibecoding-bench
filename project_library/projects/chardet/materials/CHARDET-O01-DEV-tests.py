"""任意初始分块必须与整份BOM识别一致。"""
import codecs
from chardet import UniversalDetector, detect

def test_utf_boms_one_byte_chunks():
    """UTF8/16/32的一字节feed保留完整BOM身份。@return None。"""
    samples = [codecs.BOM_UTF8 + '中文'.encode('utf-8'), codecs.BOM_UTF16_LE + 'ab'.encode('utf-16-le'), codecs.BOM_UTF16_BE + 'ab'.encode('utf-16-be'), codecs.BOM_UTF32_LE + 'ab'.encode('utf-32-le'), codecs.BOM_UTF32_BE + 'ab'.encode('utf-32-be')]
    for sample in samples:
        detector = UniversalDetector()
        for value in sample:
            detector.feed(bytes([value]))
        assert detector.close()['encoding'] == detect(sample)['encoding']

def test_prefix_close_and_reset():
    """不完整BOM在close时也需进入原检测，reset不残留。@return None。"""
    detector = UniversalDetector()
    detector.feed(b'\xef')
    assert detector.close()['encoding'] is not None
    detector.reset()
    detector.feed(b'ordinary ascii')
    assert detector.close()['encoding'] == 'ascii'

def test_near_prefix_and_empty_chunks():
    """相似但不匹配前缀不能丢字节。@return None。"""
    sample = b'\xef\xbbX plain text'
    detector = UniversalDetector()
    for part in (b'', sample[:1], b'', sample[1:2], sample[2:]): detector.feed(part)
    assert detector.close() == detect(sample)
