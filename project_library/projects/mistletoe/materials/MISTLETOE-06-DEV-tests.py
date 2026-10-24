"""LaTeX文本模式保留字面反斜线及波浪，不污染明确原文路径。"""
from mistletoe.latex_renderer import LaTeXRenderer
from mistletoe.span_token import RawText


def test_literal_backslash_and_tilde():
    """单遍转义不把生成的控制序列重复处理。@return None。"""
    with LaTeXRenderer() as renderer:
        assert renderer.render_raw_text(RawText(r'\alpha ~'))==r'\textbackslash{}alpha \textasciitilde{}'


def test_existing_symbols_and_unescaped_mode():
    """已有特殊字符保持既有形式，代码与数学的原文路径不变。@return None。"""
    with LaTeXRenderer() as renderer:
        assert renderer.render_raw_text(RawText('${}_%^'))==r'\$\{\}\_\%\^{}'
        assert renderer.render_raw_text(RawText(r'\alpha ~'),escape=False)==r'\alpha ~'

