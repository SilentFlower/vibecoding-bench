"Public regression tests for MARKDOWN-IT-O03-DEV; the complete business contract is in materials/MARKDOWN-IT-O03-DEV-contract.md."
from markdown_it import MarkdownIt
import pytest

def test_explicit_full_block_preserves_container_and_one_trailing_newline():
    "Verify explicit full block preserves container and one trailing newline."
    from markdown_it.renderer import HighlightResult
    for text in ['<div class="highlight">code</div>','<div>code</div>\n']:
        md=MarkdownIt(options_update={'highlight':lambda *args:HighlightResult(text,block=True)})
        assert md.render('```py\nsource\n```')==text.rstrip('\n')+'\n'

def test_inline_explicit_pre_looking_and_empty_results_have_defined_behavior():
    "Verify inline explicit pre looking and empty results have defined behavior."
    from markdown_it.renderer import HighlightResult
    md=MarkdownIt(options_update={'highlight':lambda *args:HighlightResult('<pre-fragment>x',block=False)})
    assert md.render('```py\nsource\n```')=='<pre><code class="language-py"><pre-fragment>x</code></pre>\n'
    empty=MarkdownIt(options_update={'highlight':lambda *args:HighlightResult('',block=True)})
    assert empty.render('```\n<a>\n```')=='<pre><code>&lt;a&gt;\n</code></pre>\n'

def test_legacy_strings_callback_arguments_and_errors_are_preserved():
    "Verify legacy strings callback arguments and errors are preserved."
    from markdown_it.renderer import HighlightResult
    seen=[]
    md=MarkdownIt(options_update={'highlight':lambda *args:seen.append(args) or '<pre>legacy</pre>'})
    assert md.render('```py extra\ncode\n```')=='<pre>legacy</pre>\n' and seen==[('code\n','py','extra')]
    with pytest.raises(TypeError):HighlightResult('x',block='yes')
    with pytest.raises(TypeError):MarkdownIt(options_update={'highlight':lambda *args:object()}).render('```\nx\n```')
