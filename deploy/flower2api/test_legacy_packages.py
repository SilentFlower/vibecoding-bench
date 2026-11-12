"""以合成包API验证三项旧包精确清理及失败恢复。"""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import legacy_packages as cleanup


class FakeApi:
    """记录真实调用顺序的合成GitHub包边界。"""

    def __init__(self):
        """初始化三项包及独立版本。:return: None。"""
        self.packages = {name: {'id': index + 1, 'name': name, 'package_type': 'container',
            'owner': {'login': 'SilentFlower'}, 'repository': {'full_name': cleanup.REPOSITORY},
            'version_count': 1} for index, name in enumerate(cleanup.TARGETS)}
        self.versions = {name: [{'id': 100 + index, 'name': 'sha256:' + str(index) * 64,
            'metadata': {'container': {'tags': ['latest', 'abc1234']}}}]
            for index, name in enumerate(cleanup.TARGETS)}
        self.calls = []
        self.denied = None
        self.fail_delete = None
        self.run = {'head_sha': 'a' * 40, 'event': 'workflow_dispatch', 'conclusion': 'success',
            'path': cleanup.WORKFLOW, 'head_branch': 'flower2api', 'repository': {'full_name': cleanup.REPOSITORY}}
        self.runs = {'workflow_runs': [], 'total_count': 0}

    def request(self, method, path):
        """执行合成请求并保留顺序。:param method: 方法。:param path: 路径。:return: 独立JSON副本。"""
        self.calls.append((method, path))
        if self.denied:
            raise cleanup.ApiError(self.denied)
        if '/actions/workflows/' in path:
            return copy.deepcopy(self.runs)
        if '/actions/runs/' in path:
            return copy.deepcopy(self.run)
        name = path.split('/container/', 1)[1].split('/', 1)[0].split('?', 1)[0]
        if method == 'DELETE':
            if name == self.fail_delete:
                raise cleanup.ApiError(403)
            if name not in self.packages:
                raise cleanup.ApiError(404)
            del self.packages[name]
            return None
        if name not in self.packages:
            raise cleanup.ApiError(404)
        if '/versions?' in path:
            return copy.deepcopy(self.versions[name])
        return copy.deepcopy(self.packages[name])


