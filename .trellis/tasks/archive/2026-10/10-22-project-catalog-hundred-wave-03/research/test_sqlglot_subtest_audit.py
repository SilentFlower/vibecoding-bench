"""用真实产品链结果验证审计器拒绝子项摘要和见证篡改。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
from sqlite3 import connect
from tempfile import TemporaryDirectory
import unittest

from sqlglot_subtest_audit import subtests_match_contract


ROOT = Path.cwd()
BUNDLE = ROOT / '.deploy/project-catalog-hundred/stage-03/mock-batch-015-retry-002-sqlglot'


class SQLGlotSubtestAuditTests(unittest.TestCase):
    """只修改隔离副本，真实运行和冻结控制原件保持。"""

    def setUp(self) -> None:
        """复制最小私有见证并读取实际已通过的产品结果。@return None。"""
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.catalog = Path(temporary.name)
        self.project = self.catalog / 'projects/sqlglot'
        private = self.project / 'verification'
        private.mkdir(parents=True)
        original = BUNDLE / 'library/projects/sqlglot'
        for name in ('project.json', 'verification/native_regression.py', 'verification/native-contract.json',
                'verification/native-subtests-attempt-005.json.gz'):
            copyfile(original / name, self.project / name)
        self.contract = json.loads((private / 'native-contract.json').read_text())
        database = BUNDLE / 'run-001/evidence/private-synthetic.sqlite'
        with connect(database.as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
            raw = connection.execute('SELECT j.native_result_json FROM project_evaluation_jobs j '
                'JOIN project_scenario_tasks t ON t.id=j.task_id WHERE t.task_key=? AND j.status=? ORDER BY j.id LIMIT 1',
                ('SG-M01', 'passed')).fetchone()[0]
        self.actual = json.loads(raw)['native']['regression']['regression']

    def test_real_product_result_matches_all_frozen_subtests(self) -> None:
        """实际1500主项及21780子项的完整见证可被审计。@return None。"""
        before = {str(path.relative_to(self.project)): sha256(path.read_bytes()).hexdigest()
            for path in self.project.rglob('*') if path.is_file()}
        self.assertTrue(subtests_match_contract(self.actual, self.contract, 'SG-M01', self.catalog))
        after = {str(path.relative_to(self.project)): sha256(path.read_bytes()).hexdigest()
            for path in self.project.rglob('*') if path.is_file()}
        self.assertEqual(before, after)

    def test_wrong_count_digest_result_and_format_are_rejected(self) -> None:
        """缺项、换摘要、缺匹配证明或伪造表示均拒绝。@return None。"""
        for field, value in (('subtest_count', 21779), ('subtests_match_contract', False),
                ('subtest_contract', {**self.contract['subtests'], 'sha256': '0' * 64}),
                ('subtests_evidence', {})):
            with self.subTest(field=field):
                actual = {**self.actual, field: value}
                self.assertFalse(subtests_match_contract(actual, self.contract, 'SG-M01', self.catalog))
        contract = deepcopy(self.contract)
        contract['subtests']['format'] = 'unknown'
        self.assertFalse(subtests_match_contract(self.actual, contract, 'SG-M01', self.catalog))
        self.assertFalse(subtests_match_contract(self.actual, self.contract, 'other-task', self.catalog))

    def test_corrupted_complete_archive_is_rejected(self) -> None:
        """不能仅凭正确摘要头忽略丢失或被改写的全量原件。@return None。"""
        archive = self.project / 'verification/native-subtests-attempt-005.json.gz'
        archive.write_bytes(archive.read_bytes()[:-1])
        self.assertFalse(subtests_match_contract(self.actual, self.contract, 'SG-M01', self.catalog))

    def test_changed_frozen_controller_is_rejected(self) -> None:
        """审计必须绑定本仓原冻结规则，不能借共享控制器漂移放行。@return None。"""
        runner = self.project / 'verification/native_regression.py'
        runner.write_bytes(runner.read_bytes() + b'\n')
        self.assertFalse(subtests_match_contract(self.actual, self.contract, 'SG-M01', self.catalog))

    def test_archive_symlink_is_rejected(self) -> None:
        """完整证据必须是本库普通文件，不能沿链接读取另一份原件。@return None。"""
        archive = self.project / 'verification/native-subtests-attempt-005.json.gz'
        archive.unlink()
        archive.symlink_to(BUNDLE / 'library/projects/sqlglot/verification/native-subtests-attempt-005.json.gz')
        with self.assertRaises(ValueError):
            subtests_match_contract(self.actual, self.contract, 'SG-M01', self.catalog)

    def test_legacy_lists_keep_exact_comparison_and_duplicate_count(self) -> None:
        """旧列表保持全部重复上下文，不能用新格式降低旧合同。@return None。"""
        rows = [{'parent_nodeid': 'original', 'ordinal': ordinal, 'outcome': 'passed'} for ordinal in (1, 2)]
        contract = {'nodes': [{'id': 'original'}], 'subtests': rows}
        actual = {'subtests': deepcopy(rows), 'subtest_count': 2, 'subtests_match_contract': True}
        self.assertTrue(subtests_match_contract(actual, contract, 'legacy', self.catalog))
        actual['subtests'].pop()
        self.assertFalse(subtests_match_contract(actual, contract, 'legacy', self.catalog))


if __name__ == '__main__':
    unittest.main()
