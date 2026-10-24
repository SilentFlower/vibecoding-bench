"""URI链接范围可选且属性安全转义，不能把任意标签当链接。"""
import unittest
import markdown


def test_opt_in_ssh_urn_and_attribute_escaping():
    """ssh/urn通过本实例策略，URL中的&不会破坏属性。@return None。"""
    text='<ssh://example.com/repo?x=1&y=2> <urn:example:one>'
    assert '<a href="ssh:' not in markdown.markdown(text)
    output=markdown.markdown(text,extensions=['markdown.extensions.uri_autolink'])
    assert 'href="ssh://example.com/repo?x=1&amp;y=2"' in output
    assert 'href="urn:example:one"' in output
    assert '<em>keep</em>' in markdown.markdown('<em>keep</em>',extensions=['markdown.extensions.uri_autolink'])


def test_code_and_dangerous_policy_remain_separate():
    """代码中不展开，危险白名单直接拒绝。@return None。"""
    output=markdown.markdown('`<ssh://example.com>` <javascript:alert(1)>',extensions=['markdown.extensions.uri_autolink'])
    assert '<code>&lt;ssh://example.com&gt;</code>' in output and '<a href="javascript:' not in output
    with unittest.TestCase().assertRaises(ValueError):markdown.Markdown(extensions=['markdown.extensions.uri_autolink'],extension_configs={'markdown.extensions.uri_autolink':{'schemes':['javascript']}})

