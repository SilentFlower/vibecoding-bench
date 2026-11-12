"""验证可选缓存驱动与实际工作流的信任、隔离和回退合同。"""
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import yaml

import manage


ROOT = Path(__file__).resolve().parents[2]


class BuildCacheTests(unittest.TestCase):
    """确保缓存配置保持本地默认行为并限制可信写入。"""

    def test_default_and_missing_runtime_keep_local_builds(self) -> None:
        """普通入口沿用 Docker，缺少缓存鉴权时仍可加载本地镜像。@return None。"""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(manage._build_arguments('control'), ['docker', 'build'])
        with patch.dict(os.environ, {'FLOWER2API_BUILDX_BUILDER': 'synthetic',
                'FLOWER2API_BUILD_CACHE_SCOPE': 'synthetic'}, clear=True):
            arguments = manage._build_arguments('control')
        self.assertIn('--load', arguments)
        self.assertNotIn('--cache-from', arguments)
        self.assertNotIn('--cache-to', arguments)

    def test_roles_import_separately_and_only_trusted_jobs_export(self) -> None:
        """PR与非受信事件只读缓存，两个角色分别导入并导出。@return None。"""
        environment = {'FLOWER2API_BUILDX_BUILDER': 'synthetic',
            'FLOWER2API_BUILD_CACHE_SCOPE': 'synthetic-scope',
            'FLOWER2API_BUILD_CACHE_WRITE': 'true', 'ACTIONS_RUNTIME_TOKEN': 'synthetic-secret',
            'ACTIONS_RESULTS_URL': 'https://synthetic.invalid', 'GITHUB_ACTIONS': 'true',
            'GITHUB_REPOSITORY': 'SilentFlower/vibecoding-bench',
            'GITHUB_REF': 'refs/heads/flower2api', 'GITHUB_EVENT_NAME': 'push'}
        for changes, writable in (({}, True), ({'GITHUB_REF': 'refs/heads/v3'}, True),
                ({'GITHUB_EVENT_NAME': 'workflow_dispatch'}, True),
                ({'GITHUB_EVENT_NAME': 'pull_request'}, False),
                ({'GITHUB_REPOSITORY': 'synthetic/fork'}, False),
                ({'GITHUB_REF': 'refs/heads/untrusted'}, False),
                ({'FLOWER2API_BUILD_CACHE_WRITE': 'false'}, False)):
            with self.subTest(changes=changes), patch.dict(os.environ, environment | changes, clear=True):
                for role in ('control', 'account'):
                    arguments = manage._build_arguments(role)
                    cache = arguments[arguments.index('--cache-from') + 1]
                    self.assertIn('version=2', cache)
                    self.assertIn('scope=synthetic-scope-' + role, cache)
                    self.assertEqual('--cache-to' in arguments, writable)
                    self.assertNotIn('--push', arguments)
                    self.assertNotIn('synthetic-secret', ' '.join(arguments))
                    if writable:
                        exported = arguments[arguments.index('--cache-to') + 1]
                        self.assertIn('ignore-error=true', exported)

    def test_invalid_configuration_stops_before_snapshot_or_docker(self) -> None:
        """名称注入和非法开关在产生任何构建副作用前拒绝。@return None。"""
        for key, value in (('FLOWER2API_BUILDX_BUILDER', '--push'),
                ('FLOWER2API_BUILD_CACHE_SCOPE', 'scope,token=synthetic'),
                ('FLOWER2API_BUILD_CACHE_WRITE', 'yes')):
            with self.subTest(key=key), patch.dict(os.environ, {key: value}, clear=True):
                with patch.object(manage, 'command') as command:
                    with self.assertRaises(ValueError):
                        manage.build('synthetic', Path('/synthetic/manifest.json'))
                    command.assert_not_called()

    def test_action_mounts_match_dockerfile_and_activation_is_last(self) -> None:
        """恢复实际挂载ID，只有完整准备成功才向后续构建启用缓存。@return None。"""
        action = yaml.load((ROOT / '.github/actions/flower2api-build-cache/action.yml').read_text(),
            Loader=yaml.BaseLoader)
        steps = action['runs']['steps']
        dance = next(step for step in steps if 'buildkit-cache-dance@' in step.get('uses', ''))
        mounts = json.loads(dance['with']['cache-map'])
        actual = {(item['id'], item['target']) for item in mounts.values()}
        dockerfile = (ROOT / 'images/v3/Dockerfile').read_text()
        expected = set(re.findall(r'--mount=type=cache,id=([^,]+),target=([^,\s]+)', dockerfile))
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 3)
        self.assertIn('FLOWER2API_BUILDX_BUILDER', steps[-1]['run'])
        self.assertTrue(all('GITHUB_ENV' not in step.get('run', '') for step in steps[:-1]))
        saver = next(i for i, step in enumerate(steps) if step.get('uses') == 'actions/cache@v5')
        extractor = steps.index(dance)
        self.assertLess(saver, extractor)
        self.assertIn("write == 'true'", steps[saver]['if'])
        reader = next(step for step in steps if step.get('uses') == 'actions/cache/restore@v5')
        self.assertIn("write != 'true'", reader['if'])
        config = next(step for step in steps if step.get('id') == 'config')['env']
        for path in ('Cargo.toml', 'Cargo.lock', 'vendor/**', 'craftls/**', 'Dockerfile'):
            self.assertIn(path, config['DEPENDENCIES'])
        for path in ('services/gateway/src/**', 'apps/web/**', 'platform-release.json'):
            self.assertIn(path, config['SOURCES'])

    def test_only_cache_preparation_is_optional_in_both_workflows(self) -> None:
        """缓存准备可回退，实际构建与全部来源的演练错误阻断流程。@return None。"""
        for filename in ('v3-build.yml', 'v3-release.yml'):
            workflow = yaml.load((ROOT / '.github/workflows' / filename).read_text(), Loader=yaml.BaseLoader)
            steps = next(iter(workflow['jobs'].values()))['steps']
            optional = [step for step in steps if step.get('continue-on-error') == 'true']
            self.assertEqual(len(optional), 1)
            self.assertEqual(optional[0]['uses'], './.github/actions/flower2api-build-cache')
            build = next(step for step in steps if 'manage.py build' in step.get('run', ''))
            self.assertLess(steps.index(optional[0]), steps.index(build))
            if filename == 'v3-release.yml':
                verify = next(step for step in steps if 'verify_database_compatibility.py --manifest' in step.get('run', ''))
                self.assertIn('--workers 2', verify['run'])


if __name__ == '__main__':
    unittest.main()
