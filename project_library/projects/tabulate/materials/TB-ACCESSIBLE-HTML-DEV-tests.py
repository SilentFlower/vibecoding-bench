"""公开可访问安全HTML报表回归。"""
import pytest
from html.parser import HTMLParser
from tabulate.accessibility import accessible_html

def test_caption_and_column_header_scopes_are_real_elements():
    result=accessible_html([['a',1]],headers=['name','value'],caption='Orders')
    assert '<caption>Orders</caption>' in result and result.count('scope="col"')==2

def test_body_row_header_conversion_preserves_other_cells():
    result=accessible_html([['a',1],['b',2]],headers=['name','value'],row_headers=True)
    assert result.count('scope="row"')==2 and result.count('<td')==2

def test_caption_id_and_data_are_safely_escaped():
    result=accessible_html([['<script>bad</script>']],headers=['x'],caption='<b>caption</b>',table_id='x"onclick="bad')
    assert '<script>' not in result and '<b>caption' not in result and '&quot;' in result and '&lt;script&gt;' in result

def test_unsafe_output_override_and_bad_metadata_fail():
    with pytest.raises(ValueError):
        accessible_html([[1]],tablefmt='unsafehtml')
    with pytest.raises(ValueError):
        accessible_html([[1]],table_id='bad id')
