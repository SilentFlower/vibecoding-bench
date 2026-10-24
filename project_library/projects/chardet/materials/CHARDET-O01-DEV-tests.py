"Public regression tests for CHARDET-O01-DEV; the complete business contract is in materials/CHARDET-O01-DEV-contract.md."
import codecs
from chardet import UniversalDetector, detect

def test_utf_boms_one_byte_chunks():
    "Verify utf boms one byte chunks."
    samples = [codecs.BOM_UTF8 + '中文'.encode('utf-8'), codecs.BOM_UTF16_LE + 'ab'.encode('utf-16-le'), codecs.BOM_UTF16_BE + 'ab'.encode('utf-16-be'), codecs.BOM_UTF32_LE + 'ab'.encode('utf-32-le'), codecs.BOM_UTF32_BE + 'ab'.encode('utf-32-be')]
    for sample in samples:
        detector = UniversalDetector()
        for value in sample:
            detector.feed(bytes([value]))
        assert detector.close()['encoding'] == detect(sample)['encoding']

def test_prefix_close_and_reset():
    "Verify prefix close and reset."
    detector = UniversalDetector()
    detector.feed(b'\xef')
    assert detector.close()['encoding'] is not None
    detector.reset()
    detector.feed(b'ordinary ascii')
    assert detector.close()['encoding'] == 'ascii'

def test_near_prefix_and_empty_chunks():
    "Verify near prefix and empty chunks."
    sample = b'\xef\xbbX plain text'
    detector = UniversalDetector()
    for part in (b'', sample[:1], b'', sample[1:2], sample[2:]): detector.feed(part)
    assert detector.close() == detect(sample)
