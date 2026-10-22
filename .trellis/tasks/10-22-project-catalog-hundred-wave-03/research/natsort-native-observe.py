"""核产品标识的数值解析、路径分组和同序列联动重排。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import natsort
from natsort import index_natsorted, natsorted, ns, order_by_index


def main() -> None:
    """按任务选择已核控制，分别保留自然序和业务语义边界。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(natsort.__file__).resolve() == root / 'library/natsort/__init__.py'}
    task = argv[1]
    if task == 'NS-U01':
        values = ['v-3', 'v2', 'v-10']
        result['signed_numeric_parsing_changes_the_identifier_order'] = (
            natsorted(values) == ['v2', 'v-3', 'v-10']
            and natsorted(values, alg=ns.SIGNED) == ['v-10', 'v-3', 'v2'])
    elif task == 'NS-U02':
        values = ['p1.10', 'p1.2', 'p1.9']
        exponent = ['v1e2', 'v20', 'v3']
        result['float_and_exponent_flags_are_not_semantic_version_ordering'] = (
            natsorted(values) == ['p1.2', 'p1.9', 'p1.10']
            and natsorted(values, alg=ns.FLOAT) == ['p1.10', 'p1.2', 'p1.9']
            and natsorted(exponent, alg=ns.FLOAT) == ['v3', 'v20', 'v1e2']
            and natsorted(exponent, alg=ns.FLOAT | ns.NOEXP) == ['v1e2', 'v3', 'v20'])
    elif task == 'NS-C01':
        values = ['Folder/', 'Folder (1)/', 'Folder (10)/']
        result['path_components_require_explicit_path_sorting_semantics'] = (
            natsorted(values) == ['Folder (1)/', 'Folder (10)/', 'Folder/']
            and natsorted(values, alg=ns.PATH) == values)
    elif task == 'NS-C02':
        result['bytes_are_not_implicitly_decoded_into_natural_text_numbers'] = (
            natsorted([b'f10', b'f2']) == [b'f10', b'f2']
            and natsorted(['f10', 'f2']) == ['f2', 'f10'])
    elif task == 'NS-P01':
        labels, amounts = ['part10', 'part2', 'part1'], [100, 20, 10]
        ordering = index_natsorted(labels)
        result['one_frozen_index_permutation_preserves_parallel_record_alignment'] = (
            ordering == [2, 1, 0]
            and order_by_index(labels, ordering) == ['part1', 'part2', 'part10']
            and list(order_by_index(amounts, ordering, iter=True)) == [10, 20, 100]
            and amounts == [100, 20, 10])
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
