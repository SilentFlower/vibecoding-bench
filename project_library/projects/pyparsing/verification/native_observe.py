"""核完整解析、命名结果、选择顺序和原始字符位置。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import pyparsing
from pyparsing import Forward, Literal, Located, OneOrMore, ParseException, ParserElement, Suppress, Word, alphas, nums


def main() -> None:
    """所有语法只处理合成文本；全局模式诊断结束时恢复关闭。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(pyparsing.__file__).resolve() == root / 'library/pyparsing/__init__.py'}
    task = argv[1]
    if task == 'PP-U01':
        rule = Word(nums)
        prefix = rule.parse_string('12 trailing').as_list()
        rejected = False
        try:
            rule.parse_string('12 trailing', parse_all=True)
        except ParseException:
            rejected = True
        result['whole_input_acceptance_requires_an_explicit_end_check'] = (
            prefix == ['12'] and rejected and rule.parse_string('12', parse_all=True).as_list() == ['12'])
    elif task == 'PP-U02':
        last = OneOrMore(Word(alphas)('item')).parse_string('tea book', parse_all=True)
        all_values = OneOrMore(Word(alphas)('item*')).parse_string('tea book', parse_all=True)
        result['named_result_overwrite_and_all_matches_are_different_views'] = (
            last.as_list() == all_values.as_list() == ['tea', 'book']
            and last.as_dict() == {'item': 'book'} and all_values.as_dict() == {'item': ['tea', 'book']})
    elif task == 'PP-C01':
        short, long = Literal('a'), Literal('ab')
        first = (short | long).parse_string('ab').as_list()
        rejected = False
        try:
            (short | long).parse_string('ab', parse_all=True)
        except ParseException:
            rejected = True
        result['ordered_choice_does_not_reconsider_a_success_for_whole_input'] = (
            first == ['a'] and rejected
            and (long | short).parse_string('ab', parse_all=True).as_list() == ['ab']
            and (short ^ long).parse_string('ab', parse_all=True).as_list() == ['ab'])
    elif task == 'PP-C02':
        integer = Word(nums).set_parse_action(lambda tokens: int(tokens[0]))
        replacement = integer.copy().set_parse_action(lambda tokens: tokens[0] * 2)
        appended = integer.copy().add_parse_action(lambda tokens: tokens[0] * 2)
        result['parse_action_replacement_and_append_require_deliberate_rule_copies'] = (
            integer.parse_string('5', parse_all=True).as_list() == [5]
            and replacement.parse_string('5', parse_all=True).as_list() == ['55']
            and appended.parse_string('5', parse_all=True).as_list() == [10]
            and integer is not replacement and integer is not appended)
    elif task == 'PP-P01':
        source = '\t价格=12'
        default = (Suppress('价格=') + Located(Word(nums))).parse_string(source, parse_all=True)
        preserved = (Suppress('价格=') + Located(Word(nums))).parse_with_tabs().parse_string(source, parse_all=True)
        result['source_spans_must_name_tab_and_character_vs_byte_coordinates'] = (
            default.locn_start == 11 and default.locn_end == 13
            and preserved.locn_start == 4 and preserved.locn_end == 6
            and source[preserved.locn_start:preserved.locn_end] == '12'
            and len(source[:preserved.locn_start].encode('utf_8')) == 8)
    elif task == 'PP-D01':
        failure = None
        try:
            ParserElement.disable_memoization()
            ParserElement.enable_packrat()
            try:
                ParserElement.enable_left_recursion()
            except RuntimeError as error:
                failure = str(error)
            ParserElement.disable_memoization()
            ParserElement.enable_left_recursion()
            expression = Forward()
            number = Word(nums)
            expression <<= expression + '+' + number | number
            result.update(error=failure, left_recursion_control=expression.parse_string('1+2+3', parse_all=True).as_list())
        finally:
            ParserElement.disable_memoization()
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
