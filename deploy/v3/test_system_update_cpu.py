"""更新器在新旧平台重建后保留CPU实际额度的宿主边界验证。"""
import copy
import json
import unittest
from unittest.mock import patch

from system_update_host import HostDeployment


class SystemUpdateCpuTests(unittest.TestCase):
    """直接执行宿主归属、资源及生命周期校验。"""

    def setUp(self):
        """构造三个已核验的角色。@return None。"""
        self.host = HostDeployment.__new__(HostDeployment)
        self.host.policy = {'deployment': 'test'}
        self.environment = {'environment_id': 'a'*32, 'roles': {}}
        self.objects, self.calls = {}, []
        for role, label in [('cli', 'account'), ('sender', 'account-sender'), ('network', 'account-network')]:
            identifier = role+'-id'
            self.environment['roles'][role] = {'id': identifier, 'image_id': 'synthetic-image'}
            self.objects[identifier] = {'Id': identifier, 'Image': 'synthetic-image',
                'Config': {'Labels': {'vibebench.product': 'v3', 'vibebench.deployment': 'test',
                    'vibebench.environment': 'a'*32, 'vibebench.role': label, 'vibebench.isolation-version': '2'}},
                'HostConfig': {'NanoCpus': 250000000, 'Memory': 100, 'MemorySwap': 200, 'PidsLimit': 128},
                'State': {'StartedAt': 'synthetic-start'}, 'RestartCount': 0}
        def docker(*arguments):
            self.calls.append(arguments)
            if arguments[0] == 'inspect':
                return json.dumps([self.objects[arguments[1]]])
            self.assertEqual(arguments[:2], ('update', '--cpus'))
            self.objects[arguments[3]]['HostConfig']['NanoCpus'] = round(float(arguments[2])*1_000_000_000)
            return arguments[3]
        self.patch = patch('system_update_host.docker', side_effect=docker)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_recreated_old_runtime_roles_restore_the_frozen_custom_quotas(self):
        """目标旧程序采用默认值时，宿主仍恢复原动态额度。@return None。"""
        frozen = {'cli': 2000000000, 'sender': 1000000000, 'network': 500000000}
        before = copy.deepcopy(self.objects)
        self.assertEqual(self.host.environment_cpu(self.environment), dict.fromkeys(frozen, 250000000))
        self.assertEqual(self.host.environment_cpu(self.environment, frozen), frozen)
        for role, value in frozen.items():
            expected = before[role+'-id']
            expected['HostConfig']['NanoCpus'] = value
            self.assertEqual(self.objects[role+'-id'], expected)
        updates = len([call for call in self.calls if call[0] == 'update'])
        self.host.environment_cpu(self.environment, frozen)
        self.assertEqual(len([call for call in self.calls if call[0] == 'update']), updates)

    def test_update_freezes_cpu_before_rebuild_and_restores_new_owned_roles(self):
        """真实更新方法先持久冻结CPU，再恢复重建后的新角色。@return None。"""
        current = copy.deepcopy(self.environment)
        current.update(generation=14, origin={'release':'old'})
        expected = {'cli':2000000000,'sender':1000000000,'network':500000000}
        for role in current['roles']:
            current['roles'][role]['state'] = 'running'
            self.objects[role+'-id']['HostConfig']['NanoCpus'] = expected[role]
        selected = {'selection':{'account':{'content_sha256':'new-content','release':'new'}}}
        operation = {'original':{'selection':{'account':{'content_sha256':'old-content'}}},
            'before':{'environments':[copy.deepcopy(current)]},'operation_id':'synthetic-op','epoch':'synthetic-epoch'}
        self.host.drained = lambda value: {'ready':True,'environments':[copy.deepcopy(current)]}
        self.host.verify_images = lambda value: {'account':{'Id':'new-image'}}
        rebuilt = copy.deepcopy(current)
        rebuilt.update(generation=15,origin={'release':'new'})
        calls, saved = [], []
        def request(service, path, body, **options):
            calls.append(path)
            if path.endswith('/environment'):
                self.assertEqual(operation['environment_cpu_before'][current['environment_id']],expected)
                for role in current['roles']:
                    identifier = 'new-'+role
                    info = copy.deepcopy(self.objects[role+'-id'])
                    info.update(Id=identifier,Image='new-image')
                    info['HostConfig']['NanoCpus'] = 250000000
                    info['State']['StartedAt'] = 'new-start'
                    self.objects[identifier] = info
                    rebuilt['roles'][role].update(id=identifier,image_id='new-image')
                return {'ok':True}
            return {'environments':[rebuilt]}
        self.host.request = request
        self.host.update_environments(operation,selected,lambda:saved.append(copy.deepcopy(operation)))
        self.assertEqual(saved[0]['environment_cpu_before'][current['environment_id']],expected)
        self.assertEqual([self.objects['new-'+role]['HostConfig']['NanoCpus'] for role in expected],list(expected.values()))
        self.assertEqual(calls,['/internal/v3/system-updates/environment','/internal/v3/system-updates/snapshot'])

    def test_wrong_ownership_and_incomplete_evidence_fail_before_any_update(self):
        """归属冲突与缺少CPU证据都拒绝更新。@return None。"""
        frozen = dict.fromkeys(('cli', 'sender', 'network'), 1000000000)
        self.objects['sender-id']['Config']['Labels']['vibebench.environment'] = 'other'
        with self.assertRaisesRegex(ValueError, '归属'):
            self.host.environment_cpu(self.environment, frozen)
        with self.assertRaisesRegex(ValueError, '证据'):
            self.host.environment_cpu(self.environment, {'cli': 1000000000})
        self.assertFalse(any(call[0] == 'update' for call in self.calls))
