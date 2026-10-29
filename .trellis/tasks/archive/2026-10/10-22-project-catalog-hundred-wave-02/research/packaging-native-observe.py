"""核版本身份、预发布候选集合、目标环境和离线候选筛选。"""
import json
import os
from pathlib import Path
import sys

import packaging
from packaging.dependency_groups import resolve_dependency_groups
from packaging.markers import Marker, default_environment
from packaging.specifiers import SpecifierSet
from packaging.tags import Tag
from packaging.utils import parse_wheel_filename
from packaging.version import Version


def main() -> None:
    """用固定源码和完整合成输入核五项只读合同。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(packaging.__file__).resolve() == root / 'library/src/packaging/__init__.py'}
    task = sys.argv[1]
    if task == 'PK-U01':
        first, second = Version('v1.0'), Version('1.0.0')
        result['normalized_version_equality_is_distinct_from_original_or_display_identity'] = (
            first == second and hash(first) == hash(second)
            and str(first) == '1.0' and str(second) == '1.0.0'
            and str(Version('1.0+ABC_1')) == '1.0+abc.1'
            and Version('1.0+abc.1') != Version('1.0'))
    elif task == 'PK-U02':
        specifier = SpecifierSet('>=1.2.3')
        result['prerelease_selection_depends_on_candidate_set_and_explicit_policy'] = (
            specifier.contains('1.5a1')
            and list(specifier.filter(['1.3', '1.5a1'])) == ['1.3']
            and list(specifier.filter(['1.2', '1.5a1'])) == ['1.5a1']
            and list(specifier.filter(['1.3', '1.5a1'], prereleases=True)) == ['1.3', '1.5a1']
            and not specifier.contains('1.5a1', prereleases=False))
    elif task == 'PK-C01':
        marker = Marker('sys_platform == "win32" and python_version >= "3.10"')
        result['partial_marker_overrides_keep_host_fields_and_require_complete_target_policy'] = (
            default_environment()['sys_platform'] == 'linux'
            and not marker.evaluate({'python_version': '3.12'})
            and marker.evaluate({'sys_platform': 'win32', 'python_version': '3.12'}))
    elif task == 'PK-C02':
        groups = {'test': ['pytest>=8'], 'Dev_Test': [
            {'include-group': 'test'}, 'ruff', {'include-group': 'test'}]}
        result['existing_dependency_group_resolution_normalizes_names_and_retains_order_and_duplicates'] = (
            resolve_dependency_groups(groups, 'dev-test') == ('pytest>=8', 'ruff', 'pytest>=8')
            and groups['Dev_Test'][0] == {'include-group': 'test'})
    elif task == 'PK-P01':
        target = {Tag('cp312', 'cp312', 'manylinux_2_17_x86_64'), Tag('py3', 'none', 'any')}
        inputs = ['demo-1.0-py3-none-any.whl', 'demo-2.0-cp313-cp313-win_amd64.whl']
        parsed = [parse_wheel_filename(name) for name in inputs]
        matches = [bool(row[3] & target) for row in parsed]
        result['wheel_filename_parsing_and_tag_intersection_do_not_open_or_verify_archives'] = (
            matches == [True, False] and [str(row[1]) for row in parsed] == ['1.0', '2.0']
            and all(row[0] == 'demo' and row[2] == () for row in parsed))
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
