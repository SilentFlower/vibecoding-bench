"""旧式HTML颜色只移除规范中的五种ASCII空白。"""
import unittest
import webcolors


def test_non_ascii_whitespace_remains_input_data():
    """NBSP不允许被Python宽泛strip吞掉。@return None。"""
    assert webcolors.html5_parse_legacy_color('\u00a0red\u00a0')==(0,237,0)
    assert webcolors.html5_parse_legacy_color('red')==(255,0,0)


def test_ascii_trim_and_strict_simple_are_separate():
    """旧宽容入口的ASCII修剪不能污染严格simple入口。@return None。"""
    for char in (' ','\t','\n','\r','\f'):
        assert webcolors.html5_parse_legacy_color(char+'red'+char)==(255,0,0)
    with unittest.TestCase().assertRaises(ValueError):webcolors.html5_parse_legacy_color(' transparent ')
    with unittest.TestCase().assertRaises(ValueError):webcolors.html5_parse_simple_color(' #ff0000 ')
    assert webcolors.html5_parse_legacy_color(' \t\n')==(0,0,0)

