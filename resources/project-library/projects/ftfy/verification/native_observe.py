"""核文字修整、解释重放、实体范围和配置一致性修复。"""
import json
import os
from io import BytesIO, StringIO
from pathlib import Path
import sys

import ftfy
from ftfy import TextFixerConfig, apply_plan, fix_and_explain, fix_file, fix_text, fix_text_segment


def main() -> None:
    """核固定源码，修改路径以独立字面期望和兼容控制约束。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(ftfy.__file__).resolve() == root / 'library/ftfy/__init__.py'}
    task = sys.argv[1]
    if task == 'FT-U01':
        source = 'FranÃ§ais &amp; 中文\r\nＨｅｌｌｏ ﬁle'
        explained = fix_and_explain(source)
        result['explanation_replays_the_observed_conversion_without_recovering_original_bytes'] = (
            explained.text == 'Français & 中文\nHello file' and explained.explanation
            and apply_plan(source, explained.explanation) == explained.text
            and fix_text('正常中文') == '正常中文')
    elif task == 'FT-U02':
        source = 'plain &amp;\n<b>HTML</b>\nafter &amp;'
        result['automatic_entity_scope_depends_on_segmentation_and_explicit_policy'] = (
            fix_text(source) == 'plain &\n<b>HTML</b>\nafter &amp;'
            and fix_and_explain(source).text == source
            and fix_text(source, unescape_html=True) == 'plain &\n<b>HTML</b>\nafter &')
    elif task == 'FT-C01':
        result['compatibility_normalization_can_change_a_scientific_exponent'] = (
            fix_text('10³', normalization='NFC') == '10³'
            and fix_text('10³', normalization='NFKC') == '103')
    elif task == 'FT-C02':
        rejected = False
        try:
            fix_text(b'caf\xc3\xa9')
        except UnicodeError:
            rejected = True
        result['unicode_fixing_requires_an_explicit_bytes_decoding_boundary'] = (
            rejected and fix_text(b'caf\xc3\xa9'.decode('utf-8')) == 'café')
    elif task == 'FT-P01':
        source = '第一行\n第二行\n'
        payload = source.encode('utf-16')
        rejected = False
        try:
            list(fix_file(BytesIO(payload), encoding='utf-16'))
        except UnicodeDecodeError:
            rejected = True
        result['byte_line_iteration_precedes_multibyte_decoding_and_text_stream_control_succeeds'] = (
            rejected and list(fix_file(StringIO(payload.decode('utf-16')))) == ['第一行\n', '第二行\n'])
    elif task == 'FT-M01':
        cases = [('中文 cafÃ©', {'decode_inconsistent_utf8': False}, '中文 cafÃ©'),
            ('voilÃ le travail', {'decode_inconsistent_utf8': False, 'restore_byte_a0': False}, 'voilÃ le travail'),
            ('schÃ¶n', {'fix_encoding': False}, 'schÃ¶n'), ('schÃ¶n', {}, 'schön')]
        checks = []
        for source, options, expected in cases:
            explained = fix_and_explain(source, TextFixerConfig(**options, explain=True))
            silent_config = TextFixerConfig(**options, explain=False)
            silent = fix_and_explain(source, silent_config)
            checks.append(explained.text == silent.text == expected and silent.explanation is None
                and isinstance(explained.explanation, list)
                and apply_plan(source, explained.explanation) == expected
                and fix_text(source, silent_config) == expected
                and fix_text_segment(source, silent_config) == expected)
        result['disabling_explanations_preserves_all_supplied_encoding_options_and_wrapper_controls'] = (
            all(checks) and fix_and_explain('中文 cafÃ©', explain=False, decode_inconsistent_utf8=False).text == '中文 cafÃ©')
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
