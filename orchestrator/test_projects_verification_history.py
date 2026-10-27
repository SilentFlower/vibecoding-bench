"""验证真实候选保住已接受功能，不能只满足本轮需求便通过。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from project_library import ProjectDefinition, snapshot_tree
from projects_verification import ProjectsVerification


class NativeBehavior:
    """在独立 Python 进程调用候选函数，模拟程序验收的能力边界。"""

    def __init__(self):
        """保存观察到的候选路径和可控基础设施错误次数。:return: None。"""
        self.paths = []
        self.errors = 0

    def verify_native(self, candidate, project, specification, environment, profile, *, regression=False,
                      cancel=None, **kwargs):
        """用独立进程检查指定实际行为，不信任提交说明。

        :param candidate: 同一冻结交付。
        :param project: 原冻结项目。
        :param specification: 冻结函数结果。
        :param environment: 原环境目录。
        :param profile: 原离线环境。
        :param regression: 是否只核原有模块可加载。
        :param cancel: 取消信号。
        :param kwargs: 产品验证器的其他公开可选参数。
        :return: 程序实际通过、失败或基础设施错误。
        """
        self.paths.append(candidate)
        if 'previous' in specification['expected'] and self.errors:
            self.errors -= 1
            return {'status': 'error', 'message': '合成容器暂不可用'}
        program = """import json,sys
