"""独立核对页码中间件的实际行为，首尾空白不作为未公布的拒绝条件。"""
import json
import os
from pathlib import Path

import bibtexparser
from bibtexparser import Library, parse_string
from bibtexparser.middlewares.middleware import BlockMiddleware
from bibtexparser.model import Entry, Field


def _source(pages: str) -> Library:
    """创建每项检查独立使用的真实输入。:param pages: 原页码文本。:return: 含其它字段的文献库。"""
    return Library([Entry('article', 'sample', [Field('pages', pages), Field('year', '2026'), Field('title', 'a-b')])])


def _ranges(normalize) -> bool:
    """核对数字原文与真实双连字符归一。:param normalize: 候选中间件类型。:return: 是否完成明确范围转换。"""
    for original, expected in ((' 001 - 009 ', '001--009'), ('1—3', '1--3'), ('12-19, 23–24', '12--19, 23--24')):
        actual = normalize().transform(_source(original)).entries[0]['pages']
        # 合同没有规定首尾空白；比较时容忍它，但数字和区间分隔符必须正确。
        if not isinstance(actual, str) or actual.strip() != expected:
            return False
    return True


def _unknown(normalize) -> bool:
    """核对不应猜测修复的格式整体保持。:param normalize: 候选中间件类型。:return: 是否保持未知格式。"""
    return all(normalize().transform(_source(pages)).entries[0]['pages'] == pages
        for pages in ('e123', '5', 'iv-v', '9-2', '', '12.5-13.5', '1-3,unknown'))


def _original(normalize) -> bool:
    """核对首次原值不会丢失或被后续变换覆盖。:param normalize: 候选中间件类型。:return: 是否保留来源。"""
    source = _source(' 001 - 009 ')
    output = normalize().transform(source)
    if output.entries[0].parser_metadata.get('original_pages') != ' 001 - 009 ':
        return False
    source = _source('1—3')
    source.entries[0].parser_metadata['original_pages'] = 'first original'
    return normalize().transform(source).entries[0].parser_metadata.get('original_pages') == 'first original'


def _immutable(normalize) -> bool:
    """核对默认变换保留原库与原元数据。:param normalize: 候选中间件类型。:return: 是否没有修改输入。"""
    source = _source('1—3')
    output = normalize().transform(source)
    return (output is not source and source.entries[0]['pages'] == '1—3'
        and source.entries[0].parser_metadata == {})


def _fields(normalize) -> bool:
    """核对页码之外的数据仍保留。:param normalize: 候选中间件类型。:return: 是否保持其它字段与身份。"""
    entry = normalize().transform(_source('1—3')).entries[0]
    return entry['year'] == '2026' and entry['title'] == 'a-b' and entry.key == 'sample' and entry.entry_type == 'article'


def _idempotent(normalize) -> bool:
    """核对重复处理保留已归一页码及首次原值。:param normalize: 候选中间件类型。:return: 是否幂等。"""
    first = normalize().transform(_source('1—3'))
    second = normalize().transform(first)
    return (second.entries[0]['pages'] == first.entries[0]['pages']
        and second.entries[0].parser_metadata.get('original_pages') == '1—3')


def main() -> None:
    """执行公开合同矩阵并输出有界诊断，不输出异常正文。:return: None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    checks = dict.fromkeys(('pages_api', 'pages_ranges', 'pages_unknown', 'pages_original',
        'pages_immutable', 'pages_fields', 'pages_idempotent', 'pages_default_stack'), False)
    try:
        from bibtexparser.pages import NormalizePages
        checks['pages_api'] = isinstance(NormalizePages, type) and issubclass(NormalizePages, BlockMiddleware)
    except ImportError:
        NormalizePages = None
    if checks['pages_api']:
        cases = (
            ('pages_ranges', lambda: _ranges(NormalizePages)),
            ('pages_unknown', lambda: _unknown(NormalizePages)),
            ('pages_original', lambda: _original(NormalizePages)),
            ('pages_immutable', lambda: _immutable(NormalizePages)),
            ('pages_fields', lambda: _fields(NormalizePages)),
            ('pages_idempotent', lambda: _idempotent(NormalizePages)),
            ('pages_default_stack', lambda: parse_string('@article{x,pages={1-3}}').entries[0]['pages'] == '1-3'),
        )
        for code, check in cases:
            try:
                checks[code] = bool(check())
            except Exception:
                pass
    print(json.dumps({'candidate_import': Path(bibtexparser.__file__).resolve().is_relative_to(root / 'library'),
        'business': all(checks.values()), 'feedback_codes': [code for code, passed in checks.items() if not passed]}))


if __name__ == '__main__':
    main()
