"Public regression tests for RICH-04-DEV; the complete business contract is in materials/RICH-04-DEV-contract.md."
from rich.text import Text
from rich.ansi import AnsiDecoder


def test_ignored_c0_inside_ansi_still_decodes_style():
    "Verify ignored c0 inside ansi still decodes style."
    for raw in ('\x1b\x00[31mRED\x1b[0m','\x1b[\x0031mRED\x1b[0m','\x1b\x01\x02[31mRED\x1b[0m'):
        text=Text.from_ansi(raw)
        assert text.plain=='RED' and '\x1b' not in text.plain and text.spans


def test_standard_sgr_osc_and_plain_whitespace_keep_contract():
    "Verify standard sgr osc and plain whitespace keep contract."
    normal=Text.from_ansi('\x1b[1mBold\x1b[0m')
    assert normal.plain=='Bold' and normal.spans
    linked=Text.from_ansi('\x1b]8;;https://example.com\x1b\\link\x1b]8;;\x1b\\')
    assert linked.plain=='link' and linked.spans[0].style.link=='https://example.com'
    assert Text.from_ansi('one\ttwo\nthree').plain=='one\ttwo\nthree'
    assert '\x1b' not in Text.from_ansi('text\x1b[').plain

