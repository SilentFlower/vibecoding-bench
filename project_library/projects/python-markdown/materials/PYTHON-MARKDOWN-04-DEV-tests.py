"""结束围栏最小长度是显式兼容模式，默认exact保持。"""
import unittest
import markdown


def test_longer_same_character_closer_and_default_isolation():
    """开三闭五可选识别，语言与代码正文不丢。@return None。"""
    text='~~~python\nprint("中文")\n~~~~~'
    default=markdown.markdown(text,extensions=['markdown.extensions.fenced_code'])
    output=markdown.markdown(text,extensions=['markdown.extensions.fenced_code'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'at_least'}})
    assert '<pre>' not in default
    assert '<pre><code class="language-python">print(&quot;中文&quot;)\n</code></pre>' in output
    assert '<pre>' not in markdown.markdown(text,extensions=['markdown.extensions.fenced_code'])


def test_shorter_mixed_or_nonstandalone_closer_does_not_close():
    """字符与长度双重约束，内部较短围栏仍为代码。@return None。"""
    text='~~~~\na\n~~~\nb\n~~~~~'
    output=markdown.markdown(text,extensions=['markdown.extensions.fenced_code'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'at_least'}})
    assert 'a\n~~~\nb\n' in output and '<pre>' in output
    for text in ('~~~\na\n````','~~~\na\n~~~~tail'):
        assert '<pre>' not in markdown.markdown(text,extensions=['markdown.extensions.fenced_code'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'at_least'}})
    with unittest.TestCase().assertRaises(ValueError):markdown.Markdown(extensions=['markdown.extensions.fenced_code'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'wrong'}})

