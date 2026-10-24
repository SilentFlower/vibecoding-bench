"""一条坏记录不吞其他有效记录，引号中的分隔符不是同步点。"""
import unittest
import pyparsing as pp
from pyparsing.recovery import parse_recovering

def test_quoted_separator_multiline_record_and_bad_middle_recovery():
    """真实每记录语法解析，成功/失败坐标都保留。@return None。"""
    grammar=pp.Word(pp.alphas)+pp.Suppress('=')+pp.QuotedString('"',esc_char='\\',multiline=True)
    text='a="one;two";bad;\nb="line\nvalue";'
    value=parse_recovering(grammar,text)
    assert [x.results.as_list() for x in value.records]==[['a','one;two'],['b','line\nvalue']]
    assert len(value.errors)==1 and text[value.errors[0].start:value.errors[0].end]=='bad'
    assert value.errors[0].offset>=value.errors[0].start

def test_consecutive_bad_eof_empty_and_fatal_policy():
    """连续错误都有记录，未闭合引号不错误切出内部伪记录。@return None。"""
    grammar=pp.Literal('ok')
    value=parse_recovering(grammar,';bad;;ok;worse;')
    assert len(value.records)==1 and len(value.errors)==2
    assert len(parse_recovering(grammar,'"unclosed;ok').errors)==1
    def fatal():raise pp.ParseFatalException('x',0,'fatal')
    with unittest.TestCase().assertRaises(pp.ParseFatalException):parse_recovering(pp.Literal('x').set_parse_action(fatal),'x;ok')
    assert parse_recovering(grammar,'').records==()

