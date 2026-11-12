"Public regression tests for HTML2TEXT-O05-DEV; the complete business contract is in materials/HTML2TEXT-O05-DEV-contract.md."
from html2text import HTML2Text

def test_hidden_boolean_template_and_descendants_are_really_removed():
    "Verify hidden boolean template and descendants are really removed."
    converter=HTML2Text(bodywidth=0);converter.visible_content=True
    html='<p>visible</p><div hidden="false"><a href="https://secret">secret</a><img src="secret"><strong>secret</strong></div><template><p>placeholder</p></template><p>after</p>'
    actual=converter.handle(html)
    assert actual.strip()=='visible\n\nafter' and 'secret' not in actual and 'placeholder' not in actual
    assert converter.hidden_regions==2

def test_nested_void_and_mismatched_hidden_tags_do_not_leak_quiet_state():
    "Verify nested void and mismatched hidden tags do not leak quiet state."
    converter=HTML2Text(bodywidth=0);converter.visible_content=True
    html='<p>A</p><img hidden src="x"><p>B</p><section hidden><div><script>secret</script></section><p>C</p>'
    actual=converter.handle(html)
    assert actual.strip()=='A\n\nB\n\nC' and converter.quiet==0 and converter.hidden_regions==2

def test_default_unclosed_eof_next_document_and_no_css_guessing():
    "Verify default unclosed eof next document and no css guessing."
    converter=HTML2Text(bodywidth=0);converter.visible_content=True
    assert converter.handle('<p>before</p><div hidden>unclosed').strip()=='before'
    assert converter.handle('<p style="display:none">css text</p>').strip()=='css text' and converter.hidden_regions==0
    assert 'secret' in HTML2Text(bodywidth=0).handle('<div hidden>secret</div>')

def test_hidden_filter_precedes_callbacks_and_any_delivered_inline_buffer():
    "Verify hidden filter precedes callbacks and any delivered inline buffer."
    converter=HTML2Text(bodywidth=0);converter.visible_content=True;seen=[]
    converter.tag_callback=lambda owner,tag,attrs,start:seen.append((tag,start))
    if hasattr(converter,'adaptive_inline_code'):converter.adaptive_inline_code=True
    actual=converter.handle('<code>A<span hidden>secret<strong>nested</strong></span>B</code>')
    assert actual.strip()=='`AB`' and converter.hidden_regions==1
    assert not any(tag in ('span','strong') for tag,start in seen)
