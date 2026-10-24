"Public regression tests for PYTHON-MARKDOWN-03-DEV; the complete business contract is in materials/PYTHON-MARKDOWN-03-DEV-contract.md."
import unittest
import markdown


def test_opt_in_ssh_urn_and_attribute_escaping():
    "Verify opt in ssh urn and attribute escaping."
    text='<ssh://example.com/repo?x=1&y=2> <urn:example:one>'
    assert '<a href="ssh:' not in markdown.markdown(text)
    output=markdown.markdown(text,extensions=['markdown.extensions.uri_autolink'])
    assert 'href="ssh://example.com/repo?x=1&amp;y=2"' in output
    assert 'href="urn:example:one"' in output
    assert '<em>keep</em>' in markdown.markdown('<em>keep</em>',extensions=['markdown.extensions.uri_autolink'])


def test_code_and_dangerous_policy_remain_separate():
    "Verify code and dangerous policy remain separate."
    output=markdown.markdown('`<ssh://example.com>` <javascript:alert(1)>',extensions=['markdown.extensions.uri_autolink'])
    assert '<code>&lt;ssh://example.com&gt;</code>' in output and '<a href="javascript:' not in output
    with unittest.TestCase().assertRaises(ValueError):markdown.Markdown(extensions=['markdown.extensions.uri_autolink'],extension_configs={'markdown.extensions.uri_autolink':{'schemes':['javascript']}})

