"""高亮器显式声明完整块，避免div容器被再包一层pre。"""
from markdown_it import MarkdownIt
import pytest

def test_explicit_full_block_preserves_container_and_one_trailing_newline():
    """实际fence渲染输出完整div，已有换行不重复。@return None。"""
    from markdown_it.renderer import HighlightResult
    for text in ['<div class="highlight">code</div>','<div>code</div>\n']:
        md=MarkdownIt(options_update={'highlight':lambda *args:HighlightResult(text,block=True)})
        assert md.render('```py\nsource\n```')==text.rstrip('\n')+'\n'

def test_inline_explicit_pre_looking_and_empty_results_have_defined_behavior():
    """显式inline不走旧字符串pre启发式；空结果回退转义原文。@return None。"""
    from markdown_it.renderer import HighlightResult
    md=MarkdownIt(options_update={'highlight':lambda *args:HighlightResult('<pre-fragment>x',block=False)})
    assert md.render('```py\nsource\n```')=='<pre><code class="language-py"><pre-fragment>x</code></pre>\n'
    empty=MarkdownIt(options_update={'highlight':lambda *args:HighlightResult('',block=True)})
    assert empty.render('```\n<a>\n```')=='<pre><code>&lt;a&gt;\n</code></pre>\n'

def test_legacy_strings_callback_arguments_and_errors_are_preserved():
    """旧字符串/空值契约不变，非法类型和回调异常明确传播。@return None。"""
    from markdown_it.renderer import HighlightResult
    seen=[]
    md=MarkdownIt(options_update={'highlight':lambda *args:seen.append(args) or '<pre>legacy</pre>'})
    assert md.render('```py extra\ncode\n```')=='<pre>legacy</pre>\n' and seen==[('code\n','py','extra')]
    with pytest.raises(TypeError):HighlightResult('x',block='yes')
    with pytest.raises(TypeError):MarkdownIt(options_update={'highlight':lambda *args:object()}).render('```\nx\n```')