class LegacyPackageTests(unittest.TestCase):
    """对默认只读、冻结核验和逐项写入进行行为断言。"""

    def test_preview_reads_all_targets_and_does_not_delete(self):
        """完整预览读取全部包和版本，零写入。:return: None。"""
        api = FakeApi()
        plan = cleanup.preview(api, 'a' * 40, {})
        self.assertEqual([item['name'] for item in plan['packages']], list(cleanup.TARGETS))
        self.assertEqual(len(api.calls), 6)
        self.assertTrue(all(method == 'GET' for method, _ in api.calls))

    def test_permission_and_missing_package_fail_before_writes(self):
        """403和不可见404均拒绝形成删除计划。:return: None。"""
        for status in (403, 404):
            with self.subTest(status=status):
                api = FakeApi()
                api.denied = status
                with self.assertRaises(cleanup.ApiError):
                    cleanup.preview(api, 'a' * 40, {})
                self.assertFalse(any(method == 'DELETE' for method, _ in api.calls))

    def test_wrong_owner_repository_and_version_drift_reject(self):
        """错误归属与版本漂移在全部删除之前被拒绝。:return: None。"""
        for field in ('owner', 'repository', 'versions', 'evidence', 'revision'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                api = FakeApi()
                plan = cleanup.preview(api, 'a' * 40, {})
                target = cleanup.TARGETS[-1]
                if field == 'owner':
                    api.packages[target]['owner']['login'] = 'other'
                elif field == 'repository':
                    api.packages[target]['repository']['full_name'] = 'SilentFlower/other'
                elif field == 'versions':
                    api.versions[target][0]['metadata']['container']['tags'].append('new')
                elif field == 'evidence':
                    plan['reference_evidence_sha256'] = 'b' * 64
                else:
                    plan['revision'] = 'b' * 40
                with self.assertRaises(ValueError):
                    cleanup.apply(api, plan, Path(folder) / 'receipt.json', 'a' * 40, {})
                self.assertFalse(any(method == 'DELETE' for method, _ in api.calls))

    def test_all_protected_packages_and_arbitrary_names_are_rejected(self):
        """正式包与任意其他路径均不属于删除白名单。:return: None。"""
        for name in (*cleanup.PROTECTED, '../other', 'vibebench-sidecar/versions/1', 'other'):
            with self.assertRaises(ValueError):
                cleanup.package_path(name)

    def test_delete_has_positive_receipt_and_absence_check(self):
        """三项204删除与404复查均记录，其他包零触碰。:return: None。"""
        api = FakeApi()
        plan = cleanup.preview(api, 'a' * 40, {})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'receipt.json'
            result = cleanup.apply(api, plan, path, 'a' * 40, {})
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(len(result['deleted']), 3)
            self.assertTrue(all(item['delete_status'] == 204 and item['verified_absent'] for item in result['deleted']))
            self.assertEqual(json.loads(path.read_text()), result)
        self.assertEqual([path for method, path in api.calls if method == 'DELETE'],
            [cleanup.package_path(name) for name in cleanup.TARGETS])

    def test_partial_failure_preserves_receipt_and_stops_remaining(self):
        """第二包失败保留第一包收据，第三包保持存在。:return: None。"""
        api = FakeApi()
        api.fail_delete = cleanup.TARGETS[1]
        plan = cleanup.preview(api, 'a' * 40, {})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'receipt.json'
            with self.assertRaises(cleanup.ApiError):
                cleanup.apply(api, plan, path, 'a' * 40, {})
            result = json.loads(path.read_text())
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['failed'], cleanup.TARGETS[1])
            self.assertEqual(len(result['deleted']), 1)
            self.assertTrue(result['deleted'][0]['verified_absent'])
        self.assertIn(cleanup.TARGETS[2], api.packages)

    def test_preview_origin_binds_source_workflow_event_and_repository(self):
        """篡改来源SHA、事件或仓库均拒绝，合法同源预览通过。:return: None。"""
        api = FakeApi()
        plan = cleanup.preview(api, 'a' * 40, {})
        cleanup.validate_origin(api, plan, '123')
        for key in ('head_sha', 'event', 'path', 'head_branch', 'conclusion', 'repository'):
            with self.subTest(key=key):
                original = api.run[key]
                api.run[key] = {'full_name': 'other'} if key == 'repository' else 'other'
                with self.assertRaises(ValueError):
                    cleanup.validate_origin(api, plan, '123')
                api.run[key] = original

    def test_reference_check_requires_fresh_complete_zero_reference_evidence(self):
        """陈旧、未来或仍被引用的宿主核验保持失败。:return: None。"""
        now = datetime.now(timezone.utc)
        value = {'schema_version': 1, 'checked_at': now.isoformat(), 'container_count': 15,
            'legacy_references': [], 'protected_packages': list(cleanup.PROTECTED)}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'evidence.json'
            path.write_text(json.dumps(value))
            self.assertEqual(cleanup.reference_evidence(path, now=now), value)
            for delta in (timedelta(days=2), timedelta(seconds=-1)):
                with self.assertRaises(ValueError):
                    cleanup.reference_evidence(path, now=now + delta)
            value['legacy_references'] = ['vibebench-worker:latest']
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                cleanup.reference_evidence(path, now=now)

    def test_retired_workflow_and_active_legacy_run_protection(self):
        """退役标记及全部在途旧发布均核验。:return: None。"""
        api = FakeApi()
        cleanup.check_retirement(api, cleanup.ROOT)
        api.runs['workflow_runs'] = [{'status': 'queued'}]
        with self.assertRaises(ValueError):
            cleanup.check_retirement(api, cleanup.ROOT)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / '.github/workflows/docker-publish.yml'
            path.parent.mkdir(parents=True)
            path.write_text('LEGACY_IMAGES_RETIRED\nuses: docker/build-push-action@v7')
            with self.assertRaises(ValueError):
                cleanup.check_retirement(FakeApi(), root)


if __name__ == '__main__':
    unittest.main()
