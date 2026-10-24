"Public regression tests for MS-URL-REWRITE-DEV; the complete business contract is in materials/MS-URL-REWRITE-DEV-contract.md."
import pytest
import mistune

def test_link_image_and_reference_links_use_explicit_kinds():
    calls=[]
    def rewrite(url,kind):
        calls.append((url,kind))
        return '/published/'+url
    md=mistune.create_markdown(renderer=mistune.HTMLRenderer(url_rewriter=rewrite))
    result=md('[text](page) ![alt](img.png) [ref][x]\n\n[x]: target')
    assert calls==[('page','link'),('img.png','image'),('target','link')]
    assert 'href="/published/page"' in result and 'alt="alt"' in result

def test_dangerous_rewritten_url_still_uses_original_protocol_policy():
    md=mistune.create_markdown(renderer=mistune.HTMLRenderer(url_rewriter=lambda url,kind:'javascript:alert(1)'))
    assert 'href="#harmful-link"' in md('[safe](page)')

def test_attribute_escaping_and_visible_markup_are_preserved():
    md=mistune.create_markdown(renderer=mistune.HTMLRenderer(url_rewriter=lambda url,kind:'a?x="&y=2'))
    result=md('[**bold**](page)')
    assert '<strong>bold</strong>' in result and '&quot;' in result and '&amp;' in result

def test_invalid_return_and_callback_errors_propagate():
    md=mistune.create_markdown(renderer=mistune.HTMLRenderer(url_rewriter=lambda url,kind:None))
    with pytest.raises(TypeError):
        md('[x](page)')
    with pytest.raises(TypeError):
        mistune.HTMLRenderer(url_rewriter=3)
