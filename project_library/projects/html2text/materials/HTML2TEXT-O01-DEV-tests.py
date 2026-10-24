"""显式动态行内代码模式产生可还原的真实代码跨度。"""
from html2text import HTML2Text
import re

def convert(text):
    """通过真实handle入口启用自适应代码。@return Markdown。"""
    converter=HTML2Text(bodywidth=0);converter.adaptive_inline_code=True;return converter.handle(text).strip('\n')

def decode_span(text):
    """独立按CommonMark围栏宽度及padding规则还原跨度。@return 代码正文。"""
    match=re.match(r'^(`+)(.*)\1$',text,re.S);assert match
    body=match.group(2)
    if body.startswith(' ') and body.endswith(' ') and body.strip(' '):body=body[1:-1]
    assert max((len(value) for value in re.findall(r'`+',body)),default=0)<len(match.group(1))
    return body

def test_backtick_runs_edges_entities_and_padding_roundtrip():
    """不是只检查反引号个数，独立解码后原文完整。@return None。"""
    for text in ['a`b','``edge`','a```b','`',' both ','   ','plain']:
        assert decode_span(convert('<code>'+text+'</code>'))==text
    assert decode_span(convert('<kbd>&lt;a&gt;&amp;`</kbd>'))=='<a>&`'

def test_nested_markup_multiple_spans_and_unclosed_eof_do_not_leak():
    """嵌套标签只贡献正文，连续及EOF未闭合代码各自正确收口。@return None。"""
    assert convert('<code>a<strong>b</strong>`c</code>')=='``ab`c``'
    assert convert('<tt>a`b</tt> next <kbd>plain</kbd>')=='``a`b`` next `plain`'
    converter=HTML2Text(bodywidth=0);converter.adaptive_inline_code=True
    assert converter.handle('<code>unfinished`').strip('\n')=='`` unfinished` ``'
    assert converter.handle('<p>next</p>').strip()=='next'

def test_default_and_pre_behavior_remain_existing_paths():
    """默认简单代码和pre路径保持，空代码不伪造不可解析空跨度。@return None。"""
    assert HTML2Text(bodywidth=0).handle('<code>plain</code>').strip()=='`plain`'
    assert convert('<code></code>')==''
    assert '    a`b' in convert('<pre>a`b</pre>')
