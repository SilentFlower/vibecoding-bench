"""只在候选纯Python解析器内核配置类型、图、流和文档投影。"""
import json
import os
from pathlib import Path
import sys

import yaml
from yaml import BaseLoader, SafeLoader, YAMLError, compose, load, safe_dump, safe_load, safe_load_all


def yaml_error(action) -> bool:
    """确认真实YAML错误，不执行不安全构造器。@param action 调用。@return 是否拒绝。"""
    try:
        action()
    except YAMLError:
        return True
    return False


def main() -> None:
    """按冻结任务返回可核事实，循环图从不直接JSON序列化。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(yaml.__file__).resolve() == root / 'library/lib/yaml/__init__.py'}
    if yaml.__with_libyaml__:
        raise ValueError('本场景只声明实际纯Python路径')
    task = sys.argv[1]
    if task == 'YY-U01':
        plain = safe_load('enabled: on\ncode: 012\nlabel: "on"\n')
        base = load('enabled: on\ncode: 012\nlabel: "on"\n', Loader=BaseLoader)
        result['implicit_scalars_and_base_loader_have_distinct_types'] = (
            plain == {'enabled': True, 'code': 10, 'label': 'on'}
            and base == {'enabled': 'on', 'code': '012', 'label': 'on'})
    elif task == 'YY-C01':
        result['safe_tag_policy_is_not_business_schema_or_work_limit'] = (
            yaml_error(lambda: safe_load('!warehouse A'))
            and load('!warehouse A', Loader=BaseLoader) == 'A'
            and safe_load('sku: ""\nqty: -2\n') == {'sku': '', 'qty': -2})
    elif task == 'YY-U02':
        data = safe_load('base: &stock [A]\nleft: *stock\nright: *stock\n')
        shared = data['base'] is data['left'] is data['right']
        data['left'].append('B')
        cycle = safe_load('&stock [*stock]')
        result['aliases_preserve_shared_identity_and_can_form_cycles'] = (
            shared and data['right'] == ['A', 'B'] and cycle[0] is cycle)
    elif task == 'YY-U03':
        source = '# warehouse comment\nb: "A"\na: 1\n'
        data = safe_load(source)
        encoded = safe_dump(data, sort_keys=True)
        result['dump_round_trip_preserves_values_not_original_presentation'] = (
            safe_load(encoded) == data and '# warehouse comment' not in encoded
            and encoded.startswith('a: 1\n') and encoded != source)
    elif task == 'YY-C02':
        source = 'qty: 1\nqty: 2\n'
        node = compose(source, Loader=SafeLoader)
        pairs = [(key.value, value.value) for key, value in node.value]
        collision = safe_load('true: first\n1: second\n')
        result['duplicate_pairs_remain_in_nodes_but_constructed_mapping_is_last_wins'] = (
            safe_load(source) == {'qty': 2} and pairs == [('qty', '1'), ('qty', '2')]
            and len(collision) == 1 and collision[True] == 'second')
    elif task == 'YY-P01':
        documents = safe_load_all('batch: 1\n---\nbatch: [\n')
        first = next(documents)
        later_error = yaml_error(lambda: next(documents))
        valid = 'batch: 1\n---\nbatch: 2\n'
        result['multi_document_iteration_can_fail_after_a_valid_prefix'] = (
            first == {'batch': 1} and later_error
            and yaml_error(lambda: safe_load(valid))
            and list(safe_load_all(valid)) == [{'batch': 1}, {'batch': 2}])
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
