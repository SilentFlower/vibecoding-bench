"Public regression tests for PYTHON-MARKDOWN-04-DEV; the complete business contract is in materials/PYTHON-MARKDOWN-04-DEV-contract.md."
import unittest
import markdown


def test_longer_same_character_closer_and_default_isolation():
    "Verify longer same character closer and default isolation."
    text='~~~python\nprint("中文")\n~~~~~'
    default=markdown.markdown(text,extensions=['markdown.extensions.fenced_code'])
    output=markdown.markdown(text,extensions=['markdown.extensions.fenced_code'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'at_least'}})
    assert '<pre>' not in default
    assert '<pre><code class="language-python">print(&quot;中文&quot;)\n</code></pre>' in output
    assert '<pre>' not in markdown.markdown(text,extensions=['markdown.extensions.fenced_code'])


def test_shorter_mixed_or_nonstandalone_closer_does_not_close():
    "Verify shorter mixed or nonstandalone closer does not close."
    text='~~~~\na\n~~~\nb\n~~~~~'
    output=markdown.markdown(text,extensions=['markdown.extensions.fenced_code'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'at_least'}})
    assert 'a\n~~~\nb\n' in output and '<pre>' in output
    for text in ('~~~\na\n````','~~~\na\n~~~~tail'):
        assert '<pre>' not in markdown.markdown(text,extensions=['markdown.extensions.fenced_code'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'at_least'}})
    with unittest.TestCase().assertRaises(ValueError):markdown.Markdown(extensions=['markdown.extensions.fenced_code'],extension_configs={'markdown.extensions.fenced_code':{'closing_fence':'wrong'}})

