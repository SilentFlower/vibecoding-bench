"""代码块必须在真实Markdown围栏语法下完整容纳正文。"""
from markdownify import markdownify,MarkdownConverter
import pytest

def test_internal_backticks_cannot_close_outer_fence():
    """围栏比正文最长连续反引号更长，三行内部块仍完整。@return None。"""
    text='first\n```python\ninside\n```\nlast'
    actual=markdownify('<pre>'+text+'</pre>',code_language='text')
    assert actual=='````text\n'+text+'\n````'
    for width in [1,2,4,8]:
        body='a\n'+'`'*width+'\nb'
        result=markdownify('<pre>'+body+'</pre>')
        assert result.splitlines()[0]=='`'*max(3,width+1)
        assert '\n'.join(result.splitlines()[1:-1])==body

def test_strip_modes_and_language_callback_are_kept():
    """去空白和回调仍按既有配置作用于实际pre元素。@return None。"""
    converter=MarkdownConverter(code_language='text',code_language_callback=lambda el:el.get('data-language'),strip_pre=None)
    assert converter.convert('<pre data-language="py">\n```\n</pre>')=='````py\n\n```\n\n````'
    assert markdownify('<pre>simple</pre>')=='```\nsimple\n```'

def test_invalid_information_line_is_rejected_not_injected():
    """信息行不能通过换行/反引号注入围栏结构。@return None。"""
    for value in ['py\n# escaped','py\rplain','py`']:
        with pytest.raises(ValueError):markdownify('<pre>code</pre>',code_language=value)
    with pytest.raises(TypeError):markdownify('<pre>code</pre>',code_language_callback=lambda el:123)
