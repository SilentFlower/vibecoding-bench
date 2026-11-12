"""校验实际工作流的事件、权限与发布步骤边界。"""
import unittest
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from install_system_updater import SOURCE_FILES


ROOT = Path(__file__).resolve().parents[2]


class WorkflowTests(unittest.TestCase):
    """对真实 YAML 验证构建零发布和手动发行前置条件。"""

    def workflow(self, filename: str) -> dict:
        """读取 YAML，保留 on 与布尔字面值。

        :param filename: 精确工作流文件名。
        :return: 解析后的结构。
        """
        return yaml.load((ROOT / '.github/workflows' / filename).read_text(), Loader=yaml.BaseLoader)

    def test_build_has_no_publish_permissions_secrets_or_commands(self) -> None:
        """自动或手动构建均无发布步骤及写权限。@return None。"""
        value = self.workflow('v3-build.yml')
        self.assertEqual(set(value['on']), {'push', 'pull_request', 'workflow_dispatch'})
        for event in ('push', 'pull_request'):
            self.assertEqual(value['on'][event]['branches'], ['v3', 'flower2api'])
        self.assertEqual(value['permissions'], {'contents': 'read'})
        for job in value['jobs'].values():
            self.assertNotIn('permissions', job)
            for step in job['steps']:
                text = str(step)
                for forbidden in ('secrets.', 'docker/login-action', 'docker push', 'gh release',
                        'publish_system_release.py', 'manage.py publish', 'git push'):
                    self.assertNotIn(forbidden, text)
        checkout = value['jobs']['build']['steps'][0]
        self.assertEqual(checkout['with']['persist-credentials'], 'false')

    def test_release_requires_explicit_input_and_same_batch_verification(self) -> None:
        """正式发布仅有手动入口，签名预检与兼容演练先于推送。@return None。"""
        value = self.workflow('v3-release.yml')
        self.assertEqual(set(value['on']), {'workflow_dispatch'})
        publish = value['on']['workflow_dispatch']['inputs']['publish']
        self.assertEqual(publish['type'], 'boolean')
        self.assertEqual(publish['default'], 'false')
        job = value['jobs']['release']
        for required in ('workflow_dispatch', 'inputs.publish', 'refs/heads/v3', 'refs/heads/flower2api',
                'SilentFlower/vibecoding-bench'):
            self.assertIn(required, job['if'])
        self.assertEqual(job['concurrency'], {'group': 'v3-signed-system-release', 'cancel-in-progress': 'false'})
        runs = [step.get('run', '') for step in job['steps']]
        preflight = next(i for i, run in enumerate(runs) if '--check-signing' in run)
        build = next(i for i, run in enumerate(runs) if 'manage.py build' in run)
        verify = next(i for i, run in enumerate(runs) if 'verify_database_compatibility.py' in run)
        publish = next(i for i, run in enumerate(runs) if 'manage.py publish' in run)
        self.assertLess(preflight, build)
        self.assertLess(build, verify)
        self.assertLess(verify, publish)
        self.assertNotIn('if [', runs[verify])
        build_runs = [step.get('run', '') for step in self.workflow('v3-build.yml')['jobs']['build']['steps']]
        self.assertIn(runs[build], build_runs)
        validation = next(run for run in runs if 'unittest discover' in run)
        self.assertIn(validation, build_runs)
        for required in ('test_publication', 'test_system_workflow', 'test_database_compatibility'):
            self.assertIn(required, validation)

    def test_legacy_main_publish_is_manual(self) -> None:
        """main 的旧交付仍须手动触发。@return None。"""
        value = self.workflow('docker-publish.yml')
        self.assertEqual(set(value['on']), {'workflow_dispatch'})
        self.assertIn('workflow_dispatch', value['jobs']['publish']['if'])
        self.assertIn('refs/heads/main', value['jobs']['publish']['if'])

    def test_frozen_updater_can_import_build_helpers(self) -> None:
        """固定源码包在仓库外独立导入，避免依赖只在开发树中可用。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in SOURCE_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            result = subprocess.run([sys.executable, '-I', '-c',
                'import sys; sys.path.insert(0, sys.argv[1]); import manage, system_updater',
                str(root / 'deploy/v3')], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
