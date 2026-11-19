"""验证候选来源、归档完整性、后台缓存边界及当前发布身份。"""
import copy
import hashlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import candidate_artifacts as artifacts
import candidate_images as images
import manage


class CandidateBuildTests(unittest.TestCase):
    """所有网络与Docker副作用使用合成边界，原始文件校验使用真实字节。"""

    def setUp(self) -> None:
        """建立两角色清单、同源GitHub运行与隔离目录。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.identity = {'repository': artifacts.REPOSITORY, 'ref': 'refs/heads/flower2api',
            'revision': 'a' * 40, 'run_id': 123, 'run_attempt': 1}
        self.environment = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': artifacts.REPOSITORY,
            'GITHUB_REF': self.identity['ref'], 'GITHUB_SHA': self.identity['revision'],
            'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_RUN_ID': '456', 'GITHUB_RUN_ATTEMPT': '2',
            'GITHUB_WORKFLOW_REF': artifacts.REPOSITORY + '/.github/workflows/v3-release.yml@' + self.identity['ref'],
            'V3_PUBLISH_CONFIRMED': 'true'}
        context = patch.dict(os.environ, self.environment, clear=True)
        context.start()
        self.addCleanup(context.stop)
        from agy_auth import SOURCE_BYTES, SOURCE_SHA256
        self.manifest = {'schema': 3, 'layout_version': 2, 'release': 'ci-123-1',
            'agy_auth': {'available': True, 'source_version': '1.5.9', 'bytes': SOURCE_BYTES, 'sha256': SOURCE_SHA256},
            'parent_revision': 'a' * 40, 'gateway_revision': 'a' * 40,
            'dirty_worktree': False, 'source_content_sha256': 'b' * 64,
            'images': {role: {'reference': f'flower2api-{role}:v3-ci-123-1',
                'digest': 'sha256:' + 'c' * 64, 'config_digest': 'sha256:' + 'c' * 64,
                'platform': 'linux/amd64'} for role in ('control', 'account')}}
        self.folder = self.root / 'candidate'
        self.folder.mkdir()
        (self.folder / images.MANIFEST_NAME).write_text(json.dumps(self.manifest))
        (self.folder / images.BUNDLE_NAME).write_bytes(b'synthetic image archive')
        self.metadata = {'schema_version': 1, **self.identity}
        for key, name in [('manifest', images.MANIFEST_NAME), ('bundle', images.BUNDLE_NAME)]:
            path = self.folder / name
            self.metadata[key] = {'name': name, 'size': path.stat().st_size, 'sha256': manage._file_sha256(path)}
        (self.folder / images.METADATA_NAME).write_text(json.dumps(self.metadata))
        self.run = {'id': 123, 'run_attempt': 1, 'head_sha': 'a' * 40, 'head_branch': 'flower2api',
            'event': 'push', 'path': artifacts.WORKFLOW, 'status': 'in_progress', 'conclusion': None,
            'repository': {'id': 99, 'full_name': artifacts.REPOSITORY},
            'head_repository': {'id': 99, 'full_name': artifacts.REPOSITORY}}
        self.jobs = {'jobs': [{'name': 'build', 'steps': [{'name': name, 'status': 'completed',
            'conclusion': 'success'} for name in artifacts.REQUIRED_STEPS]}]}
        self.artifact = {'id': 789, 'name': 'v3-candidate-123-1', 'expired': False,
            'size_in_bytes': 2048, 'digest': 'sha256:' + 'd' * 64,
            'workflow_run': {'id': 123, 'head_sha': 'a' * 40, 'head_branch': 'flower2api',
                'repository_id': 99, 'head_repository_id': 99}}

    def archive(self) -> bytes:
        """生成实际候选ZIP。:return: 原始归档字节。"""
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for path in self.folder.iterdir():
                archive.writestr(path.name, path.read_bytes())
        return output.getvalue()

    def api(self, endpoint: str) -> dict:
        """返回当前用例的固定GitHub对象。:param endpoint: API路径。:return: 合成响应。"""
        if '/runs?' in endpoint:
            return {'workflow_runs': [self.run]}
        if endpoint.endswith('/jobs?per_page=100'):
            return self.jobs
        if endpoint.endswith('/artifacts?per_page=100'):
            return {'artifacts': [self.artifact]}
        return self.run

    def test_export_rejects_pr_fork_wrong_workflow_and_dirty_source(self) -> None:
        """只有受信构建可导出，非法来源在Docker操作前拒绝。:return: None。"""
        trusted = {**self.environment, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_EVENT_NAME': 'push', 'GITHUB_WORKFLOW_REF': artifacts.REPOSITORY + '/' + artifacts.WORKFLOW + '@' + self.identity['ref']}
        with patch.dict(os.environ, trusted, clear=True):
            self.assertEqual(self.identity, images.build_identity())
            for changes in ({'GITHUB_EVENT_NAME': 'pull_request'}, {'GITHUB_REPOSITORY': 'fork/repository'},
                    {'GITHUB_REF': 'refs/heads/main'}, {'GITHUB_RUN_ATTEMPT': '0'},
                    {'GITHUB_WORKFLOW_REF': trusted['GITHUB_WORKFLOW_REF'].replace('v3-build', 'v3-release')}):
                with self.subTest(changes=changes), patch.dict(os.environ, changes):
                    with self.assertRaises(ValueError):
                        images.build_identity()
        for key, value in [('dirty_worktree', True), ('parent_revision', 'f' * 40), ('release', 'ci-123-2')]:
            with self.subTest(field=key):
                changed = {**self.manifest, key: value}
                with self.assertRaises(ValueError):
                    images.validate_candidate_manifest(changed, self.identity)

    def test_files_match_exact_identity_and_tampering_refuses_before_docker(self) -> None:
        """两份文件的真实摘要必须匹配，篡改后不能加载镜像。:return: None。"""
        self.assertEqual(self.manifest, images.validate_candidate_files(self.folder, self.identity))
        for name in (images.MANIFEST_NAME, images.BUNDLE_NAME):
            path = self.folder / name
            original = path.read_bytes()
            path.write_bytes(original + b'changed')
            with patch.object(manage, 'command') as command:
                with self.assertRaises(ValueError):
                    images.adopt_candidate(self.folder, self.identity, self.root / 'formal.json')
                command.assert_not_called()
            path.write_bytes(original)
        changed = {**self.metadata, 'run_attempt': True}
        (self.folder / images.METADATA_NAME).write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            images.validate_candidate_files(self.folder, self.identity)

    def test_origin_excludes_other_source_branch_workflow_and_repository(self) -> None:
        """同SHA的PR、外仓、错误分支和伪工作流均不进入复用路径。:return: None。"""
        self.assertTrue(artifacts.trusted_run(self.run, 'a' * 40, self.identity['ref']))
        for key, value in [('event', 'pull_request'), ('head_branch', 'v3'), ('head_sha', 'f' * 40),
                ('path', '.github/workflows/other.yml'), ('run_attempt', True),
                ('head_repository', {'id': 12, 'full_name': artifacts.REPOSITORY}),
                ('repository', {'id': 99, 'full_name': 'fork/repository'})]:
            with self.subTest(field=key):
                self.assertFalse(artifacts.trusted_run({**self.run, key: value}, 'a' * 40, self.identity['ref']))

    def test_implicit_build_triggers_and_changed_runtime_config_refuse_adoption(self) -> None:
        """换批前阻止ONBUILD执行，换批后拒绝任何运行配置变化。:return: None。"""
        missing = SimpleNamespace(returncode=1, stderr='No such image', stdout='')
        for trigger in (True, False):
            before = {'Id': 'sha256:' + 'c' * 64, 'Config': {'Labels': {'vibebench.release': 'ci-123-1'},
                'Env': ['SYNTHETIC=stable'], 'OnBuild': ['RUN invalid'] if trigger else None},
                'RootFS': {'Type': 'layers', 'Layers': ['sha256:' + 'e' * 64]}, 'Os': 'linux', 'Architecture': 'amd64'}
            after = copy.deepcopy(before)
            after['Config']['Labels']['vibebench.release'] = 'ci-456-2'
            after['Config']['Env'] = ['SYNTHETIC=changed']
            def command(*args, **kwargs):
                if args[:3] == ('docker', 'image', 'inspect'):
                    return json.dumps([after if 'ci-456-2' in args[3] else before])
                return ''
            output = self.root / 'unsafe.json'
            with patch.object(images.subprocess, 'run', return_value=missing), \
                    patch.object(manage, 'inspect_images'), patch.object(manage, 'command', side_effect=command) as called:
                with self.assertRaises(ValueError):
                    images.adopt_candidate(self.folder, self.identity, output)
                if trigger:
                    self.assertFalse(any(call.args[:2] == ('docker', 'build') for call in called.call_args_list))
                self.assertFalse(output.exists())

    def test_provider_error_has_no_credential_or_raw_body_in_public_message(self) -> None:
        """来源API失败保持失败，公开错误不回显原始响应。:return: None。"""
        failed = SimpleNamespace(returncode=1, stdout=b'PRIVATE_API_CANARY', stderr=b'PRIVATE_API_CANARY')
        with patch.object(artifacts.subprocess, 'run', return_value=failed):
            with self.assertRaises(RuntimeError) as error:
                artifacts.github_json('actions/runs/123')
        self.assertNotIn('PRIVATE_API_CANARY', str(error.exception))

    def test_artifact_requires_all_checks_and_allows_cache_post_to_continue(self) -> None:
        """必要步骤已成功时允许job仍在post，失败或未完成检查保持关闭。:return: None。"""
        value = {'artifacts': [self.artifact]}
        self.assertEqual(self.artifact, artifacts.candidate_artifact(self.run, self.jobs, value))
        for conclusion in ('failure', None):
            jobs = copy.deepcopy(self.jobs)
            jobs['jobs'][0]['steps'][0]['conclusion'] = conclusion
            self.assertIsNone(artifacts.candidate_artifact(self.run, jobs, value))
        self.assertIsNone(artifacts.candidate_artifact(self.run, self.jobs,
            {'artifacts': [{**self.artifact, 'expired': True}]}))
        for changed in ({**self.artifact, 'digest': ''}, {**self.artifact, 'id': True},
                {**self.artifact, 'workflow_run': {**self.artifact['workflow_run'], 'head_sha': 'f' * 40}}):
            with self.assertRaises(ValueError):
                artifacts.candidate_artifact(self.run, self.jobs, {'artifacts': [changed]})
        with self.assertRaises(ValueError):
            artifacts.candidate_artifact(self.run, self.jobs, {'artifacts': [self.artifact, self.artifact]})

    def test_zip_rejects_unknown_duplicate_symlink_and_oversized_members(self) -> None:
        """归档只可包含三份普通文件，拒绝路径穿越、链接和膨胀成员。:return: None。"""
        valid = self.archive()
        path = self.root / 'artifact.zip'
        path.write_bytes(valid)
        target = self.root / 'unpacked'
        target.mkdir()
        artifacts.unpack_archive(path, target)
        self.assertEqual(self.manifest, images.validate_candidate_files(target, self.identity))
        for invalid in ('../escape', images.MANIFEST_NAME):
            output = io.BytesIO(valid)
            with zipfile.ZipFile(output, 'a') as archive:
                archive.writestr(invalid, b'synthetic')
            path.write_bytes(output.getvalue())
            with self.assertRaises(ValueError):
                artifacts.unpack_archive(path, self.root)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for source in self.folder.iterdir():
                info = zipfile.ZipInfo(source.name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, source.read_bytes())
        path.write_bytes(output.getvalue())
        with self.assertRaises(ValueError):
            artifacts.unpack_archive(path, self.root)
        path.write_bytes(valid)
        with patch.object(artifacts, 'MAX_BUNDLE_BYTES', 2), self.assertRaises(ValueError):
            artifacts.unpack_archive(path, self.root)

    def test_download_checks_the_github_zip_digest(self) -> None:
        """下载只使用固定归档ID，GitHub摘要不符时拒绝解包。:return: None。"""
        raw = self.archive()
        expected = {**self.artifact, 'digest': 'sha256:' + hashlib.sha256(raw).hexdigest()}
        def download(args, **kwargs):
            self.assertEqual(f"repos/{artifacts.REPOSITORY}/actions/artifacts/789/zip", args[-1])
            kwargs['stdout'].write(raw)
            return SimpleNamespace(returncode=0)
        with patch.object(artifacts.subprocess, 'run', side_effect=download):
            artifacts.download_archive(expected, self.root / 'download.zip')
            with self.assertRaises(ValueError):
                artifacts.download_archive(self.artifact, self.root / 'bad.zip')

    def test_resolve_reuses_verified_in_progress_build_and_checks_again_after_download(self) -> None:
        """实际解包后再次核对来源，确认当前batch校验仍由换批入口持有。:return: None。"""
        raw = self.archive()
        self.artifact['digest'] = 'sha256:' + hashlib.sha256(raw).hexdigest()
        def download(artifact, path):
            path.write_bytes(raw)
        with patch.object(artifacts, 'check_checkout'), patch.object(artifacts, 'github_json', side_effect=self.api), \
                patch.object(artifacts, 'download_archive', side_effect=download), \
                patch.object(artifacts, 'adopt_candidate') as adopt:
            self.assertTrue(artifacts.resolve_candidate(self.root / 'formal.json', 0))
            self.assertEqual(self.identity, adopt.call_args.args[1])
        calls = 0
        def drift(endpoint):
            nonlocal calls
            result = self.api(endpoint)
            if endpoint == 'actions/runs/123':
                calls += 1
                if calls > 1:
                    return {**result, 'run_attempt': 2}
            return result
        with patch.object(artifacts, 'check_checkout'), patch.object(artifacts, 'github_json', side_effect=drift), \
                patch.object(artifacts, 'download_archive', side_effect=download), \
                patch.object(artifacts, 'adopt_candidate') as adopt:
            with self.assertRaises(ValueError):
                artifacts.resolve_candidate(self.root / 'formal.json', 0)
            adopt.assert_not_called()

    def test_absent_failed_expired_and_legacy_builds_use_full_build_path(self) -> None:
        """缺失或不可用候选只回到完整构建，超时及损坏候选明确失败。:return: None。"""
        with patch.object(artifacts, 'check_checkout'), patch.object(artifacts, 'github_json', return_value={'workflow_runs': []}):
            self.assertFalse(artifacts.resolve_candidate(self.root / 'formal.json', 0))
        for condition in ('failure', 'expired', 'legacy'):
            self.run['status'] = 'completed'
            self.run['conclusion'] = 'failure' if condition == 'failure' else 'success'
            self.artifact['expired'] = condition == 'expired'
            self.jobs['jobs'][0]['steps'] = [] if condition == 'legacy' else [
                {'name': name, 'status': 'completed', 'conclusion': 'success'} for name in artifacts.REQUIRED_STEPS]
            with patch.object(artifacts, 'check_checkout'), patch.object(artifacts, 'github_json', side_effect=self.api):
                self.assertFalse(artifacts.resolve_candidate(self.root / 'formal.json', 0))
        self.run.update(status='in_progress', conclusion=None)
        with patch.object(artifacts, 'check_checkout'), patch.object(artifacts, 'github_json', side_effect=self.api), self.assertRaises(RuntimeError):
            artifacts.resolve_candidate(self.root / 'formal.json', 0)

    def test_dirty_or_different_checkout_refuses_before_candidate_lookup(self) -> None:
        """复用不能掩盖本地源码变更，干净同SHA才允许读取候选。:return: None。"""
        for head, dirty in [('f' * 40, ''), ('a' * 40, ' M source.py')]:
            with patch.object(manage, 'command', side_effect=[head, dirty]), self.assertRaises(ValueError):
                artifacts.check_checkout('a' * 40)
        with patch.object(manage, 'command', side_effect=['a' * 40, '']):
            artifacts.check_checkout('a' * 40)

    @unittest.skipUnless(os.environ.get('FLOWER2API_CANDIDATE_DOCKER') == '1', '真实Docker候选验收按开关运行')
    def test_real_docker_candidate_keeps_files_and_configuration_when_rebatched(self) -> None:
        """真实导出、摘要核对、加载与换批保留文件层，只改发行身份。:return: None。"""
        token = uuid.uuid4().hex
        origin = 2000000000000 + int(token[:10], 16)
        target = origin + 1
        self.identity['run_id'] = origin
        self.manifest['release'] = f'ci-{origin}-1'
        references = [images.image_reference(role, batch) for batch in (f'ci-{origin}-1', f'ci-{target}-2')
            for role in ('control', 'account')]
        def inspect(reference):
            result = subprocess.run(['docker', 'image', 'inspect', reference], capture_output=True, text=True)
            return json.loads(result.stdout)[0] if result.returncode == 0 else None
        def cleanup():
            for reference in reversed(references):
                info = inspect(reference)
                if info and (info['Config'].get('Labels') or {}).get('flower2api.test-id') == token:
                    subprocess.run(['docker', 'image', 'rm', reference], capture_output=True, check=True)
        self.addCleanup(cleanup)
        self.assertTrue(all(inspect(reference) is None for reference in references))
        source = self.root / 'source'
        source.mkdir()
        (source / 'payload').write_bytes(b'synthetic candidate file\n')
        for role in ('control', 'account'):
            reference = images.image_reference(role, self.manifest['release'])
            (source / 'Dockerfile').write_text('FROM scratch\nCOPY payload /payload\n'
                'ENV SYNTHETIC_CONFIG=stable\nCMD ["/payload"]\n'
                f'LABEL flower2api.test-id="{token}" vibebench.product="v3" vibebench.role="{role}" '
                f'vibebench.release="{self.manifest["release"]}" vibebench.isolation-version="2" '
                f'vibebench.parent-revision="{"a" * 40}" vibebench.gateway-revision="{"a" * 40}"\n')
            subprocess.run(['docker', 'build', '--network=none', '-t', reference, str(source)],
                check=True, capture_output=True)
            info = inspect(reference)
            self.manifest['images'][role] = {'reference': reference, 'digest': info['Id'],
                'config_digest': manage._image_config_digest(reference),
                'platform': info['Os'] + '/' + info['Architecture'], 'unpacked_bytes': info['Size']}
        source_manifest = self.root / 'source.json'
        source_manifest.write_text(json.dumps(self.manifest))
        with patch.dict(os.environ, {'GITHUB_RUN_ID': str(origin), 'GITHUB_RUN_ATTEMPT': '1',
                'GITHUB_EVENT_NAME': 'push',
                'GITHUB_WORKFLOW_REF': artifacts.REPOSITORY + '/' + artifacts.WORKFLOW + '@' + self.identity['ref']}):
            images.export_candidate(source_manifest, self.root / 'exported')
        for entry in self.manifest['images'].values():
            subprocess.run(['docker', 'image', 'rm', entry['reference']], check=True, capture_output=True)
            self.assertIsNone(inspect(entry['reference']))
        self.folder = self.root / 'exported'
        self.run['id'] = origin
        self.artifact['name'] = f'v3-candidate-{origin}-1'
        self.artifact['workflow_run']['id'] = origin
        raw = self.archive()
        self.artifact['digest'] = 'sha256:' + hashlib.sha256(raw).hexdigest()
        def download(artifact, path):
            path.write_bytes(raw)
        with patch.dict(os.environ, {'GITHUB_RUN_ID': str(target)}):
            output = self.root / 'adopted.json'
            with patch.object(artifacts, 'check_checkout'), patch.object(artifacts, 'github_json', side_effect=self.api), \
                    patch.object(artifacts, 'download_archive', side_effect=download):
                self.assertTrue(artifacts.resolve_candidate(output, 0))
            adopted = json.loads(output.read_text())
            self.assertEqual(f'ci-{target}-2', adopted['release'])
            self.assertEqual(self.manifest['source_content_sha256'], adopted['source_content_sha256'])
            for role in ('control', 'account'):
                before = inspect(self.manifest['images'][role]['reference'])
                after = inspect(adopted['images'][role]['reference'])
                self.assertEqual(before['RootFS'], after['RootFS'])
                self.assertEqual(before['Config']['Env'], after['Config']['Env'])
                self.assertEqual(before['Config']['Cmd'], after['Config']['Cmd'])
                self.assertEqual(self.manifest['release'], before['Config']['Labels']['vibebench.release'])
            with self.assertRaises(ValueError):
                images.adopt_candidate(self.root / 'exported', self.identity, self.root / 'repeated.json')


if __name__ == '__main__':
    unittest.main()
