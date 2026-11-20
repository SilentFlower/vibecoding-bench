"""语义版本元数据、历史兼容及正式发布递增合同。"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import ExitStack
from source_layout import source_path

sys.path.insert(0, str(source_path(Path(__file__).resolve().parents[2], 'orchestrator')))
from platform_version import ensure_forward_version, read_version, signed_changes, version_from_changes
import manage


class PlatformVersionTests(unittest.TestCase):
    """版本来源及受信说明保持一致。"""

    def test_metadata_and_signed_projection(self):
        """真实元数据生成可读版本，非法或旧说明保持区别。@return None。"""
        value = read_version(Path(__file__).with_name('platform-release.json'))
        self.assertEqual(version_from_changes(signed_changes(value)), tuple(map(int, value['version'][1:].split('.'))))
        self.assertIsNone(version_from_changes('历史发行'))
        self.assertIsNone(version_from_changes('平台版本：v01.0.0'))
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'version.json'
            for invalid in [dict(value, version='1.0.0'), dict(value, extra=True), dict(value, schema_version=True)]:
                target.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    read_version(target)

    def test_patch_feature_legacy_and_same_source_rerun(self):
        """允许递增及同源重跑，不同源码必须更新版本。@return None。"""
        previous = {'changes': '平台版本：v1.0.0\n旧说明', 'control': {'revision': 'a' * 40}, 'account': {'revision': 'b' * 40}}
        ensure_forward_version(copy.deepcopy(previous), previous)
        for version in ['v1.0.1', 'v1.1.0', 'v2.0.0']:
            current = copy.deepcopy(previous)
            current['changes'] = '平台版本：' + version
            current['control']['revision'] = 'c' * 40
            ensure_forward_version(current, previous)
        for version in ['v1.0.0', 'v0.9.0']:
            current = copy.deepcopy(previous)
            current['changes'] = '平台版本：' + version
            current['account']['revision'] = 'c' * 40
            with self.assertRaisesRegex(ValueError, '递增'):
                ensure_forward_version(current, previous)
        ensure_forward_version(previous, dict(previous, changes='旧说明'))

    def test_build_projects_runtime_version_and_keeps_compile_inputs_version_independent(self) -> None:
        """真实快照与摘要绑定版本文件，编译命令及前端/Rust源码保持一致。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ('cc2api/src', 'cc2api/vendor', 'cc2api/craftls', 'cc2api/web',
                    'images/account', 'images/sidecar', 'images/worker', 'images/v3', 'images/pi-agent',
                    'orchestrator', 'webui', 'project_library', 'research/github-projects', 'deploy/v3'):
                (root / relative).mkdir(parents=True, exist_ok=True)
            for relative in ('cc2api/src/main.rs', 'cc2api/web/index.html', 'cc2api/Cargo.toml',
                    'cc2api/Cargo.lock', 'topics.md', 'images/v3/Dockerfile'):
                (root / relative).write_text('synthetic-source\n')
            metadata = root / 'deploy/v3/platform-release.json'
            seen = []

            def asset(path, **options):
                """只替换原生资产获取，版本快照与内容摘要仍由真实build生成。"""
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'synthetic-runtime')
                return {'sha256': 'a' * 64}

            def command(*arguments, **options):
                """截取实际构建输入，隔离Docker执行。"""
                if arguments[:3] == ('git', 'rev-parse', 'HEAD'):
                    return 'a' * 40
                if arguments[:2] == ('git', 'status'):
                    return ''
                if arguments[:2] == ('docker', 'build'):
                    snapshot = Path(arguments[-1])
                    seen.append({'version': json.loads((snapshot / 'runtime-build/platform-version.json').read_text()),
                        'metadata': read_version(snapshot / 'deploy/v3/platform-release.json')['version'],
                        'frontend': (snapshot / 'cc2api/web/index.html').read_bytes(),
                        'backend': (snapshot / 'cc2api/src/main.rs').read_bytes(), 'arguments': arguments})
                    return ''
                if arguments[:3] == ('docker', 'image', 'inspect'):
                    return json.dumps([{'Id': 'sha256:' + 'a' * 64, 'Size': 123,
                        'Os': 'linux', 'Architecture': 'amd64', 'Config': {'Labels': {}}}])
                raise AssertionError('合成夹具出现非预期命令')

            manifests = []
            with ExitStack() as stack:
                for name, value in (('REPO', root),):
                    stack.enter_context(patch.object(manage, name, value))
                stack.enter_context(patch.object(manage, '_build_arguments', return_value=['docker', 'build']))
                stack.enter_context(patch.object(manage, 'stage_asset', side_effect=asset))
                stack.enter_context(patch.object(manage, 'restore_upstream_checkout_bytes', return_value=[]))
                stack.enter_context(patch.object(manage, 'deduplicate_immutable_tree'))
                stack.enter_context(patch.object(manage, '_image_config_digest', return_value='sha256:' + 'b' * 64))
                stack.enter_context(patch.object(manage, 'command', side_effect=command))
                stack.enter_context(patch.object(manage.subprocess, 'run', return_value=SimpleNamespace(returncode=1)))
                for index, version in enumerate(('v1.17.2', 'v1.17.3', 'v1.17.3')):
                    metadata.write_text(json.dumps({'schema_version': 1, 'version': version, 'changes': '合成版本说明'}))
                    output = root / ('manifest-' + str(index) + '.json')
                    build_options = {} if index == 2 else {'prebuilt': False}
                    manage.build('ci-' + str(index + 1) + '-1', output, **build_options)
                    manifests.append(json.loads(output.read_text()))
            self.assertEqual([value['version']['version'] for value in seen], ['v1.17.2'] * 2 + ['v1.17.3'] * 5)
            self.assertTrue(all(value['version']['version'] == value['metadata'] for value in seen))
            self.assertEqual(len({value['frontend'] for value in seen}), 1)
            self.assertEqual(len({value['backend'] for value in seen}), 1)
            self.assertTrue(all(not any('VITE_PLATFORM_VERSION' in argument for argument in value['arguments']) for value in seen))
            self.assertNotEqual(manifests[0]['source_content_sha256'], manifests[1]['source_content_sha256'])
            self.assertEqual(manifests[1]['source_content_sha256'], manifests[2]['source_content_sha256'])
            compiler, control, account = (entry['arguments'] for entry in seen[-3:])
            self.assertEqual([arguments[arguments.index('--target') + 1] for arguments in (compiler, control, account)],
                ['compiled-artifacts', 'control', 'account'])
            compiled_path = compiler[compiler.index('--output') + 1].removeprefix('type=local,dest=')
            self.assertEqual(compiler[-1], control[-1])
            self.assertEqual(compiler[-1], account[-1])
            for arguments in (control, account):
                self.assertEqual(arguments[arguments.index('--build-context') + 1], f'compiled-artifacts={compiled_path}')


if __name__ == '__main__':
    unittest.main()
