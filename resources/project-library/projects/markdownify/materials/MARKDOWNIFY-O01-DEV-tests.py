"Public regression tests for MARKDOWNIFY-O01-DEV; the complete business contract is in materials/MARKDOWNIFY-O01-DEV-contract.md."
from markdownify import markdownify,MarkdownConverter
import pytest

def test_internal_backticks_cannot_close_outer_fence():
    "Verify internal backticks cannot close outer fence."
    text='first\n```python\ninside\n```\nlast'
    actual=markdownify('<pre>'+text+'</pre>',code_language='text')
    assert actual=='````text\n'+text+'\n````'
    for width in [1,2,4,8]:
        body='a\n'+'`'*width+'\nb'
        result=markdownify('<pre>'+body+'</pre>')
        assert result.splitlines()[0]=='`'*max(3,width+1)
        assert '\n'.join(result.splitlines()[1:-1])==body

def test_strip_modes_and_language_callback_are_kept():
    "Verify strip modes and language callback are kept."
    converter=MarkdownConverter(code_language='text',code_language_callback=lambda el:el.get('data-language'),strip_pre=None)
    assert converter.convert('<pre data-language="py">\n```\n</pre>')=='````py\n\n```\n\n````'
    assert markdownify('<pre>simple</pre>')=='```\nsimple\n```'

def test_invalid_information_line_is_rejected_not_injected():
    "Verify invalid information line is rejected not injected."
    for value in ['py\n# escaped','py\rplain','py`']:
        with pytest.raises(ValueError):markdownify('<pre>code</pre>',code_language=value)
    with pytest.raises(TypeError):markdownify('<pre>code</pre>',code_language_callback=lambda el:123)
