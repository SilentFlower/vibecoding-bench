"""验证固定画像的兼容选择、损坏拒绝和真实 CPU 字段保留。"""
import copy
import unittest

from system_profile import generate_system_profile, render_system_profile, validate_system_profile


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

    def test_unknown_mixed_or_changed_cpu_cannot_silently_select_another_profile(self) -> None:
        """不支持的宿主与迁移代际冲突都明确拒绝，不伪造能力。@return None。"""
        profile = generate_system_profile(self.cpuinfo)
        for cpu in ('', 'processor: 0\nmodel name: missing', self.cpuinfo.replace('23', '999'),
                self.cpuinfo + self.cpuinfo.replace('23', '25')):
            with self.subTest(cpu=cpu[:30]), self.assertRaises(ValueError):
                generate_system_profile(cpu)
        with self.assertRaisesRegex(ValueError, '代际冲突'):
            validate_system_profile(profile, self.cpuinfo.replace('cpu family\t: 23', 'cpu family\t: 25'))
