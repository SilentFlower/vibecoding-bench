"""书目差异比较忽略排版但不丢失真实字段变化。"""
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_field_order_not_change():
    """字段排列和类型大小写不构成语义变化。@return None。"""
    from bibtexparser.diff import diff_libraries
    one = Library([Entry('ARTICLE', 'x', [Field('title', 'A'), Field('year', '2026')])])
    two = Library([Entry('article', 'x', [Field('year', '2026'), Field('title', 'A')])])
    assert diff_libraries(one, two)['entries'] == {'added': [], 'removed': [], 'changed': []}

def test_changes_and_added_removed():
    """改字段、新增和删除分别定位。@return None。"""
    from bibtexparser.diff import diff_libraries
    one = Library([Entry('article', 'x', [Field('title', 'A')]), Entry('book', 'old', [])])
    two = Library([Entry('article', 'x', [Field('title', 'B')]), Entry('book', 'new', [])])
    result = diff_libraries(one, two)['entries']
    assert result['added'] == ['new'] and result['removed'] == ['old']
    assert result['changed'][0]['key'] == 'x'

def test_ignored_and_nonentry_blocks():
    """显式忽略字段仍比较宏与注释。@return None。"""
    from bibtexparser.diff import diff_libraries
    from bibtexparser.model import String, ExplicitComment
    one = Library([Entry('article', 'x', [Field('year', '1')]), String('m', 'one'), ExplicitComment('a')])
    two = Library([Entry('article', 'x', [Field('year', '2')]), String('m', 'two'), ExplicitComment('b')])
    result = diff_libraries(one, two, ignore_fields=['year'])
    assert result['entries']['changed'] == [] and result['strings'] is not None and result['comments'] is not None
