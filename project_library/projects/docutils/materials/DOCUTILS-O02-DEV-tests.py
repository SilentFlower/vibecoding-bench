"""显式分段列表经过真实RST解析并生成可发布的表格节点。"""
from docutils.core import publish_doctree,publish_parts
from docutils import nodes
import io

def settings():
    """隔离警告输出并阻止错误中止，允许检查真实system_message。@return 参数。"""
    return {'warning_stream':io.StringIO(),'halt_level':6,'report_level':5}

def test_real_table_headers_cells_inline_markup_and_title():
    """中文、标题、格式化单元格及HTML列关系都真实存在。@return None。"""
    source='.. segmented-list:: Product data\n   :columns: 名称 | 数量\n   :name: products\n\n   **苹果** | 2\n   Pear | 3\n'
    document=publish_doctree(source,settings_overrides=settings());table=next(document.findall(nodes.table))
    assert table['ids']==['products'] and next(table.findall(nodes.title)).astext()=='Product data'
    assert [entry.astext() for entry in table.findall(nodes.entry)]==['名称','数量','苹果','2','Pear','3']
    assert len(list(table.findall(nodes.strong)))==1
    html=publish_parts(source,writer='html5',settings_overrides=settings())['html_body'];assert '<table' in html and '苹果' in html and '<th' in html

def test_quoted_delimiter_empty_cells_and_original_plain_text_are_preserved():
    """CSV引号允许单元内竖线，空单元保留，普通冒号语句不被重解释。@return None。"""
    source='.. segmented-list::\n   :columns: Name | Value\n\n   "A|B"|\n\nordinary: text\n'
    document=publish_doctree(source,settings_overrides=settings());table=next(document.findall(nodes.table))
    assert [entry.astext() for entry in table.findall(nodes.entry)]==['Name','Value','A|B','']
    assert 'ordinary: text' in document.astext()

def test_missing_headers_bad_column_count_and_bad_quotes_are_real_diagnostics():
    """非法数据不生成貌似合法的半表格。@return None。"""
    for source in ['.. segmented-list::\n\n   A | B\n','.. segmented-list::\n   :columns: A | B\n\n   only-one\n','.. segmented-list::\n   :columns: A | B\n\n   "unclosed | B\n']:
        document=publish_doctree(source,settings_overrides=settings())
        assert list(document.findall(nodes.system_message)) and not list(document.findall(nodes.table))