from pathlib import Path
namespace={}
exec(compile(Path(sys.argv[1]).read_text(),sys.argv[1],'exec'),namespace)
expected=json.loads(sys.argv[2])
assert all(namespace[name]()==value for name,value in expected.items())
"""
        expected = {} if regression else specification['expected']
        process = subprocess.run([sys.executable, '-I', '-c', program,
            str(candidate / 'library/example.py'), json.dumps(expected)], capture_output=True, text=True)
        return {'status': 'passed' if process.returncode == 0 else 'failed'}


class ProjectsVerificationHistoryTests(unittest.TestCase):
    """在同一候选上重放旧合同，验证返工和基础设施错误的区分。"""

    def setUp(self):
        """建立真实旧功能、新需求与两份独立冻结合同。:return: None。"""
        temporary = tempfile.TemporaryDirectory(prefix='projects-accepted-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.baseline = self.root / 'baseline'
        (self.baseline / 'library').mkdir(parents=True)
        (self.baseline / 'library/example.py').write_text('def previous():\n    return 1\n')
        self.current = {'id': 'NEXT', 'allowed_paths': ['library/example.py'],
            'evaluation': {'native': 'verification/current.json', 'semantic': False}}
        self.previous = {'id': 'FIRST', 'evaluation': {'native': 'verification/previous.json'}}
        self.current_assets = self.assets('new', 'current.json', {'expected': {'current': 2}, 'regression': True}, self.current)
        self.old_assets = self.assets('old', 'previous.json', {'expected': {'previous': 1}}, self.previous)
        self.old_work = {'id': 'old-work', 'project_key': 'example', 'objective_id': 'FIRST',
            'definition_json': json.dumps(self.previous), 'library_digest': 'old'}
        self.work = {'id': 'new-work', 'account_id': 1, 'project_key': 'example', 'objective_id': 'NEXT',
            'definition_json': json.dumps(self.current), 'library_digest': 'new',
            'baseline_json': json.dumps(snapshot_tree(self.baseline))}
        self.native = NativeBehavior()
        catalog = SimpleNamespace(for_work=lambda work: self.old_assets
            if work['library_digest'] == 'old' else self.current_assets)
        terminal = SimpleNamespace(conversation=lambda work: [{'role': 'assistant', 'content': '已交付'}])
        self.verification = ProjectsVerification(catalog, terminal, self.native, None, lambda: None,
            accepted=lambda work: [self.old_work])

    def assets(self, digest, name, specification, definition):
        """构造原版本的真实私有规范文件。

        :param digest: 内容版本标识。
        :param name: 私有规范文件名。
        :param specification: 冻结行为预期。
        :param definition: 原工程定义。
        :return: 只包含产品已定义字段的资产替身。
        """
        root = self.root / digest
        (root / 'verification').mkdir(parents=True)
        (root / 'verification' / name).write_text(json.dumps(specification))
        project = ProjectDefinition(root, {'environment': 'python'})
        library = SimpleNamespace(digest=digest, root=root, environments={'python': {}})
        return SimpleNamespace(library=library, objective=lambda key, task: (project, definition))

    def submit(self, previous_value):
        """冻结一个满足新需求、但可保留或破坏旧功能的实际候选。

        :param previous_value: 旧功能真实返回值。
        :return: 产品同款验收结果。
        """
        candidate = self.root / 'source'
        (candidate / 'library').mkdir(parents=True)
        (candidate / 'library/example.py').write_text(
            f'def previous():\n    return {previous_value}\n\ndef current():\n    return 2\n')
        objects = self.root / 'objects'
        frozen = snapshot_tree(candidate, objects)
        directory = self.root / 'submission'
        directory.mkdir()
        return self.verification(self.work, frozen, objects, directory, '新旧行为都正确')

    def test_new_feature_cannot_pass_by_breaking_a_previous_accepted_feature(self):
        """新需求通过而旧能力退化时，当前交付必须返工。:return: None。"""
        result = self.submit(0)
        self.assertEqual('failed', result['status'])
        self.assertEqual('passed', result['checks']['regression'])
        self.assertEqual('failed', result['checks']['previous_objectives'])
        self.assertEqual('FIRST', result['program']['previous_objectives'][0]['objective_id'])
        self.assertEqual(1, len(set(self.native.paths)))

    def test_one_frozen_candidate_preserves_both_real_features(self):
        """新旧两项实际能力均满足时同一冻结候选可通过。:return: None。"""
        result = self.submit(1)
        self.assertEqual('passed', result['status'])
        self.assertEqual('passed', result['checks']['previous_objectives'])
        self.assertEqual(3, len(self.native.paths))

    def test_historical_infrastructure_error_is_retried_without_becoming_business_failure(self):
        """历史能力检查无法执行时返回环境错误，不能算业务失败。:return: None。"""
        self.native.errors = 2
        result = self.submit(1)
        self.assertEqual('error', result['status'])
        self.assertEqual('error', result['checks']['previous_objectives'])

    def test_unverifiable_history_is_not_silently_ignored(self):
        """已接受记录与原冻结合同不同，拒绝省略检查。:return: None。"""
        self.old_work['definition_json'] = json.dumps({'id': 'FIRST'})
        with self.assertRaisesRegex(ValueError, '冻结合同'):
            self.submit(1)

    def test_progress_is_published_before_each_real_program_check(self):
        """用户在检查仍执行时即可看到当前阶段，事件只含公开操作信息。:return: None。"""
        events, observed = [], []
        self.verification.event = lambda *args: events.append(args)
        original = self.native.verify_native

        def verify(*args, **kwargs):
            """在实际独立进程启动前核对当前阶段。:param args: 验收参数。:param kwargs: 可选参数。:return: 程序结果。"""
            observed.append(events[-1][2])
            return original(*args, **kwargs)

        with patch.object(self.native, 'verify_native', side_effect=verify):
            result = self.submit(1)
        self.assertEqual('passed', result['status'])
        self.assertEqual(['business', 'regression', 'previous_objectives'], [item['stage'] for item in observed])
        self.assertEqual((1, 1), (observed[-1]['current'], observed[-1]['total']))
        self.assertEqual('finalize', events[-1][2]['stage'])
        self.assertTrue(all(event[0] == 1 and event[1] == 'verification_progress'
            and event[2]['submission_id'] == 'submission' and event[3] == 'new-work' for event in events))
        self.assertNotIn(str(self.root), json.dumps(events))

    def test_environment_retry_is_visible_without_claiming_completion(self):
        """环境故障重试显示实际次数，失败不发布最终成功阶段。:return: None。"""
        events = []
        self.verification.event = lambda *args: events.append(args[2])
        self.native.errors = 2
        result = self.submit(1)
        self.assertEqual('error', result['status'])
        self.assertEqual(2, events[-1]['attempt'])
        self.assertIn('重试', events[-1]['message'])
        self.assertNotIn('finalize', [item['stage'] for item in events])


if __name__ == '__main__':
    unittest.main()
