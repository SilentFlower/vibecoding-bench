"""从候选核英语文案、引擎状态和失败更新边界。"""
import json
import os
from pathlib import Path
import sys

import inflect
from inflect import UnknownClassicalModeError, engine


def unchanged_after_failure(options: dict) -> bool:
    """失败调用必须保持先前模式。@param options 模式参数。@return 是否符合。"""
    instance = engine()
    instance.classical(names=False, zero=True)
    before = instance.classical_dict.copy()
    try:
        instance.classical(**options)
    except UnknownClassicalModeError:
        return instance.classical_dict == before
    return False


def main() -> None:
    """执行单条有界合成业务，读取实际候选而非发行安装。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(inflect.__file__).resolve() == root / 'library/inflect/__init__.py'}
    task, instance = sys.argv[1], engine()
    if task == 'IF-U01':
        initial = instance.plural_noun('child')
        instance.num(1)
        implicit, explicit = instance.plural_noun('child'), instance.plural_noun('child', 2)
        instance.num()
        result['persistent_count_changes_implicit_calls_and_can_be_reset'] = (
            (initial, implicit, explicit, instance.plural_noun('child')) == ('children', 'child', 'children', 'children'))
    elif task == 'IF-C01':
        result['articles_use_word_specific_pronunciation_rules'] = (
            instance.a('hour') == 'an hour' and instance.a('university') == 'a university'
            and instance.a('MRI') == 'an MRI' and instance.a('hour', 2) == '2 hour')
    elif task == 'IF-C02':
        original = engine().plural_noun('URL')
        instance.defnoun('URL', 'URLs', case='preserve')
        result['scoped_custom_noun_rule_preserves_explicit_case'] = (
            instance.plural_noun('URL') == 'URLs' and original != 'URLs'
            and engine().plural_noun('URL') == original and instance.plural_noun('child') == 'children')
    elif task == 'IF-U02':
        result['number_words_are_not_a_strict_numeric_input_parser'] = (
            instance.number_to_words('1e3') == 'thirteen' and instance.number_to_words('abc') == 'zero'
            and instance.number_to_words(1000) == 'one thousand'
            and instance.number_to_words('12.30') == 'twelve point three zero')
    elif task == 'IF-U03':
        result['human_join_adapts_punctuation_and_is_not_machine_csv'] = (
            instance.join(['ant', 'bee', 'fly']) == 'ant, bee, and fly'
            and instance.join(['blue, green', 'red', 'gold']) == 'blue, green; red; and gold'
            and instance.join(['A', 'B']) == 'A and B' and instance.join(None) == '')
    elif task == 'IF-P01':
        other = engine()
        instance.num(1)
        instance.classical(names=False)
        result['engine_instances_own_count_modes_and_custom_rules'] = (
            instance.plural_noun('child') == 'child' and other.plural_noun('child') == 'children'
            and instance.plural_noun('Property', 2) == 'Properties'
            and other.plural_noun('Property', 2) == 'Propertys')
    elif task == 'IF-M01':
        cases = [{'all': True, 'invalid_option': True}, {'zero': False, 'invalid_option': True},
            {'invalid_option': True, 'all': False}, {'names': True, 'ancient': True, 'invalid_option': True}]
        valid = engine()
        valid.classical()
        all_enabled = all(valid.classical_dict.values())
        valid.classical(all=False, names=True)
        mixed = valid.classical_dict['names'] and not valid.classical_dict['zero']
        result['invalid_classical_keys_leave_prior_modes_unchanged'] = (
            all(unchanged_after_failure(case) for case in cases) and all_enabled and bool(mixed)
            and valid.plural_noun('child') == 'children')
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
