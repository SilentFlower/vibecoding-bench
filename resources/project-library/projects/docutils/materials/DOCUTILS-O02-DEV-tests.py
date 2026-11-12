"Public regression tests for DOCUTILS-O02-DEV; the complete business contract is in materials/DOCUTILS-O02-DEV-contract.md."
from docutils.core import publish_doctree,publish_parts
from docutils import nodes
import io

def settings():
    "Support the public regression through settings."
    return {'warning_stream':io.StringIO(),'halt_level':6,'report_level':5}

def test_real_table_headers_cells_inline_markup_and_title():
    "Verify real table headers cells inline markup and title."
    source='.. segmented-list:: Product data\n   :columns: 名称 | 数量\n   :name: products\n\n   **苹果** | 2\n   Pear | 3\n'
    document=publish_doctree(source,settings_overrides=settings());table=next(document.findall(nodes.table))
    assert table['ids']==['products'] and next(table.findall(nodes.title)).astext()=='Product data'
    assert [entry.astext() for entry in table.findall(nodes.entry)]==['名称','数量','苹果','2','Pear','3']
    assert len(list(table.findall(nodes.strong)))==1
    html=publish_parts(source,writer='html5',settings_overrides=settings())['html_body'];assert '<table' in html and '苹果' in html and '<th' in html

def test_quoted_delimiter_empty_cells_and_original_plain_text_are_preserved():
    "Verify quoted delimiter empty cells and original plain text are preserved."
    source='.. segmented-list::\n   :columns: Name | Value\n\n   "A|B"|\n\nordinary: text\n'
    document=publish_doctree(source,settings_overrides=settings());table=next(document.findall(nodes.table))
    assert [entry.astext() for entry in table.findall(nodes.entry)]==['Name','Value','A|B','']
    assert 'ordinary: text' in document.astext()

def test_missing_headers_bad_column_count_and_bad_quotes_are_real_diagnostics():
    "Verify missing headers bad column count and bad quotes are real diagnostics."
    for source in ['.. segmented-list::\n\n   A | B\n','.. segmented-list::\n   :columns: A | B\n\n   only-one\n','.. segmented-list::\n   :columns: A | B\n\n   "unclosed | B\n']:
        document=publish_doctree(source,settings_overrides=settings())
        assert list(document.findall(nodes.system_message)) and not list(document.findall(nodes.table))
