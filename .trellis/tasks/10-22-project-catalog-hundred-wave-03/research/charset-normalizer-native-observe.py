"""核原字节、候选归属、编码转换及失败后的真实日志状态。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import charset_normalizer
from charset_normalizer import from_bytes
from charset_normalizer.api import explain_handler, logger


def main() -> None:
    """只处理合成字节；日志故障观察在本进程内完整恢复。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(charset_normalizer.__file__).resolve()
        == root / 'library/src/charset_normalizer/__init__.py'}
    task = argv[1]
    if task == 'CN-U01':
        text = 'Café €'
        raw = b'\xef\xbb\xbf' + text.encode('utf_8')
        match = from_bytes(raw).best()
        longer = 'The café serves tea every morning. Prices are shown in euros: €5. ' * 6
        longer_raw = b'\xef\xbb\xbf' + longer.encode('utf_8')
        control = from_bytes(longer_raw).best()
        result['bom_hint_does_not_override_the_full_detection_policy'] = (
            match is not None and match.encoding == 'shift_jis_2004' and not match.bom
            and str(match) != text and match.raw == raw and raw.decode('utf-8-sig') == text
            and control is not None and control.bom and control.encoding == 'utf_8'
            and control.raw == longer_raw and str(control) == longer
            and control.output() == longer.encode('utf_8'))
    elif task == 'CN-U02':
        text = 'café café café'
        matches = from_bytes(text.encode('cp1252'), cp_isolation=['cp1252', 'latin_1'])
        match = matches.best()
        result['equivalent_decodings_are_grouped_without_proving_the_origin'] = (
            len(matches) == 1 and match is not None and str(match) == text and match.has_submatch
            and set(match.could_be_from_charset) == {'cp1252', 'latin_1'})
    elif task == 'CN-C01':
        raw = 'café'.encode('cp1252')
        restricted = from_bytes(raw, cp_isolation=['utf_8'])
        known = from_bytes(raw, cp_isolation=['cp1252']).best()
        result['restricted_no_match_does_not_prove_binary_input'] = (
            not restricted and restricted.best() is None and known is not None
            and str(known) == raw.decode('cp1252') == 'café')
    elif task == 'CN-C02':
        text = 'Café — €'
        match = from_bytes(text.encode('utf_8'), cp_isolation=['utf_8']).best()
        strict_failed = False
        try:
            text.encode('ascii', 'strict')
        except UnicodeEncodeError:
            strict_failed = True
        result['output_reencoding_replaces_unrepresentable_characters'] = (
            match is not None and str(match) == text and match.output('ascii') == b'Caf? ? ?' and strict_failed)
    elif task == 'CN-P01':
        text = '<?xml version="1.0" encoding="windows-1252"?><note>café</note>'
        raw = text.encode('cp1252')
        match = from_bytes(raw, cp_isolation=['cp1252']).best()
        result['normalized_output_rewrites_the_declared_encoding_without_replacing_raw'] = (
            match is not None and match.raw == raw and str(match) == text
            and match.output().decode('utf_8') == text.replace('windows-1252', 'utf-8')
            and match.output() != raw)
    elif task == 'CN-D01':
        previous_level, previous_handlers = logger.level, list(logger.handlers)
        failure = None
        try:
            try:
                from_bytes(b'hello', steps=0, explain=True)
            except ZeroDivisionError as error:
                failure = type(error).__name__
            result.update(error=failure, before_level=previous_level, after_level=logger.level,
                explain_handler_added=explain_handler not in previous_handlers and explain_handler in logger.handlers,
                original_handlers_retained=all(handler in logger.handlers for handler in previous_handlers))
        finally:
            # 只移除本次加上的上游诊断handler；不删除原有配置或把私有观察当公共API。
            if explain_handler not in previous_handlers and explain_handler in logger.handlers:
                logger.removeHandler(explain_handler)
            logger.setLevel(previous_level)
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
