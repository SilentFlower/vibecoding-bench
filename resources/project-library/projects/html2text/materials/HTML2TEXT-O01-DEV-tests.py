"Public regression tests for HTML2TEXT-O01-DEV; the complete business contract is in materials/HTML2TEXT-O01-DEV-contract.md."
from html2text import HTML2Text
import re

def convert(text):
    "Support the public regression through convert."
    converter=HTML2Text(bodywidth=0);converter.adaptive_inline_code=True;return converter.handle(text).strip('\n')

def decode_span(text):
    "Support the public regression through decode_span."
    match=re.match(r'^(`+)(.*)\1$',text,re.S);assert match
    body=match.group(2)
    if body.startswith(' ') and body.endswith(' ') and body.strip(' '):body=body[1:-1]
    assert max((len(value) for value in re.findall(r'`+',body)),default=0)<len(match.group(1))
    return body

def test_backtick_runs_edges_entities_and_padding_roundtrip():
    "Verify backtick runs edges entities and padding roundtrip."
    for text in ['a`b','``edge`','a```b','`',' both ','   ','plain']:
        assert decode_span(convert('<code>'+text+'</code>'))==text
    assert decode_span(convert('<kbd>&lt;a&gt;&amp;`</kbd>'))=='<a>&`'

def test_nested_markup_multiple_spans_and_unclosed_eof_do_not_leak():
    "Verify nested markup multiple spans and unclosed eof do not leak."
    assert convert('<code>a<strong>b</strong>`c</code>')=='``ab`c``'
    assert convert('<tt>a`b</tt> next <kbd>plain</kbd>')=='``a`b`` next `plain`'
    converter=HTML2Text(bodywidth=0);converter.adaptive_inline_code=True
    assert converter.handle('<code>unfinished`').strip('\n')=='`` unfinished` ``'
    assert converter.handle('<p>next</p>').strip()=='next'

def test_default_and_pre_behavior_remain_existing_paths():
    "Verify default and pre behavior remain existing paths."
    assert HTML2Text(bodywidth=0).handle('<code>plain</code>').strip()=='`plain`'
    assert convert('<code></code>')==''
    assert '    a`b' in convert('<pre>a`b</pre>')
