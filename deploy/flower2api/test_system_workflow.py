"""校验实际工作流的事件、权限与发布步骤边界。"""
import unittest
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from source_layout import source_path

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
        """历史入口保留明确退役说明，写权限和镜像发布步骤归零。@return None。"""
        value = self.workflow('docker-publish.yml')
        self.assertEqual(set(value['on']), {'workflow_dispatch'})
        self.assertIn('workflow_dispatch', value['jobs']['publish']['if'])
        self.assertIn('refs/heads/main', value['jobs']['publish']['if'])
        self.assertEqual(value['permissions'], {'contents': 'read'})
        self.assertIn('LEGACY_IMAGES_RETIRED', str(value))
        for forbidden in ('packages', 'docker/build-push-action', 'docker/login-action', 'matrix', 'docker push'):
            self.assertNotIn(forbidden, str(value))

    def test_package_cleanup_requires_exact_preview_and_trusted_manual_branch(self) -> None:
        """清理默认预览，仅受信手动分支可应用带运行和摘要的计划。@return None。"""
        value = self.workflow('ghcr-legacy-cleanup.yml')
        self.assertEqual(set(value['on']), {'workflow_dispatch'})
        self.assertEqual(value['on']['workflow_dispatch']['inputs']['apply']['default'], 'false')
        self.assertEqual(value['permissions'], {'contents': 'read'})
        job = value['jobs']['cleanup']
        for expected in ('workflow_dispatch', 'SilentFlower/vibecoding-bench', 'refs/heads/flower2api'):
            self.assertIn(expected, job['if'])
        self.assertEqual(job['permissions'], {'contents': 'read', 'actions': 'read', 'packages': 'write'})
        commands = '\n'.join(step.get('run', '') for step in job['steps'])
        for expected in ('--plan-run', '--plan-sha256', 'legacy_packages.py', 'legacy-package-preview'):
            self.assertIn(expected, commands)
        self.assertFalse(any('${{' in step.get('run', '') for step in job['steps']))
        self.assertEqual(value['concurrency']['cancel-in-progress'], 'false')

    def test_frozen_updater_can_import_build_helpers(self) -> None:
        """固定源码包在仓库外独立导入，避免依赖只在开发树中可用。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in SOURCE_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path(ROOT, name), target)
            result = subprocess.run([sys.executable, '-I', '-c',
                'import sys; sys.path.insert(0, sys.argv[1]); import manage, system_updater',
                str(root / 'deploy/v3')], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_git_preserves_frozen_resource_bytes_and_patch_context(self) -> None:
        """工程库入库时保留原始换行与验证补丁上下文。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copyfile(ROOT / '.gitattributes', root / '.gitattributes')
            subprocess.run(['git', '-c', 'init.defaultBranch=main', 'init', '-q'],
                cwd=root, check=True, capture_output=True)
            resource = 'resources/project-library/projects/fixture/seed/library/CRLF.csv'
            patch = 'resources/project-library/projects/fixture/verification/fixture.patch'
            content = b'field,value\r\none,two\r\n'
            (root / resource).parent.mkdir(parents=True)
            (root / resource).write_bytes(content)
            (root / patch).parent.mkdir(parents=True)
            # 空白上下文是补丁格式的一部分，必须沿用工程库的精确字节约定。
            (root / patch).write_bytes(b' context\n \n+added\n')
            subprocess.run(['git', '-c', 'core.autocrlf=input', 'add', '-f', '--',
                '.gitattributes', resource, patch], cwd=root, check=True, capture_output=True)
            stored = subprocess.run(['git', 'show', ':' + resource], cwd=root,
                check=True, capture_output=True)
            self.assertEqual(stored.stdout, content)
            checked = subprocess.run(['git', 'diff', '--cached', '--check', '--', patch],
                cwd=root, capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)


if __name__ == '__main__':
    unittest.main()
