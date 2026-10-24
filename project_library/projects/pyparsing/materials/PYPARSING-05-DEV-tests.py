"""机器错误坐标为字符口径，不能伪称字节或显示宽度。"""
import unittest
import pyparsing as pp
from pyparsing.diagnostics import to_diagnostic

def test_real_multiline_unicode_error_preserves_existing_text():
    """真实失败的异常文字不被投影过程改写。@return None。"""
    grammar=(pp.Literal('雪')+pp.Literal('ok')).parse_with_tabs()
    with unittest.TestCase().assertRaises(pp.ParseException) as caught:grammar.parse_string('雪\n?',parse_all=True)
    error=caught.exception;before=str(error);report=to_diagnostic(error)
    assert report['schema']==1 and report['offset']==2 and report['end_offset']==3
    assert report['line']==2 and report['column']==1 and report['at_eof'] is False
    assert report['code']=='parse-error' and report['expected'] is None and str(error)==before

def test_eof_fatal_and_nonparse_exceptions_have_explicit_policy():
    """EOF范围为零宽，fatal单独代码，用户普通错误不装成语法错误。@return None。"""
    error=pp.ParseFatalException('茶',1,'fatal',pp.Literal('x'))
    report=to_diagnostic(error)
    assert report['code']=='parse-fatal' and report['at_eof'] and report['offset']==report['end_offset']==1
    assert report['node_type'] in ('Literal','_SingleCharLiteral')
    with unittest.TestCase().assertRaises(TypeError):to_diagnostic(ValueError('action'))

