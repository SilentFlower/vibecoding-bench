"""观察固定5.2版的检测、流状态、重置和codec适配边界。"""
import codecs
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import chardet
from chardet import UniversalDetector, detect


def main() -> None:
    """所有输入是合成字节，不根据猜测修改任何源文件。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(chardet.__file__).resolve() == root / 'library/chardet/__init__.py'}
    task = argv[1]
    if task == 'CD-U01':
        raw = b'plain text'
        observed = detect(raw)
        result['ascii_confidence_does_not_identify_the_original_encoding'] = (
            observed['encoding'] == 'ascii' and observed['confidence'] == 1
            and raw.decode('ascii') == raw.decode('utf-8') == raw.decode('cp1252'))
    elif task == 'CD-U02':
        detector = UniversalDetector()
        prefix = codecs.BOM_UTF8 + b'hello'
        detector.feed(prefix)
        before = detector.result.copy()
        detector.feed(b'\xff')
        invalid = False
        try:
            (prefix + b'\xff').decode('utf-8-sig', errors='strict')
        except UnicodeDecodeError:
            invalid = True
        result['early_detector_done_does_not_validate_the_complete_byte_stream'] = (
            detector.done and detector.close() == before
            and before['encoding'] == 'UTF-8-SIG' and invalid)
    elif task == 'CD-C01':
        detector = UniversalDetector()
        detector.feed(codecs.BOM_UTF8 + b'hello')
        first = detector.close().copy()
        detector.feed(b'plain text')
        reused = detector.close().copy()
        detector.reset()
        detector.feed(b'plain text')
        reset = detector.close()
        result['detector_reuse_requires_reset_between_independent_documents'] = (
            first == reused and first['encoding'] == 'UTF-8-SIG' and reset['encoding'] == 'ascii')
    elif task == 'CD-C02':
        observed = detect(b'\xfe\xff\x00\x00')
        unavailable = False
        try:
            codecs.lookup(observed['encoding'])
        except LookupError:
            unavailable = True
        result['a_detected_encoding_label_may_not_name_a_python_codec'] = (
            observed['encoding'] == 'X-ISO-10646-UCS-4-3412' and unavailable)
    elif task == 'CD-P01':
        raw = b'Caf\xe9'
        result['identical_decodings_can_leave_source_encoding_ambiguous'] = (
            raw.decode('latin-1') == raw.decode('cp1252') == 'Café'
            and raw.decode('latin-1').encode('latin-1') == raw
            and raw.decode('cp1252').encode('cp1252') == raw)
    elif task == 'CD-D01':
        raw = codecs.BOM_UTF8 + 'Hello café'.encode()
        whole = detect(raw)
        detector = UniversalDetector()
        for byte in raw:
            detector.feed(bytes([byte]))
        result.update(whole=whole, one_byte_chunks=detector.close())
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
