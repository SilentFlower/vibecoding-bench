"""用合成凭据和线程屏障验证账号发布串行性，不接触真实账号或刷新接口。"""
import json
import threading
import unittest
from unittest.mock import patch

import test_account_runtime
from account_isolation import ISOLATION_VERSION
from account_runtime import atomic_json


class CredentialPublicationTests(unittest.TestCase):
    """同账号读取到全部副本发布连续互斥，不同账号可以独立前进。"""

    def setUp(self):
        """复用临时数据库和假容器，所有凭据均为本测试新建合成值。:return: None。"""
        test_account_runtime.AccountRuntimeTests.setUp(self)

    def fixture(self, account_id=1, name='synthetic'):
        """创建固定账号的三份发布目的地。:param account_id: 合成账号ID。:param name: 合成名称。:return: 账号、环境、管理凭据路径和目的地。"""
        if account_id != 1:
            with self.database() as connection:
                connection.execute('INSERT INTO accounts(id,name,cc2api_account_id) VALUES(?,?,?)',
                    (account_id, name, 7 + account_id))
        account = {'id': account_id, 'name': name, 'cc2api_account_id': 7 if account_id == 1 else 7 + account_id}
        row = self.runtime._row(name, account_id)
        row['isolation_version'] = ISOLATION_VERSION
        profile = self.root / 'profiles' / name / '.credentials.json'
        destinations = [self.runtime._root(row) / 'home/.claude/.credentials.json',
            self.runtime._root(row) / 'runtime/access/.credentials.json',
            self.runtime._network_runtime(row) / 'access/.credentials.json']
        atomic_json(profile, self.credentials('old'))
        return account, row, profile, destinations

    @staticmethod
    def credentials(version):
        """生成可辨识的合成轮换快照。:param version: 合成版本。:return: 仅供临时文件使用的字典。"""
        return {'claudeAiOauth': {'accessToken': 'synthetic-at-' + version,
            'refreshToken': 'synthetic-rt-' + version, 'expiresAt': 2000 if version == 'new' else 1000}}

    def test_delayed_old_reader_cannot_overwrite_new_three_copies(self):
        """把旧发布停在首次替换前，新权威随后到达，最终三副本必须为新AT且没有RT。:return: None。"""
        account, row, profile, destinations = self.fixture()
        captured, resume, attempted, finished = (threading.Event() for _ in range(4))
        errors = []

        def publish():
            try:
                attempted.set()
                self.runtime.sync_credentials(row, account)
            except Exception as error:
                errors.append(type(error).__name__)
            finally:
                finished.set()

        def write(path, value, *args, **kwargs):
            if threading.current_thread().name == 'delayed-old' and path == destinations[0]:
                captured.set()
                if not resume.wait(3):
                    raise TimeoutError('合成线程屏障超时')
            return atomic_json(path, value, *args, **kwargs)

        with patch('account_runtime.atomic_json', side_effect=write):
            old = threading.Thread(target=publish, name='delayed-old')
            fresh = threading.Thread(target=publish, name='fresh-publisher')
            old.start()
            try:
                self.assertTrue(captured.wait(2))
                atomic_json(profile, self.credentials('new'))
                attempted.clear()
                fresh.start()
                self.assertTrue(attempted.wait(2))
                # 旧实现会让新线程先写完，再被迟到旧快照覆盖；发布锁让新线程完整排在旧线程之后。
                finished.wait(.2)
            finally:
                resume.set()
                old.join(3)
                if fresh.ident is not None:
                    fresh.join(3)
        self.assertFalse(old.is_alive() or fresh.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(self.credentials('new'), json.loads(profile.read_text()))
        for path in destinations:
            oauth = json.loads(path.read_text())['claudeAiOauth']
            self.assertEqual('synthetic-at-new', oauth['accessToken'])
            self.assertEqual(2000, oauth['expiresAt'])
            self.assertNotIn('refreshToken', oauth)

    def test_other_account_does_not_wait_for_blocked_publisher(self):
        """一个账号磁盘发布等待时，另一个账号仍能完成三副本发布。:return: None。"""
        account, row, _, destinations = self.fixture()
        other, other_row, _, other_destinations = self.fixture(2, 'synthetic-other')
        captured, resume, finished = (threading.Event() for _ in range(3))
        errors = []

        def write(path, value, *args, **kwargs):
            if path == destinations[0]:
                captured.set()
                if not resume.wait(3):
                    raise TimeoutError('合成线程屏障超时')
            return atomic_json(path, value, *args, **kwargs)

        def publish(current, current_row, completion=None):
            try:
                self.runtime.sync_credentials(current_row, current)
            except Exception as error:
                errors.append(type(error).__name__)
            finally:
                if completion:
                    completion.set()

        with patch('account_runtime.atomic_json', side_effect=write):
            blocked = threading.Thread(target=publish, args=(account, row))
            independent = threading.Thread(target=publish, args=(other, other_row, finished))
            blocked.start()
            try:
                self.assertTrue(captured.wait(2))
                independent.start()
                self.assertTrue(finished.wait(2), '不同账号不应共用长时发布锁')
            finally:
                resume.set()
                blocked.join(3)
                if independent.ident is not None:
                    independent.join(3)
        self.assertFalse(blocked.is_alive() or independent.is_alive())
        self.assertEqual([], errors)
        self.assertTrue(all(path.is_file() for path in other_destinations))

    def test_unbound_home_keeps_its_rotated_refresh_token(self):
        """未绑定账号仍以完整HOME为本地权威，旧管理副本不覆盖已轮换RT。:return: None。"""
        account, row, profile, destinations = self.fixture()
        account['cc2api_account_id'] = None
        rotated = self.credentials('new')
        atomic_json(destinations[0], rotated)
        self.runtime.sync_credentials(row, account)
        self.assertEqual(rotated, json.loads(destinations[0].read_text()))
        self.assertEqual(rotated, json.loads(destinations[1].read_text()))
        self.assertNotIn('refreshToken', json.loads(destinations[2].read_text())['claudeAiOauth'])
        self.assertEqual(self.credentials('old'), json.loads(profile.read_text()))

    def test_failed_publish_releases_lock_for_next_fresh_snapshot(self):
        """某次磁盘替换失败后释放发布锁，下一次可重新发布最新完整快照。:return: None。"""
        account, row, profile, destinations = self.fixture()
        with patch('account_runtime.atomic_json', side_effect=OSError('合成磁盘错误')):
            with self.assertRaises(OSError):
                self.runtime.sync_credentials(row, account)
        atomic_json(profile, self.credentials('new'))
        self.runtime.sync_credentials(row, account)
        self.assertTrue(all(json.loads(path.read_text())['claudeAiOauth']['accessToken'] == 'synthetic-at-new'
            for path in destinations))


if __name__ == '__main__':
    unittest.main()
