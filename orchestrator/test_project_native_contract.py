"""核验原生证据等价规则与原冻结控制器的真实执行接入。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unittest

from project_native_contract import native_metadata_facts, native_skips_match, native_subtests_match
from project_verifier import _NativeRegressionControlError, _native_regression_adapter
from projects_verification import ProjectsVerification


ROOT = Path(__file__).resolve().parents[1]


class NativeContractTests(unittest.TestCase):
    """允许无业务含义的表示变化，仍拒绝不完整和错误的真实测试证据。"""

    def rows(self):
        """取得含重复上下文的独立原生记录。:return: 三条完整记录。"""
        return [{'parent_nodeid': 'parent', 'ordinal': number, 'when': 'call', 'outcome': 'passed',
            'context': {'msg': None, 'kwargs': {'value': repr(value)}}}
            for number, value in enumerate(('one', 'two', 'two'), 1)]

    def test_order_is_metadata_but_identity_context_outcome_and_multiplicity_remain_required(self):
        """重排可通过，漏项、改值、改节点、改状态和去重均失败。:return: None。"""
        expected = self.rows()
        before = deepcopy(expected)
        actual = [{**row, 'ordinal': index} for index, row in enumerate(reversed(expected), 1)]
        self.assertTrue(native_subtests_match('docutils', actual, expected))
        cases = [expected[:-1], [*expected, expected[0]], [expected[0], expected[1]]]
        for changes in ({'parent_nodeid': 'other'}, {'outcome': 'skipped'}, {'outcome': 'failed'},
                {'when': 'setup'}, {'context': {'msg': 'changed', 'kwargs': {}}}):
            cases.append([{**expected[0], **changes}, *expected[1:]])
        for rows in cases:
            with self.subTest(rows=rows):
                self.assertFalse(native_subtests_match('docutils', rows, expected))
        self.assertEqual(before, expected)

    def test_all_frozen_address_records_accept_new_addresses_without_touching_original_evidence(self):
        """三个真实套件的45条默认repr允许进程地址变化，其他字段不变。:return: None。"""
        count = 0
        for project in ('more-itertools', 'pyparsing', 'wrapt'):
            contract = json.loads((ROOT / 'project_library/projects' / project / 'verification/native-contract.json').read_text())
            original = contract['subtests']
            actual = deepcopy(original)
            for row in actual:
                for key, value in row['context']['kwargs'].items():
                    changed = re.sub(r'(?<= at )0x[0-9a-fA-F]+(?=>)', '0x123456789', value)
                    count += changed != value
                    row['context']['kwargs'][key] = changed
            self.assertTrue(native_subtests_match(project, actual, original), project)
            self.assertNotEqual(actual, original)
        self.assertEqual(count, 45)

    def test_address_rule_preserves_functions_types_literals_and_unreviewed_locations(self):
        """只容忍已核默认repr地址；业务字面量、类型和函数身份仍检查。:return: None。"""
        row = {'parent_nodeid': 'tests/test_more.py::LastTests::test_basic', 'ordinal': 1,
            'when': 'call', 'outcome': 'passed', 'context': {'msg': None,
                'kwargs': {'iterable': '<range_iterator object at 0x1234>'}}}
        good = deepcopy(row)
        good['context']['kwargs']['iterable'] = '<range_iterator object at 0xabcd>'
        self.assertTrue(native_subtests_match('more-itertools', [good], [row]))
        self.assertFalse(native_subtests_match('other', [good], [row]))
        for value in ('<list_iterator object at 0xabcd>', "'<range_iterator object at 0xabcd>'", 'SELECT 0xabcd'):
            bad = deepcopy(good)
            bad['context']['kwargs']['iterable'] = value
            self.assertFalse(native_subtests_match('more-itertools', [bad], [row]))
        for key in ('parent_nodeid', 'when', 'outcome'):
            bad = {**good, key: 'changed'}
            self.assertFalse(native_subtests_match('more-itertools', [bad], [row]))
        function = deepcopy(row)
        function['parent_nodeid'] = 'tests/test_recipes.py::PadnoneTests::test_basic'
        function['context']['kwargs'] = {'func': '<function pad_none at 0x1234>'}
        changed = deepcopy(function)
        changed['context']['kwargs']['func'] = '<function other at 0xabcd>'
        self.assertFalse(native_subtests_match('more-itertools', [changed], [function]))

    def test_skips_keep_reasons_and_duplicates_and_digest_formats_keep_original_meaning(self):
        """跳过清单只放宽次序，已有不可逆摘要仍精确比较。:return: None。"""
        rows = [{'id': 'a', 'reason': 'optional unavailable'}, {'id': 'b', 'reason': 'external converter'}]
        self.assertTrue(native_skips_match(list(reversed(rows)), rows))
        self.assertFalse(native_skips_match(rows[:-1], rows))
        self.assertFalse(native_skips_match(rows + [rows[0]], rows))
        self.assertFalse(native_skips_match([{**rows[0], 'reason': 'new missing dependency'}, rows[1]], rows))
        self.assertFalse(native_skips_match(None, rows))
        digest = {'format': 'sqlglot-subtests-v1', 'count': 3, 'sha256': 'a' * 64}
        self.assertTrue(native_subtests_match('sqlglot', deepcopy(digest), digest))
        self.assertFalse(native_subtests_match('sqlglot', {**digest, 'count': 2}, digest))

    def test_product_adapter_calls_semantic_matcher_in_decision_and_report_without_changing_frozen_files(self):
        """真实冻结函数同时用于最终判定和报告，未知源码不能推测替换。:return: None。"""
        source_path = ROOT / 'project_library/projects/docutils/verification/native_regression.py'
        source = source_path.read_bytes()
        contract = json.loads(source_path.with_name('native-contract.json').read_text())
        actual, adapter = _native_regression_adapter(source, contract)
        compile(actual, '<实际可信回归器>', 'exec')
        self.assertEqual(source, source_path.read_bytes())
        self.assertEqual(actual.count(b"native_subtests_match(options.project, subtests, contract['subtests'])"), 2)
        self.assertNotIn(b"subtests == contract['subtests']", actual)
        self.assertEqual(adapter['name'], 'native-evidence-semantics-v1')
        self.assertEqual(adapter['original_runner_sha256'], hashlib.sha256(source).hexdigest())
        self.assertEqual(adapter['effective_runner_sha256'], hashlib.sha256(actual).hexdigest())
        with self.assertRaises(_NativeRegressionControlError):
            _native_regression_adapter(source + b'\n', contract)

    def test_metadata_failure_facts_explain_difference_without_private_context(self):
        """公开固定差异数量并明确核验元数据，不暴露子测试参数正文。:return: None。"""
        rows = self.rows()
        report = {'subtests_match_contract': False, 'subtests': rows[:-1]}
        facts = native_metadata_facts('fixture', report, {'subtests': rows})
        self.assertIn('缺少 1 条，额外 0 条', facts[0]['reason'])
        self.assertNotIn('two', json.dumps(facts))
        feedback = ProjectsVerification._business_feedback({'regression': report})
        self.assertIn('先核验元数据差异', feedback[0])
