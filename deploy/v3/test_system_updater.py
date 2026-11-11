"""真实签名及持久文件下的更新、回退、中断恢复与 socket 边界验证。"""
import copy
import hashlib
import json
import os
import shutil
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import system_updater
from system_release import create_index, create_release, sign_file
from system_updater import SystemUpdater, UpdateConflict, UpdateHTTPHandler, UpdateServer
from system_updates import UnixUpdateConnection
from runtime_files import atomic_json, atomic_text
import test_system_release as release_tests


class FakeDeployment:
    """只模拟宿主边界，实际签名、持久状态及幂等逻辑均执行生产实现。"""

    def __init__(self) -> None:
        """初始化可注入故障。

        :return: None。
        """
        self.calls = []
        self.fail = None
        self.blocked = False
        self.ready = True

    def prepare(self, *args):
        """记录准备。:param args: 生产参数。@return None。"""
        self.calls.append('prepare')
        if self.fail == 'prepare':
            raise ValueError('合成下载失败')

    def capture(self, *args):
        """冻结合成现场。:param args: 原版。@return 现场。"""
        return {'controls': {}, 'environments': [], 'metadata': {}, 'env_sha256': 'a' * 64}

    def block(self, *args):
        """模拟持久关闭。:param args: 原操作。@return None。"""
        self.calls.append('block')
        self.blocked = True

    def drained(self, *args):
        """读取实际模拟活动。:param args: 原操作。@return 快照。"""
        self.calls.append('drained')
        return {'ready': self.ready, 'blockers': [] if self.ready else ['合成长流未结束'], 'environments': []}

    def switch(self, *args):
        """记录切换。:param args: 原操作及目标。@return None。"""
        self.calls.append('switch')
        if self.fail == 'switch':
            raise ValueError('合成切换失败')

    def wait_controls(self, *args):
        """模拟控制启动。:param args: 截止。@return None。"""

    def update_environments(self, *args):
        """模拟环境收口。:param args: 原操作和回调。@return None。"""
        self.calls.append('environments')

    def health(self, *args):
        """模拟验收失败。:param args: 原操作及目标。@return None。"""
        self.calls.append('health')
        if self.fail == 'health':
            raise ValueError('合成验收失败')

    def release(self, *args):
        """模拟本操作释放。:param args: 原操作。@return None。"""
        self.calls.append('release')
        self.blocked = False

    def abandon(self, *args):
        """取消保持原任务继续。:param args: 原操作。@return None。"""
        self.calls.append('abandon')
        self.blocked = False

    def restore(self, *args):
        """模拟恢复。:param args: 原操作及回调。@return None。"""
        self.calls.append('restore')
        if self.fail == 'restore':
            raise ValueError('合成恢复待对账')
        self.blocked = False

    def committed(self, *args):
        """核对已提交现场。:param args: 原操作。@return 当前已提交。"""
        self.calls.append('committed')
        self.blocked = False
        return True

    def cleanup(self, *args):
        """模拟定向清理。:param args: 安装及保留记录。@return 结果。"""
        self.calls.append('cleanup')
        if self.fail == 'cleanup':
            raise ValueError('合成回收失败')
        return {'status': 'passed', 'removed': []}


