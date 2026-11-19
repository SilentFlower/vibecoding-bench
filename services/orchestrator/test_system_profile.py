"""验证固定画像的兼容选择、损坏拒绝和真实 CPU 字段保留。"""
import copy
import unittest
from uuid import UUID

from system_profile import (DMI_FIELDS, generate_computer_profile, generate_system_profile, render_computer_profile,
    render_system_profile, validate_computer_profile, validate_system_profile)


class SystemProfileTests(unittest.TestCase):
    """保护模板持久性及真实硬件能力边界。"""

    def setUp(self) -> None:
        """准备两个逻辑 CPU 的合成样本。@return None。"""
        block = ('processor\t: {index}\nvendor_id\t: AuthenticAMD\ncpu family\t: 23\nmodel\t\t: 1\n'
            'model name\t: AMD EPYC Processor\nstepping\t: 2\ncpu cores\t: 1\nflags\t\t: sse sse2 avx2\n\n')
        self.cpuinfo = ''.join(block.format(index=index) for index in range(2))

    def test_render_keeps_all_real_cpu_fields_except_model_name(self) -> None:
        """型号覆盖不能附带修改指令集、核心数或其它实际字段。@return None。"""
        profile = generate_system_profile(self.cpuinfo)
        files = render_system_profile(profile, self.cpuinfo)
        before = [line for line in self.cpuinfo.splitlines() if not line.startswith('model name')]
        after = [line for line in files['cpuinfo'].splitlines() if not line.startswith('model name')]
        self.assertEqual(before, after)
        self.assertEqual(2, files['cpuinfo'].count(profile['cpu_model_name']))
        self.assertIn(profile['kernel_release'], files['proc-version'])
        self.assertIn(profile['kernel_version'], files['proc-version'])
        self.assertEqual(profile, validate_system_profile(copy.deepcopy(profile), self.cpuinfo))

    def test_saved_profile_rejects_corruption_without_regeneration(self) -> None:
        """已保存对象中任何篡改都不能由合法模板 ID 掩盖。@return None。"""
        profile = generate_system_profile(self.cpuinfo)
        invalid = [None, [], {}, {**profile, 'schema': True}, {**profile, 'kernel_template_id': []},
            {**profile, 'kernel_release': 'unrelated'}, {**profile, 'cpu_model_name': 'other'},
            {**profile, 'extra': 'unsupported'}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_system_profile(value)

    def test_cross_host_cpu_preserves_saved_profile_and_real_capabilities(self) -> None:
        """跨代和跨厂商迁移保留画像，硬件能力沿目标实际值渲染。@return None。"""
        profile = generate_system_profile(self.cpuinfo)
        for cpu in ('', 'processor: 0\nmodel name: missing',
                self.cpuinfo + self.cpuinfo.replace('23', '25')):
            with self.subTest(cpu=cpu[:30]), self.assertRaises(ValueError):
                generate_system_profile(cpu)
        for vendor, family, model in [('AuthenticAMD', '26', '0'), ('GenuineIntel', '6', '143')]:
            target = self.cpuinfo.replace('AuthenticAMD', vendor).replace('family\t: 23', 'family\t: ' + family)
            target = target.replace('model\t\t: 1', 'model\t\t: ' + model).replace('sse sse2 avx2', 'sse sse2 avx avx2 avx512f')
            original = copy.deepcopy(profile)
            self.assertEqual(profile, validate_system_profile(profile, target))
            rendered = render_system_profile(profile, target)['cpuinfo']
            self.assertIn('avx512f', rendered)
            self.assertIn('family\t: ' + family, rendered)
            self.assertEqual(original, profile)

    def test_unregistered_cpu_uses_actual_model_and_portable_computer(self) -> None:
        """未知型号首次创建沿实际CPU，通用机型拥有独立持久身份。@return None。"""
        for vendor, family, model in [('AuthenticAMD', '26', '0'), ('GenuineIntel', '6', '143')]:
            cpu = self.cpuinfo.replace('AuthenticAMD', vendor).replace('family\t: 23', 'family\t: ' + family)
            cpu = cpu.replace('model\t\t: 1', 'model\t\t: ' + model)
            system = generate_system_profile(cpu)
            self.assertEqual([vendor, family, model], system['cpu_signature'])
            self.assertEqual('host-cpu-v1', system['cpu_template_id'])
            self.assertEqual(system, validate_system_profile(system, cpu))
            computer = generate_computer_profile(system)
            self.assertEqual('portable-computer-v1', computer['template_id'])
            self.assertEqual(computer, validate_computer_profile(computer, system))
            render_system_profile(system, cpu)
            for invalid in ({**system, 'cpu_model_name': 'bad\nmodel'}, {**system, 'cpu_signature': [vendor, family, 0]}):
                with self.assertRaises(ValueError):
                    validate_system_profile(invalid)

    def test_computer_identity_is_independent_and_matches_cpu_family(self) -> None:
        """两个 CPU 家族只选兼容机型，每次新身份的 UUID 和序列号各自独立。@return None。"""
        for cpu in (self.cpuinfo, self.cpuinfo.replace('family\t: 23', 'family\t: 25').replace('model\t\t: 1', 'model\t\t: 80')):
            system = generate_system_profile(cpu)
            first, second = generate_computer_profile(system), generate_computer_profile(system)
            self.assertEqual(first, validate_computer_profile(copy.deepcopy(first), system))
            self.assertEqual(set(DMI_FIELDS), set(first['dmi']))
            self.assertNotEqual(first['dmi']['uuid'], second['dmi']['uuid'])
            self.assertNotEqual(first['dmi']['serial'], second['dmi']['serial'])
            self.assertEqual(4, UUID(first['dmi']['uuid']).version)
            files = render_computer_profile(first, system)
            self.assertEqual('1\n', files['computer-profile-version'])
            self.assertEqual(first['dmi']['uuid'] + '\n', files['dmi/product_uuid'])

    def test_computer_corruption_and_cross_family_never_become_new_identity(self) -> None:
        """非法模板、字段及 UUID 必须拒绝，不能修复成另一套随机身份。@return None。"""
        system = generate_system_profile(self.cpuinfo)
        first = generate_computer_profile(system)
        invalid = [None, {}, {**first, 'schema': True}, {**first, 'template_id': []}, {**first, 'extra': 1}]
        for key, value in [('manufacturer', 'other'), ('serial', 'bad\nserial'), ('uuid', '0' * 32), ('uuid', None)]:
            invalid.append({**first, 'dmi': {**first['dmi'], key: value}})
        invalid.append({**first, 'dmi': {**first['dmi'], 'extra': 'unexpected'}})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_computer_profile(value, system)
        changed = generate_system_profile(self.cpuinfo.replace('family\t: 23', 'family\t: 25').replace('model\t\t: 1', 'model\t\t: 80'))
        with self.assertRaises(ValueError):
            validate_computer_profile(first, changed)
