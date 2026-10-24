"""页码中间件不影响标题或电子页码。"""
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_numeric_ranges():
    """普通连字符和Unicode范围归一。@return None。"""
    from bibtexparser.pages import NormalizePages
    source = Library([Entry('article', 'x', [Field('pages', '12-19, 23–24'), Field('title', 'a-b')])])
    result = NormalizePages().transform(source)
    assert result.entries[0]['pages'] == '12--19, 23--24'
    assert result.entries[0]['title'] == 'a-b' and source.entries[0]['pages'] == '12-19, 23–24'

def test_unknown_and_descending_preserved():
    """电子页、罗马页和倒序不猜测修复。@return None。"""
    from bibtexparser.pages import NormalizePages
    for pages in ('e123', 'iv-v', '9-2', '', '12.5-13.5'):
        assert NormalizePages().transform(Library([Entry('article', 'x', [Field('pages', pages)])])).entries[0]['pages'] == pages

def test_idempotent_and_original():
    """重复规范不改变首次原始页码记录。@return None。"""
    from bibtexparser.pages import NormalizePages
    result = NormalizePages().transform(Library([Entry('article', 'x', [Field('pages', '1—3')])]))
    again = NormalizePages().transform(result)
    assert again.entries[0]['pages'] == '1--3'
    assert again.entries[0].parser_metadata['original_pages'] == '1—3'
