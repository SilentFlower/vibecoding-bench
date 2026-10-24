"Public regression tests for MISTLETOE-06-DEV; the complete business contract is in materials/MISTLETOE-06-DEV-contract.md."
from mistletoe.latex_renderer import LaTeXRenderer
from mistletoe.span_token import RawText


def test_literal_backslash_and_tilde():
    "Verify literal backslash and tilde."
    with LaTeXRenderer() as renderer:
        assert renderer.render_raw_text(RawText(r'\alpha ~'))==r'\textbackslash{}alpha \textasciitilde{}'


def test_existing_symbols_and_unescaped_mode():
    "Verify existing symbols and unescaped mode."
    with LaTeXRenderer() as renderer:
        assert renderer.render_raw_text(RawText('${}_%^'))==r'\$\{\}\_\%\^{}'
        assert renderer.render_raw_text(RawText(r'\alpha ~'),escape=False)==r'\alpha ~'