class SystemUpdaterTests(unittest.TestCase):
    """验证状态机、幂等和故障恢复的实际持久合同。"""

    def setUp(self) -> None:
        """建立包含两个真实签名版本的首次安装。

        :return: None。
        """
        fixture = release_tests.SystemReleaseTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root / 'updater'
        (self.root / 'releases').mkdir(parents=True)
        (self.root / 'operations').mkdir()
        (self.root / 'socket').mkdir()
        data = fixture.root / 'business'
        data.mkdir()
        self.old = fixture.release
        shutil.copytree(fixture.output, self.root / 'releases' / self.old['release'])
        fixture.build['release'] = 'ci-124-1'
        for role, entry in fixture.build['images'].items():
            entry['reference'] = f'ghcr.io/silentflower/vibebench-v3-{role}:v3-ci-124-1'
        fixture.manifest.write_text(json.dumps(fixture.build))
        self.target = create_release(fixture.manifest, fixture.policy, self.root / 'releases/system-ci-124-1', fixture.key, [11, 1], '新版')
        catalog = create_index(self.root / 'releases/system-ci-124-1/system-release.json', None, fixture.root / 'catalog.json', fixture.key)
        compose = fixture.root / 'compose.yml'
        override = fixture.root / 'override.yml'
        env = fixture.root / 'v3.env'
        compose.write_text('services: {}')
        override.write_text('services: {}')
        atomic_text(env, 'V3_DEPLOYMENT_ID=test\n')
        self.policy = {'schema_version': 1, 'deployment': 'test', 'data_root': str(data),
            'env_file': str(env), 'state_root': str(self.root), 'public_key': fixture.public,
            'compose_file': str(compose), 'compose_file_sha256': hashlib.sha256(compose.read_bytes()).hexdigest(),
            'override_file': str(override), 'override_file_sha256': hashlib.sha256(override.read_bytes()).hexdigest()}
        installed = {'release': self.old, 'selection': {role: self.old[role] for role in ('control', 'account')}, 'installed_at': '2026-11-11T00:00:00Z'}
        atomic_json(self.root / 'state.json', {'schema_version': 1, 'deployment': 'test',
            'revision': str(uuid.uuid4()), 'current': installed, 'history': [], 'active_operation': None, 'catalog': catalog})
        self.backend = FakeDeployment()
        self.engine = SystemUpdater(self.policy, self.backend)

    def request(self, release: dict | None = None) -> dict:
        """冻结当前实际版本。

        :param release: 目标，默认新版。
        :return: 合法请求。
        """
        target = release or self.target
        return {'operation_id': str(uuid.uuid4()), 'expected_revision': self.engine.status()['revision'],
            'target_release': target['release'],
            'target_manifest_sha256': hashlib.sha256((self.root / 'releases' / target['release'] / 'system-release.json').read_bytes()).hexdigest(),
            'drain_timeout_seconds': 900}

    def join(self) -> dict:
        """等候本地有限工作完成。

        :return: 公开状态。
        """
        self.engine.worker.join(10)
        self.assertFalse(self.engine.worker.is_alive())
        return self.engine.status()

    def test_install_idempotence_and_compatible_account_reuse(self) -> None:
        """一次切换且旧账号来源继续保留，迟到的更旧现场请求拒绝。

        :return: None。
        """
        body = self.request()
        self.engine.submit('install', body)
        state = self.join()
        self.assertEqual(state['operation']['phase'], 'succeeded')
        self.assertEqual(state['current_release'], self.target['release'])
        self.assertEqual(state['components']['account']['release'], 'ci-123-1')
        self.assertEqual(self.backend.calls.count('switch'), 1)
        self.assertEqual(self.engine.submit('install', body)['operation_id'], body['operation_id'])
        with self.assertRaises(UpdateConflict):
            self.engine.submit('install', {**body, 'drain_timeout_seconds': 60})
        rollback = self.request(self.old)
        self.engine.submit('rollback', rollback)
        self.assertEqual(self.join()['current_release'], self.old['release'])
        with self.assertRaises(UpdateConflict):
            self.engine.submit('install', body)

    def test_prepare_failure_keeps_current_and_gate_open(self) -> None:
        """准备失败保持原安装，维护副作用为零。

        :return: None。
        """
        self.backend.fail = 'prepare'
        self.engine.submit('install', self.request())
        state = self.join()
        self.assertEqual(state['operation']['phase'], 'failed')
        self.assertEqual(state['current_release'], self.old['release'])
        self.assertFalse(self.backend.blocked)
        self.assertNotIn('switch', self.backend.calls)

    def test_expired_catalog_does_not_authorize_installation(self) -> None:
        """已验签缓存过期后提示仍可读，安装必须重新检查。@return None。"""
        self.engine.state['catalog']['expires_at'] = '2000-01-01T00:00:00Z'
        self.assertFalse(self.engine.releases()['fresh'])
        with self.assertRaises(ValueError):
            self.engine.submit('install', self.request())
        self.assertFalse(self.backend.calls)

    def test_long_multibyte_release_history_survives_restart(self) -> None:
        """合法中文说明及完整保留窗口在重启读取时保持可用。@return None。"""
        old = copy.deepcopy(self.old)
        old['changes'] = '更' * 8000
        folder = self.root / 'releases' / old['release']
        atomic_json(folder / 'system-release.json', old)
        (folder / 'system-release.sig').unlink()
        sign_file(folder / 'system-release.json', self.fixture.key)
        state = copy.deepcopy(self.engine.state)
        state['current']['release'] = old
        state['history'] = [copy.deepcopy(state['current']) for _ in range(64)]
        atomic_json(self.root / 'state.json', state)
        self.assertGreater((self.root / 'state.json').stat().st_size, 1024 * 1024)
        restored = SystemUpdater(self.policy, self.backend)
        self.assertEqual(restored.status()['current_release'], old['release'])

    def test_failed_health_restores_original(self) -> None:
        """候选验收失败后完成原版恢复。

        :return: None。
        """
        self.backend.fail = 'health'
        self.engine.submit('install', self.request())
        state = self.join()
        self.assertEqual(state['operation']['phase'], 'restored')
        self.assertEqual(state['current_release'], self.old['release'])
        self.assertIn('restore', self.backend.calls)
        self.assertFalse(self.backend.blocked)

    def test_cleanup_failure_keeps_verified_target(self) -> None:
        """回收失败和服务安装结果分别记录。

        :return: None。
        """
        self.backend.fail = 'cleanup'
        self.engine.submit('install', self.request())
        state = self.join()
        self.assertEqual(state['operation']['phase'], 'succeeded_cleanup_pending')
        self.assertEqual(state['current_release'], self.target['release'])
        self.assertFalse(self.backend.blocked)
        self.backend.fail = None
        self.engine.control(state['operation']['operation_id'], 'recover', {'expected_revision': state['revision']})
        self.assertEqual(self.join()['operation']['phase'], 'succeeded')
        self.assertEqual(self.backend.calls.count('switch'), 1)

    def test_drain_timeout_releases_only_original_operation(self) -> None:
        """排空截止后原工作可继续，控制切换为零。

        :return: None。
        """
        self.backend.ready = False
        times = iter([0, 1000])
        with patch.object(system_updater, 'time', SimpleNamespace(monotonic=lambda: next(times), sleep=lambda _: None)):
            self.engine.submit('install', self.request())
            state = self.join()
        self.assertEqual(state['operation']['phase'], 'failed')
        self.assertIn('abandon', self.backend.calls)
        self.assertNotIn('switch', self.backend.calls)
        self.assertFalse(self.backend.blocked)

    def test_restart_before_switch_recovers_without_repeating_install(self) -> None:
        """切换前持久中断在重启后收口，原版保持。

        :return: None。
        """
        body = self.request()
        with patch.object(self.engine, '_execute'):
            self.engine.submit('install', body)
            self.engine.worker.join(1)
        operation = self.engine._operation(body['operation_id'])
        operation['before'] = self.backend.capture(self.engine.state['current'])
        self.engine._phase(operation, 'draining')
        self.backend.block(operation)
        restored = SystemUpdater(self.policy, self.backend)
        restored.resume()
        restored.worker.join(3)
        self.assertEqual(restored.status()['operation']['phase'], 'failed')
        self.assertFalse(self.backend.blocked)
        self.assertNotIn('switch', self.backend.calls)

    def test_socket_auth_and_frozen_contract(self) -> None:
        """真实私有 HTTP 拒绝无令牌及未知字段，并读取同一持久状态。

        :return: None。
        """
        path = self.root / 'socket/updater.sock'
        server = UpdateServer(str(path), UpdateHTTPHandler)
        server.token, server.engine = 'a' * 64, self.engine
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            connection = UnixUpdateConnection(path)
            connection.request('GET', '/status')
            self.assertEqual(connection.getresponse().status, 403)
            connection.close()
            connection = UnixUpdateConnection(path)
            connection.request('GET', '/status', headers={'Authorization': 'Bearer ' + server.token})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['current_release'], self.old['release'])
            connection.close()
            connection = UnixUpdateConnection(path)
            connection.request('POST', '/install', body=json.dumps({**self.request(), 'command': 'forbidden'}),
                headers={'Authorization': 'Bearer ' + server.token})
            self.assertEqual(connection.getresponse().status, 400)
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)


if __name__ == '__main__':
    unittest.main()
