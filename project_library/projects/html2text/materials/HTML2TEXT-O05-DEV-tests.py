"""可见正文是明确DOM视图选择，不把CSS或脚本行为猜成安全过滤。"""
from html2text import HTML2Text

def test_hidden_boolean_template_and_descendants_are_really_removed():
    """hidden=false仍是HTML布尔隐藏，后代链接/图片/强调也不输出。@return None。"""
    converter=HTML2Text(bodywidth=0);converter.visible_content=True
    html='<p>visible</p><div hidden="false"><a href="https://secret">secret</a><img src="secret"><strong>secret</strong></div><template><p>placeholder</p></template><p>after</p>'
    actual=converter.handle(html)
    assert actual.strip()=='visible\n\nafter' and 'secret' not in actual and 'placeholder' not in actual
    assert converter.hidden_regions==2

def test_nested_void_and_mismatched_hidden_tags_do_not_leak_quiet_state():
    """隐藏void只略去本节点，嵌套/未配对标签按栈恢复且不污染quiet。@return None。"""
    converter=HTML2Text(bodywidth=0);converter.visible_content=True
    html='<p>A</p><img hidden src="x"><p>B</p><section hidden><div><script>secret</script></section><p>C</p>'
    actual=converter.handle(html)
    assert actual.strip()=='A\n\nB\n\nC' and converter.quiet==0 and converter.hidden_regions==2

def test_default_unclosed_eof_next_document_and_no_css_guessing():
    """默认保留旧内容，EOF清理后下一文档正常，CSS不在承诺内。@return None。"""
    converter=HTML2Text(bodywidth=0);converter.visible_content=True
    assert converter.handle('<p>before</p><div hidden>unclosed').strip()=='before'
    assert converter.handle('<p style="display:none">css text</p>').strip()=='css text' and converter.hidden_regions==0
    assert 'secret' in HTML2Text(bodywidth=0).handle('<div hidden>secret</div>')

def test_hidden_filter_precedes_callbacks_and_any_delivered_inline_buffer():
    """隐藏子树必须先过滤，已交付的动态代码缓冲不能重新收集隐藏正文。@return None。"""
    converter=HTML2Text(bodywidth=0);converter.visible_content=True;seen=[]
    converter.tag_callback=lambda owner,tag,attrs,start:seen.append((tag,start))
    if hasattr(converter,'adaptive_inline_code'):converter.adaptive_inline_code=True
    actual=converter.handle('<code>A<span hidden>secret<strong>nested</strong></span>B</code>')
    assert actual.strip()=='`AB`' and converter.hidden_regions==1
    assert not any(tag in ('span','strong') for tag,start in seen)
