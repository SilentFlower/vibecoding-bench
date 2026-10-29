"""审计完整子测试合同，保持旧列表并核SQLGlot全量私有见证。"""
from collections import Counter
import gzip
from hashlib import sha256
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re
from types import CodeType


RESEARCH = Path(__file__).resolve().parent


class _FrozenControlLoader(SourceFileLoader):
    """只编译已核字节，避免读取或写入冻结目录中的pyc缓存。"""

    def __init__(self, fullname: str, path: str, contents: bytes) -> None:
        """绑定只读源码。@param fullname 模块名。@param path 取证原路径。@param contents 已核字节。@return None。"""
        super().__init__(fullname, path)
        self.contents = contents

    def get_code(self, fullname: str) -> CodeType:
        """跳过字节码缓存，仅从已核原件生成代码对象。@param fullname 模块名。@return 原件代码对象。"""
        return self.source_to_code(self.contents, self.path)


def _bytes(path: Path) -> bytes:
    """拒绝文件或父目录链接后读取原件。@param path 固定证据路径。@return 完整字节。"""
    if not path.is_file() or path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError('子项审计原件缺失或沿链接读取：' + str(path))
    return path.read_bytes()


def subtests_match_contract(actual: dict, contract: dict, task_key: str, catalog: Path) -> bool:
    """核候选完整子项结果与可信基线，不能把摘要当成少量子项。

    :param actual: 产品链实际原生结果。
    :param contract: 控制端冻结的完整合同。
    :param task_key: 实际任务标识。
    :param catalog: 本轮只读内容库。
    :return: 全部子项表示、数量、内容和结果满足同一合同为True。
    """
    expected = contract.get('subtests')
    if isinstance(expected, list):
        # 旧套件保持原审计的逐条比较与父节点校验，不重新解释列表合同。
        return (bool(expected) and actual.get('subtests') == expected
            and actual.get('subtest_count') == len(expected) and actual.get('subtests_match_contract') is True
            and all(item['parent_nodeid'] in {node['id'] for node in contract['nodes']}
                for item in actual['subtests']))
    if (task_key != 'SG-M01' or contract.get('project') != 'sqlglot'
            or not isinstance(expected, dict) or set(expected) != {'format', 'count', 'sha256'}
            or expected['format'] != 'sqlglot-subtests-v1' or type(expected['count']) is not int
            or expected['count'] <= 0 or re.fullmatch(r'[0-9a-f]{64}', expected['sha256']) is None):
        return False
    project = catalog / 'projects/sqlglot'
    manifest = json.loads(_bytes(project / 'project.json'))
    if manifest['source']['commit'] != '67961afbed7c986dfe26ab82db89a25814c1bdcb':
        return False
    receipt = json.loads(_bytes(RESEARCH / 'sqlglot-subtest-contract-attempt-005.json'))
    baseline = json.loads(_bytes(RESEARCH / 'native-baseline-sqlglot-final.json'))['projects'][0]
    private = project / 'verification'
    runner = private / 'native_regression.py'
    runner_contents = _bytes(runner)
    archive = receipt['complete_private_archive']
    compressed = _bytes(private / Path(archive['path']).name)
    if (sha256(compressed).hexdigest() != archive['sha256']
            or sha256(runner_contents).hexdigest() != baseline['runner_sha256']
            or sha256(_bytes(private / 'native-contract.json')).hexdigest() != baseline['contract_sha256']):
        return False
    raw = gzip.decompress(compressed)
    records = json.loads(raw)
    if (sha256(raw).hexdigest() != archive['observed_order_sha256'] or len(raw) != archive['expanded_bytes']
            or len(records) != expected['count'] or expected != receipt['subtests']):
        return False
    parents = {node['id'] for node in contract['nodes']}
    ordinals = Counter()
    for row in records:
        if (set(row) != {'parent_nodeid', 'ordinal', 'when', 'context', 'outcome'}
                or row['parent_nodeid'] not in parents or row['when'] != 'call'
                or row['outcome'] not in ('passed', 'skipped', 'xfailed')):
            return False
        ordinals[row['parent_nodeid']] += 1
        if type(row['ordinal']) is not int or row['ordinal'] != ordinals[row['parent_nodeid']]:
            return False
    fullname = '_frozen_sqlglot_subtest_control'
    specification = spec_from_file_location(fullname, runner,
        loader=_FrozenControlLoader(fullname, str(runner), runner_contents))
    if specification is None or specification.loader is None:
        raise ValueError('冻结SQLGlot子项控制模块无法加载')
    module = module_from_spec(specification)
    specification.loader.exec_module(module)
    # 使用逐SHA核过的本仓冻结控制器，后续共享runner升级不改变本次审计的规范化规则。
    if module._subtest_contract(records, 'sqlglot-subtests-v1') != expected:
        return False
    witness = actual.get('subtests_evidence', {})
    return (actual.get('subtest_contract') == expected and actual.get('subtest_count') == len(records)
        and actual.get('subtests_match_contract') is True and witness.get('count') == len(records)
        and witness.get('file') == 'subtests.json.gz'
        and type(witness.get('bytes')) is int and witness['bytes'] > 0
        and type(witness.get('expanded_bytes')) is int and witness['expanded_bytes'] > 0
        and all(isinstance(witness.get(key), str) and re.fullmatch(r'[0-9a-f]{64}', witness[key])
            for key in ('sha256', 'observed_order_sha256')))
