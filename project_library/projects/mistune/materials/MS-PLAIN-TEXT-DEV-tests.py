"""公开原生纯文本渲染回归。"""
import mistune
from mistune.renderers.text import PlainTextRenderer

def test_inline_formatting_code_and_entities_keep_visible_text():
    md=mistune.create_markdown(renderer=PlainTextRenderer())
    result=md('**bold** and *em* with `a < b` &amp; text')
    assert result=='bold and em with a < b & text\n' and '<strong>' not in result

def test_lists_and_paragraphs_keep_structural_boundaries():
    md=mistune.create_markdown(renderer=PlainTextRenderer())
    result=md('# Title\n\nfirst\n\n3. one\n4. two\n')
    assert 'Title\n\nfirst' in result and '3. one\n4. two' in result

def test_optional_urls_and_image_alt_are_visible_without_html():
    md=mistune.create_markdown(renderer=PlainTextRenderer(include_urls=True))
    result=md('[site](https://example.invalid) ![alt](image.png)')
    assert result=='site <https://example.invalid> alt <image.png>\n'

def test_raw_html_empty_documents_and_plugin_tables_are_supported():
    md=mistune.create_markdown(renderer=PlainTextRenderer(),plugins=['table'])
    assert md('')=='' and md('before <b>inside</b> after')=='before inside after\n'
    assert 'a\tb' in md('|a|b|\n|-|-|\n|1|2|')
