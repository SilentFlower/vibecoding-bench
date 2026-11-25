"""实际 SQLite 元数据与软件字段恢复的边界验证。"""
import copy
import base64
import json
import sqlite3
import subprocess
import tempfile
import unittest
import uuid
import gc
import gzip
import hashlib
import io
import os
import platform
import tarfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import UnixStreamServer
from threading import Event, Thread
from contextlib import closing
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from pathlib import Path
from unittest.mock import Mock, patch

from system_update_host import ControlHealthTimeout, HostDeployment, pull_image
from runtime_files import atomic_json, atomic_text
from system_update_gate import read_gate
from system_update_database import assert_quiescent, create_snapshot, restore_snapshot
from runtime_names import account_container_prefix


class DownloadProgressTests(unittest.TestCase):
    """从实际本地 HTTP 流读取镜像和签名包字节。"""

    def test_registry_tracks_parallel_layers_cache_retries_and_extraction(self) -> None:
        """本机 Engine 流分批送达，验证实际字节、未知分母与解包隔离。@return 无。"""
        received = Event()
        resume = Event()
        results, errors = [], []
        lines = [
            {'id': 'layer1', 'status': 'Pulling fs layer'},
            {'id': 'shared', 'status': 'Waiting'},
            {'id': 'layer2', 'status': 'Waiting'},
            {'id': 'shared', 'status': 'Already exists'},
            {'id': 'layer1', 'status': 'Downloading', 'progressDetail': {'current': 10, 'total': 50}},
            {'id': 'layer2', 'status': 'Downloading', 'progressDetail': {'current': 20, 'total': 100}},
            {'id': 'layer2', 'status': 'Downloading', 'progressDetail': {'current': 5, 'total': 100}},
            {'id': 'layer1', 'status': 'Download complete'},
            {'id': 'layer2', 'status': 'Download complete'},
            {'id': 'layer2', 'status': 'Extracting', 'progressDetail': {'current': 950, 'total': 1000}},
            {'status': 'Status: Downloaded newer image for synthetic'},
        ]
        encoded = [json.dumps(item).encode() + b'\n' for item in lines]
        reference = 'registry.fixture/library/test@sha256:' + 'a' * 64

        class Engine(BaseHTTPRequestHandler):
            """受控 Docker 端点，第一批数据后等待读者确认。"""

            def log_message(self, *_):
                """隐藏本地请求日志。@return 无。"""

            def do_HEAD(self):
                """返回合成的 Engine API 版本。@return 无。"""
                self.send_response(200)
                self.send_header('Api-Version', '1.52')
                self.end_headers()

            def do_POST(self):
                """写入分段 JSON 响应。@return 无。"""
                try:
                    auth = json.loads(base64.urlsafe_b64decode(self.headers['X-Registry-Auth']))
                    if auth.get('username') != 'fixture' or 'fromImage=registry.fixture%2Flibrary%2Ftest%40sha256%3A' not in self.path:
                        raise AssertionError('镜像未按冻结摘要和本地仓库鉴权拉取')
                    self.send_response(200)
                    self.send_header('Content-Length', str(sum(map(len, encoded))))
                    self.end_headers()
                    self.wfile.write(b''.join(encoded[:5]))
                    if not resume.wait(5):
                        raise AssertionError('首批字节没有实时送达')
                    self.wfile.write(b''.join(encoded[5:]))
                except Exception as error:
                    errors.append(error)

        def report(value):
            results.append(value)
            if value['downloaded_bytes'] == 10:
                received.set()
                resume.set()

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'config.json').write_text(json.dumps({'auths': {'registry.fixture': {
                'auth': base64.b64encode(b'fixture:fixture-password').decode()}}}))
            with UnixStreamServer(str(path / 'socket'), Engine) as server, patch.dict(
                    'os.environ', {'DOCKER_CONFIG': folder, 'DOCKER_AUTH_CONFIG': '', 'DOCKER_API_VERSION': ''}):
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    pull_image('unix://' + str(path / 'socket'), reference, 'control', report, timeout=10)
                finally:
                    server.shutdown()
                    thread.join(5)
        self.assertEqual([], errors)
        self.assertTrue(received.is_set())
        readings = [(item['downloaded_bytes'], item['total_bytes']) for item in results]
        self.assertIn((10, None), readings)
        self.assertIn((30, 150), readings)
        self.assertIn((15, 150), readings)
        self.assertEqual((150, 150), readings[-1])
        self.assertIn('loading', [item['state'] for item in results])
        self.assertEqual('verifying', results[-1]['state'])

    def test_signed_bundle_streams_bytes_and_reports_cache(self) -> None:
        """压缩包按实际读取进度与签名大小发布，命中本地包时无网络字节。@return 无。"""
        first = b'a' * 32768
        content = first + b'b' * 65536
        resume = Event()
        results = []

        class Bundle(BaseHTTPRequestHandler):
            """分段提供合成镜像包。"""

            def log_message(self, *_):
                """隐藏本地请求日志。@return 无。"""

            def do_GET(self):
                """写入两批包字节。@return 无。"""
                self.send_response(200)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(first)
                if resume.wait(5):
                    self.wfile.write(content[len(first):])

        def report(value):
            results.append(value)
            if value['downloaded_bytes'] == len(first):
                resume.set()

        with tempfile.TemporaryDirectory() as folder, ThreadingHTTPServer(('127.0.0.1', 0), Bundle) as server:
            root = Path(folder)
            host = HostDeployment({'state_root': folder, 'data_root': folder, 'env_file': str(root / 'v3.env'),
                'deployment': 'synthetic'})
            release = {'release': 'fixture', 'build_manifests': {role: {'name': 'build.json'} for role in ('control', 'account')},
                'bundle': {'name': 'images.tar.gz', 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}}
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch('system_update_host.DOWNLOAD_ROOT', 'http://127.0.0.1:' + str(server.server_port)), \
                        patch('system_update_host.load_bundle') as load:
                    host._load_release_bundle(release, root, report)
                    self.assertEqual(content, (root / 'images.tar.gz').read_bytes())
                    host._load_release_bundle(release, root, report)
                    self.assertEqual(2, load.call_count)
            finally:
                server.shutdown()
                thread.join(5)
        self.assertIn(('downloading', len(first), len(content)),
            [(item['state'], item['downloaded_bytes'], item['total_bytes']) for item in results])
        self.assertEqual(('loading', len(content)), (results[-2]['state'], results[-2]['downloaded_bytes']))
        self.assertEqual(('cached', 0, None),
            (results[-1]['state'], results[-1]['downloaded_bytes'], results[-1]['total_bytes']))

    def test_registry_failure_starts_bundle_with_its_own_byte_count(self) -> None:
        """仓库中断后切换签名包，保留包独立的读数和校验状态。@return 无。"""
        readings = []

        def registry(_endpoint, _image, _role, report, **_options):
            report({'source': 'registry', 'component': 'control', 'state': 'downloading',
                'downloaded_bytes': 7, 'total_bytes': 20})
            raise RuntimeError('合成仓库断流')

        def bundle(_release, _folder, report):
            report({'source': 'bundle', 'component': 'bundle', 'state': 'downloading',
                'downloaded_bytes': 0, 'total_bytes': 30})
            report({'source': 'bundle', 'component': 'bundle', 'state': 'loading',
                'downloaded_bytes': 30, 'total_bytes': 30})

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host = HostDeployment({'state_root': folder, 'data_root': folder, 'env_file': str(root / 'v3.env'),
                'deployment': 'synthetic'})
            entry = {'reference': 'fixture/release:v2', 'registry_digest': 'sha256:' + 'a' * 64,
                'config_digest': 'sha256:' + 'b' * 64, 'unpacked_bytes': 30}
            with patch.object(host, '_verify_build_manifests'), patch.object(host, '_load_release_bundle', side_effect=bundle), \
                    patch.object(host, 'verify_images', side_effect=[{}, {'control': {'Id': 'synthetic'}}]), \
                    patch.object(host, '_project_library_binding', return_value=None), \
                    patch('system_update_host._check_local_reference'), patch('system_update_host.pull_image', side_effect=registry), \
                    patch.dict(os.environ, {'DOCKER_CONTEXT': '', 'DOCKER_HOST': 'unix:///fixture.sock'}):
                host.prepare({'bundle': {'size': 30}}, {role: entry for role in ('control', 'account')}, root, readings.append)
        self.assertEqual([('registry', 7, 20), ('bundle', 0, 30), ('bundle', 30, 30), ('bundle', 30, 30)],
            [(item['source'], item['downloaded_bytes'], item['total_bytes']) for item in readings])
        self.assertEqual('verifying', readings[-1]['state'])

    @unittest.skipUnless(os.environ.get('FLOWER_TEST_LOCAL_DOCKER') == '1', '需要可访问本机回环仓库的 Docker Engine')
    def test_real_docker_pulls_from_loopback_registry(self) -> None:
        """实际 Docker 拉取分段放行的镜像，下载字节与仓库实际发送量一致。@return 无。"""
        architecture = {'x86_64': 'amd64', 'aarch64': 'arm64'}[platform.machine()]

        def sha(content):
            return 'sha256:' + hashlib.sha256(content).hexdigest()

        def descriptor(media, content):
            return {'mediaType': 'application/vnd.docker.' + media, 'size': len(content), 'digest': sha(content)}

        data = os.urandom(2 * 1024 * 1024)
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w') as archive:
            member = tarfile.TarInfo('transfer-fixture')
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        layer = gzip.compress(raw.getvalue(), mtime=0)
        config = json.dumps({'architecture': architecture, 'os': 'linux', 'config': {},
            'rootfs': {'type': 'layers', 'diff_ids': [sha(raw.getvalue())]},
            'history': [{'created_by': 'system-update-transfer-test'}]}).encode()
        manifest_type = 'application/vnd.docker.distribution.manifest.v2+json'
        manifest = json.dumps({'schemaVersion': 2, 'mediaType': manifest_type,
            'config': descriptor('container.image.v1+json', config),
            'layers': [descriptor('image.rootfs.diff.tar.gzip', layer)]}).encode()
        responses = {'/v2/': (b'{}', 'application/json'),
            '/v2/transfer-fixture/manifests/' + sha(manifest): (manifest, manifest_type),
            '/v2/transfer-fixture/blobs/' + sha(config): (config, 'application/octet-stream'),
            '/v2/transfer-fixture/blobs/' + sha(layer): (layer, 'application/octet-stream')}
        release = Event()
        sent, progress = [], []

        class Registry(BaseHTTPRequestHandler):
            """回环上游只提供本例唯一镜像。"""

            def handle_one_request(self):
                """让 Engine 对回环仓库从 TLS 探测回落到 HTTP。@return 无。"""
                if self.rfile.peek(1).startswith(b'\x16'):
                    self.wfile.write(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                    self.close_connection = True
                    return
                super().handle_one_request()

            def log_message(self, *_):
                """隐藏本地请求日志。@return 无。"""

            def do_HEAD(self):
                """报告同摘要内容的固定大小。@return 无。"""
                self._send(False)

            def do_GET(self):
                """提供制品及分段层。@return 无。"""
                self._send(True)

            def _send(self, include_body):
                value = responses.get(urlsplit(self.path).path)
                if value is None:
                    self.send_error(404)
                    return
                content, media = value
                self.send_response(200)
                self.send_header('Content-Type', media)
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Docker-Content-Digest', sha(content))
                self.send_header('Docker-Distribution-Api-Version', 'registry/2.0')
                self.end_headers()
                if include_body:
                    if content is layer:
                        self.wfile.write(layer[:len(layer) // 2])
                        release.wait(8)
                        self.wfile.write(layer[len(layer) // 2:])
                        sent.append(len(layer))
                    else:
                        self.wfile.write(content)

        def report(value):
            progress.append(value)
            current = value['downloaded_bytes']
            if current is not None and 0 < current < len(layer):
                release.set()

        with tempfile.TemporaryDirectory() as folder, ThreadingHTTPServer(('127.0.0.1', 0), Registry) as registry:
            thread = Thread(target=registry.serve_forever, daemon=True)
            thread.start()
            reference = f'127.0.0.1:{registry.server_port}/transfer-fixture@{sha(manifest)}'
            with patch.dict(os.environ, {'DOCKER_CONFIG': folder, 'DOCKER_AUTH_CONFIG': '', 'DOCKER_API_VERSION': ''}):
                try:
                    pull_image('unix:///var/run/docker.sock', reference, 'control', report, timeout=30)
                    self.assertTrue(release.is_set(), progress)
                    self.assertEqual([len(layer)], sent)
                    self.assertEqual((len(layer), len(layer)),
                        (progress[-1]['downloaded_bytes'], progress[-1]['total_bytes']))
                    cached = []
                    pull_image('unix:///var/run/docker.sock', reference, 'account', cached.append, timeout=30)
                    self.assertEqual(('cached', 0), (cached[-1]['state'], cached[-1]['downloaded_bytes']))
                    self.assertEqual([len(layer)], sent)
                finally:
                    subprocess.run(['docker', '-H', 'unix:///var/run/docker.sock', 'image', 'rm', reference],
                        check=False, capture_output=True, timeout=20)
                    registry.shutdown()
                    thread.join(5)


class HostNetworkNamesTests(unittest.TestCase):
    """宿主控制连接在单部署迁移前后使用真实受控网络。"""

    def test_legacy_retry_archives_only_a_restored_node_job(self) -> None:
        """旧编排服务重试前归档原终态，未恢复的记录留给原操作。@return 无。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host = HostDeployment({'state_root': str(root), 'data_root': str(root / 'data'),
                'env_file': str(root / 'v3.env'), 'deployment': 'test'})
            old_id, epoch, new_id = (str(uuid.uuid4()) for _ in range(3))
            node_key, job_id = 'a' * 32, 'b' * 32
            previous = root / 'operations' / old_id / 'operation.json'
            journal = host.data / 'bench/cluster-private' / node_key / 'maintenance/current.json'
            job = {'node_id': 2, 'node_key': node_key, 'job_id': job_id, 'old_release': 'ci-1-1',
                'platform_operation': old_id, 'platform_epoch': epoch, 'phase': 'platform_restored'}
            prior = {'operation_id': old_id, 'phase': 'restored', 'epoch': epoch,
                'cluster_nodes': {'nodes': [{'node_id': 2, 'node_key': node_key,
                    'job_id': job_id, 'phase': 'platform_restored'}]}}
            operation = {'operation_id': new_id, 'before': {'nodes': [{'id': 2, 'node_key': node_key,
                'kind': 'ssh', 'preparation': {'state': 'prepared', 'release': 'ci-1-1'}}]}}
            atomic_json(journal, job)
            atomic_json(previous, {**prior, 'phase': 'reconcile'})
            with self.assertRaisesRegex(ValueError, '恢复归属需要核对'):
                host._archive_restored_node_jobs(operation)
            raw = journal.read_bytes()
            atomic_json(previous, prior)
            host._archive_restored_node_jobs(operation)
            self.assertFalse(journal.exists())
            self.assertEqual(journal.with_name(job_id + '.json').read_bytes(), raw)
            host._archive_restored_node_jobs(operation)

    def test_control_probe_retains_independent_http_and_connection_failures(self) -> None:
        """网关错误不能遮住调度器超时，原始响应正文保持私有。@return 无。"""
        host = HostDeployment({'state_root': '/test', 'data_root': '/test/data',
            'env_file': '/test/v3.env', 'deployment': 'test'})
        failure = HTTPError('http://127.0.0.1', 503, 'private-body', {}, io.BytesIO(b'private-body'))
        with patch.object(host, 'request', side_effect=[failure, URLError(TimeoutError())]) as request, \
                patch('system_update_host.time.monotonic', side_effect=[0.0, 0.1, 0.2, 0.3, 0.9, 1.0, 1.0]), \
                patch('system_update_host.time.sleep'):
            with self.assertRaises(ControlHealthTimeout) as failure:
                host.wait_controls(1.0)
            recorded = failure.exception.probes
            self.assertEqual(recorded['gateway']['state'], 'http_error')
            self.assertEqual(recorded['gateway']['http_status'], 503)
            self.assertEqual(recorded['orchestrator']['state'], 'timeout')
            self.assertNotIn('private-body', str(recorded))
            self.assertEqual([call.args[0] for call in request.call_args_list], ['gateway', 'orchestrator'])
            self.assertAlmostEqual(request.call_args.kwargs['timeout'], 0.7)

    def test_interrupted_project_preparation_stops_only_its_worker(self) -> None:
        """准备超时仅停止本候选容器，保留原版且没有发布回执。@return 无。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host = HostDeployment({'state_root': str(root), 'data_root': str(root / 'data'),
                'env_file': str(root / 'v3.env'), 'deployment': 'test'})
            binding = {'deployment': 'test', 'release': 'ci-12-1', 'source': '/repo/project_library'}
            name = 'test-project-library-ci-12-1'
            containers = [{'Name': '/' + name, 'Image': 'candidate-image', 'Id': 'owned',
                'Config': {'Labels': {'vibebench.project-library-owner': name}}},
                {'Name': '/foreign', 'Image': 'candidate-image', 'Id': 'foreign',
                    'Config': {'Labels': {'vibebench.project-library-owner': name}}}]
            with patch.object(host, 'values'), patch('system_update_host.docker', side_effect=[
                    '', subprocess.TimeoutExpired(['docker', 'run'], 1800), 'owned foreign', json.dumps(containers), '']) as docker:
                with self.assertRaisesRegex(TimeoutError, '候选项目库准备超时'):
                    host._prepare_project_library(binding, 'candidate-image')
            self.assertEqual(docker.call_args.args, ('stop', 'owned'))
            self.assertFalse((host.root / 'socket/project-library-ci-12-1.json').exists())

    def test_control_probe_retains_http_status_for_invalid_json(self) -> None:
        """无效响应仍显示真实 HTTP 状态，下一次探测可成功。@return 无。"""
        host = HostDeployment({'state_root': '/test', 'data_root': '/test/data',
            'env_file': '/test/v3.env', 'deployment': 'test'})

        def reply(role, path, body=None, *, timeout, on_status):
            on_status(200)
            if role == 'orchestrator' and host.request.call_count == 2:
                raise ValueError('无效 JSON')
            return {'scope': 'central'}

        with patch.object(host, 'request', side_effect=reply), \
                patch('system_update_host.time.monotonic', side_effect=[0.0, 0.1, 0.2, 0.3, 0.9, 1.0, 1.0]), \
                patch('system_update_host.time.sleep'):
            with self.assertRaises(ControlHealthTimeout) as failure:
                host.wait_controls(1.0, central_only=True)
            self.assertEqual(failure.exception.probes['orchestrator']['state'], 'invalid_response')
            self.assertEqual(failure.exception.probes['orchestrator']['http_status'], 200)
        with patch.object(host, 'request', side_effect=reply) as request, patch('system_update_host.time.sleep'), \
                patch('system_update_host.time.monotonic', return_value=0.0):
            result = host.wait_controls(1.0, central_only=True)
            self.assertEqual(result['orchestrator']['state'], 'ready')
            self.assertEqual(result['orchestrator']['attempts'], 2)
            self.assertEqual(request.call_args.args[2], {'central_only': True})

    def test_fast_abandon_reopens_gate_without_rolling_back_independent_node(self) -> None:
        """节点预取中，快速取消恢复中央门禁，旧版仍按原账本回退。@return 无。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host = HostDeployment({'state_root': str(root), 'data_root': str(root / 'data'),
                'env_file': str(root / 'v3.env'), 'deployment': 'test'})
            host.gate.mkdir()
            atomic_text(host.env, 'synthetic=1\n')
            controls = {'gateway': {'Id': 'original', 'Image': 'trusted', 'State': {'Status': 'running'}}}
            operation = {'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()),
                'revision': str(uuid.uuid4()), 'created_at': '2026-11-20T00:00:00Z',
                'target': {'release': 'system-ci-125-1'}, 'before': {
                    'env_sha256': hashlib.sha256(host.env.read_bytes()).hexdigest(),
                    'controls': {'gateway': {'id': 'original', 'image_id': 'trusted'}}, 'nodes': [{'id': 1}]}}
            atomic_json(host.gate / 'admission.json', {'schema_version': 1, 'deployment': 'test',
                'phase': 'idle', 'epoch': operation['epoch'], 'operation_id': None, 'target_release': None,
                'revision': operation['revision'], 'created_at': operation['created_at']})
            with patch.object(host, 'controls', return_value=controls), patch.object(host, 'request') as request:
                host.block(operation)
                host.abandon({**operation, 'fast_transition': True})
                self.assertEqual(read_gate(host.gate, 'test')['phase'], 'idle')
                request.assert_not_called()
                host.block(operation)
                host.abandon(operation)
                self.assertEqual(read_gate(host.gate, 'test')['phase'], 'idle')
                self.assertEqual(request.call_args.args[2]['action'], 'rollback')

    def test_capture_retries_blocked_partial_snapshot_before_freezing_role_sources(self) -> None:
        """只读竞争后的完整证明才进入冻结记录，持续未知时拒绝冻结。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host = HostDeployment({'state_root': str(root), 'data_root': str(root / 'data'),
                'env_file': str(root / 'v3.env'), 'deployment': 'test'})
            atomic_text(host.env, 'synthetic=1\n')
            controls = {role: {'Id': role, 'Image': 'trusted-image'} for role in ('gateway', 'orchestrator')}
            partial = {'phase': 'blocked', 'ready': False, 'environments': [{'environment_id': 'synthetic'}]}
            complete = {'phase': 'blocked', 'ready': True, 'environments': [{'environment_id': 'synthetic',
                'roles': {'network': {'image_id': 'original-image'}}}]}
            current = {'selection': {'control': {'config_digest': 'trusted-image'}}}
            with patch.object(host, 'values'), patch.object(host, 'controls', return_value=controls), \
                    patch.object(host, 'verify_images', return_value={'control': {'Id': 'trusted-image'}}), \
                    patch('system_update_host._container_image_matches', return_value=True), \
                    patch.object(host, 'metadata', return_value={'protected': True}) as metadata, \
                    patch.object(host, 'request', side_effect=[partial, complete]) as request, \
                    patch('system_update_host.time.sleep'):
                frozen = host.capture(current)
                self.assertEqual(frozen['environments'][0]['roles']['network']['image_id'], 'original-image')
                self.assertEqual(request.call_count, 2)
                metadata.assert_called_once()
            with patch.object(host, 'values'), patch.object(host, 'controls', return_value=controls), \
                    patch.object(host, 'verify_images', return_value={'control': {'Id': 'trusted-image'}}), \
                    patch('system_update_host._container_image_matches', return_value=True), \
                    patch.object(host, 'metadata') as metadata, patch.object(host, 'request', return_value=partial), \
                    patch('system_update_host.time.monotonic', side_effect=[0, 6]):
                with self.assertRaisesRegex(ValueError, '冻结快照'):
                    host.capture(current)
                metadata.assert_not_called()

    def test_remote_agy_ownership_stops_platform_capture_and_cutover(self) -> None:
        """普通和快速更新沿原快照退出，保留原节点执行组件。@return 无。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        controls = {'gateway': {'Image': 'trusted-image'}}
        current = {'selection': {'control': {'config_digest': 'trusted-image'}}}
        message = 'AGY 账号 #7 仍归属远程节点，请迁回本机后更新或回退平台'
        snapshot = {'agy_update_blockers': [message], 'environments': []}
        with patch.object(host, 'values'), patch.object(host, 'controls', return_value=controls), \
                patch.object(host, 'verify_images', return_value={'control': {'Id': 'trusted-image'}}), \
                patch('system_update_host._container_image_matches', return_value=True), \
                patch.object(host, 'metadata') as metadata, patch.object(host, '_runtime_snapshot', return_value=snapshot), \
                patch.object(host, 'request') as request:
            with self.assertRaisesRegex(ValueError, '迁回本机后更新或回退平台'):
                host.capture(current)
            with self.assertRaisesRegex(ValueError, '迁回本机后更新或回退平台'):
                host.drained({'rolling_accounts': True})
            metadata.assert_not_called()
            request.assert_not_called()

    def test_environment_retry_only_replays_pre_action_quiescence_conflicts(self) -> None:
        """仅两种前置排空冲突可沿原请求重试，代次冲突与提交未知直接上抛。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        body = {'generation': 7, 'operation_id': 'synthetic-operation'}
        for message in ('平台在途工作尚未排空', '其他环境仍有在途工作或未知证据', '环境身份或代次已经变化'):
            error = HTTPError('http://synthetic.invalid', 409, 'conflict', {},
                io.BytesIO(json.dumps({'detail': message}).encode()))
            with self.subTest(message=message), patch.object(host, 'request', side_effect=[error, {'state': 'ready'}]) as request, \
                    patch('system_update_host.time.sleep'):
                if message == '环境身份或代次已经变化':
                    with self.assertRaises(HTTPError):
                        host._environment_request(body)
                    self.assertEqual(request.call_count, 1)
                else:
                    self.assertEqual(host._environment_request(body), {'state': 'ready'})
                    self.assertEqual(request.call_count, 2)
                    self.assertTrue(all(call.args[2] is body for call in request.call_args_list))
        with patch.object(host, 'request', side_effect=TimeoutError('合成提交未知')) as request:
            with self.assertRaises(TimeoutError):
                host._environment_request(body)
            self.assertEqual(request.call_count, 1)

    def test_settled_requires_fresh_ready_proof_and_preserves_persistent_blocker(self) -> None:
        """短暂读取竞争后重验，持续阻塞到期限仍返回原阻塞证明。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        blocked, ready = {'ready': False, 'blockers': ['合成占锁']}, {'ready': True, 'blockers': []}
        with patch.object(host, 'drained', side_effect=[blocked, ready]), patch('system_update_host.time.sleep'):
            self.assertIs(host._settled({}), ready)
        with patch.object(host, 'drained', return_value=blocked), patch('system_update_host.time.monotonic', side_effect=[0, 6]):
            self.assertIs(host._settled({}), blocked)

    def test_environment_update_preserves_blockers_before_any_rebuild(self) -> None:
        """账号重建前持久保存具体阻塞，错误详情可定位且角色操作保持关闭。:return: None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        current = {'environment_id': 'synthetic', 'origin': {'release': 'ci-old-1'},
            'roles': {'cli': {'state': 'running'}}}
        operation = {'original': {'selection': {'account': {}}}, 'before': {'environments': [current]}}
        selected = {'selection': {'account': {'release': 'ci-new-1'}}}
        evidence = {'ready': False, 'blockers': ['synthetic：持久执行登记尚未收口'], 'environments': [current]}
        saved = []
        with patch('system_update_host.account_rebuild_required', return_value=True), \
                patch.object(host, '_settled', return_value=evidence), \
                patch.object(host, '_environment_request') as request, patch.object(host, 'environment_cpu') as cpu:
            with self.assertRaisesRegex(ValueError, 'synthetic：持久执行登记尚未收口'):
                host.update_environments(operation, selected, lambda: saved.append(list(operation['blockers'])))
        self.assertEqual([evidence['blockers']], saved)
        self.assertEqual(evidence['blockers'], operation['blockers'])
        request.assert_not_called()
        cpu.assert_not_called()

    def test_failed_new_package_recovery_retires_only_persisted_environment_intents(self) -> None:
        """失败恢复先由候选程序收口已登记环境，完成回执阻止重复重建。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host = HostDeployment({'state_root': str(root), 'data_root': str(root / 'data'),
                'env_file': str(root / 'v3.env'), 'deployment': 'test'})
            operation = {'operation_id': 'synthetic-operation', 'epoch': 'synthetic-epoch',
                'original': {'selection': {'account': {'release': 'ci-1-1',
                    'reference': 'ghcr.io/silentflower/vibebench-v3-account:v3-ci-1-1'}}},
                'selected': {'selection': {'account': {'release': 'ci-2-1',
                    'reference': 'ghcr.io/silentflower/flower2api-account:v3-ci-2-1'}}},
                'environment_intents': {'synthetic': {'generation': 7, 'allowed_image_ids': ['old-image', 'new-image']}}}
            atomic_text(root / 'operations/synthetic-operation/candidate.env', 'synthetic=1\n')
            evidence = {'environments': [{'environment_id': 'synthetic', 'generation': 8},
                {'environment_id': 'unrelated', 'generation': 10}]}
            with patch.object(host, '_stop_controls'), patch.object(host, '_retire_legacy_controls'), \
                    patch.object(host, '_compose'), patch.object(host, '_connect_legacy_environments'), \
                    patch.object(host, 'wait_controls'), patch.object(host, 'request',
                        side_effect=[evidence, {'state': 'stopped'}]) as request:
                save = Mock()
                host._retire_restore_environments(operation, save)
                self.assertEqual(request.call_count, 2)
                body = request.call_args.args[2]
                self.assertEqual(body['action'], 'retire')
                self.assertEqual(body['environment_id'], 'synthetic')
                self.assertEqual(body['allowed_image_ids'], ['old-image', 'new-image'])
                self.assertIn('synthetic', operation['environment_restore_retired'])
                save.assert_called_once()
                host._retire_restore_environments(operation, save)
                self.assertEqual(request.call_count, 2)
                self.assertEqual(host.env.read_text(), 'synthetic=1\n')

    def test_historical_retirement_persists_proof_before_owner_removes_roles(self) -> None:
        """新到旧回退先持久意图，再由原所有者收口；重复及在途分别受控。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        selected = {'selection': {'account': {'release': 'ci-1-1',
            'reference': 'ghcr.io/silentflower/vibebench-v3-account:v3-ci-1-1'}}}
        environment = {'environment_id': 'synthetic', 'generation': 7,
            'roles': {role: {'state': 'running', 'image_id': 'new-image'} for role in ('cli', 'sender', 'network')}}
        operation = {'operation_id': 'synthetic-operation', 'epoch': 'synthetic-epoch',
            'original': {'selection': {'account': {'release': 'ci-2-1',
                'reference': 'ghcr.io/silentflower/flower2api-account:v3-ci-2-1'}}},
            'before': {'environments': [environment]}}
        evidence = {'ready': True, 'environments': [environment]}
        saved = []

        def save():
            """记录每次持久意图。@return None。"""
            saved.append(copy.deepcopy(operation))

        def retire(service, path, body, timeout):
            """验证副作用之前已经登记来源及资源。:param service: 服务。:param path: 路径。:param body: 维护请求。:param timeout: 秒。@return 收口回执。"""
            self.assertEqual(body['action'], 'retire')
            self.assertEqual(saved[-1]['environment_intents']['synthetic']['generation'], 7)
            self.assertEqual(set(saved[-1]['environment_intents']['synthetic']['allowed_image_ids']), {'old-image', 'new-image'})
            self.assertEqual(saved[-1]['environment_cpu_before']['synthetic']['cli'], 1500000000)
            return {'state': 'stopped', 'generation': 7}

        with patch.object(host, 'drained', return_value=evidence), \
                patch.object(host, 'environment_cpu', return_value={'cli': 1500000000, 'sender': 1000000000, 'network': 500000000}), \
                patch.object(host, 'verify_images', return_value={'account': {'Id': 'old-image'}}), \
                patch.object(host, 'request', side_effect=retire) as request:
            host._retire_rollback_environments(operation, selected, save)
            self.assertEqual(len(saved), 2)
            self.assertIn('synthetic', operation['environment_retired'])
            host._retire_rollback_environments(operation, selected, save)
            self.assertEqual(request.call_count, 1)
            operation.pop('environment_retired')
            evidence['ready'] = False
            with self.assertRaisesRegex(ValueError, '在途'):
                host._retire_rollback_environments(operation, selected, save)
            self.assertEqual(request.call_count, 1)

    def test_old_and_new_networks_and_ambiguous_rejection(self) -> None:
        """分别接纳新旧网络，缺失或同时存在时拒绝发送。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        for names in [('vibebench-v3-test',), ('flower2api-test',), (), ('vibebench-v3-test', 'flower2api-test')]:
            controls = {'orchestrator': {'NetworkSettings': {'Networks': {name: {'IPAddress': '10.0.0.2'} for name in names}}}}
            host.opener = Mock()
            host.opener.open.return_value = io.BytesIO(b'{}')
            with self.subTest(networks=names), patch.object(host, 'values', return_value={'V3_INTERNAL_TOKEN': 'synthetic'}), \
                    patch.object(host, 'controls', return_value=controls), patch('system_update_host.safe_read', return_value=b'synthetic'):
                if len(names) == 1:
                    self.assertEqual(host.request('orchestrator', '/health'), {})
                    self.assertEqual(host.opener.open.call_args.args[0].full_url, 'http://10.0.0.2:8000/health')
                else:
                    with self.assertRaisesRegex(ValueError, '网络'):
                        host.request('orchestrator', '/health')
                    host.opener.open.assert_not_called()

    def test_project_retirement_requires_frozen_stopped_controls(self) -> None:
        """改名只移除本操作的原控制角色；外来来源和运行状态拒绝删除。@return None。"""
        host = HostDeployment({'state_root': '/unused', 'data_root': '/unused-data',
            'env_file': '/unused-env', 'deployment': 'test'})
        gate = {'phase': 'blocked', 'epoch': 'synthetic-epoch', 'operation_id': 'synthetic-operation'}
        operation = {'epoch': gate['epoch'], 'operation_id': gate['operation_id'],
            'before': {'controls': {'gateway': {'id': 'original', 'image_id': 'old-image'}}}}
        original = {'Id': 'original', 'Image': 'old-image', 'State': {'Running': False},
            'Config': {'Labels': {'com.docker.compose.project': 'vibebench-v3-test'}}}
        for item, valid in [(original, True), ({**original, 'Id': 'foreign'}, False),
                ({**original, 'State': {'Running': True}}, False),
                ({**original, 'Config': {'Labels': {'com.docker.compose.project': 'other'}}}, False)]:
            with self.subTest(item=item), patch.object(host, 'controls', return_value={'gateway': item}), \
                    patch('system_update_host.read_gate', return_value=gate), patch('system_update_host.docker') as docker:
                if valid:
                    host._retire_legacy_controls(operation)
                    docker.assert_called_once_with('rm', 'original')
                else:
                    with self.assertRaises(ValueError):
                        host._retire_legacy_controls(operation)
                    docker.assert_not_called()

    def test_network_handoff_requires_registered_owned_role(self) -> None:
        """真实数据库登记绑定原网络角色，保留旧别名并拒绝未知来源。@return None。"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'bench').mkdir()
            environment = 'a' * 32
            with sqlite3.connect(root / 'bench/db.sqlite') as db:
                db.execute('CREATE TABLE account_environments(environment_id TEXT,network_container_id TEXT)')
                db.execute('INSERT INTO account_environments VALUES(?,?)', (environment, 'original-network'))
            host = HostDeployment({'state_root': str(root / 'updates'), 'data_root': str(root),
                'env_file': str(root / 'v3.env'), 'deployment': 'test'})
            labels = {'vibebench.product': 'v3', 'vibebench.deployment': 'test',
                'vibebench.environment': environment, 'vibebench.role': 'account-network'}
            item = {'Id': 'original-network', 'Image': 'old-image', 'Config': {'Labels': labels},
                'State': {'Running': True},
                'Name': '/' + account_container_prefix('test', legacy=True) + environment,
                'NetworkSettings': {'Networks': {'vibebench-v3-test': {'IPAddress': '10.0.0.2'}}}}
            operation = {'before': {'environments': [{'environment_id': environment,
                'roles': {'network': {'image_id': 'old-image'}}}]}, 'selected': {'selection': {}}}
            controls = {role: {'State': {'Running': True}, 'NetworkSettings': {'Networks': {
                'flower2api-test': {'IPAddress': address}}}} for role, address in
                (('gateway', '10.1.0.2'), ('orchestrator', '10.1.0.3'))}
            for mode in ('running', 'foreign', 'stopped', 'connected'):
                observed = copy.deepcopy(item)
                if mode == 'foreign':
                    observed['Config']['Labels']['vibebench.environment'] = 'b' * 32
                elif mode == 'stopped':
                    observed['State']['Running'] = False
                elif mode == 'connected':
                    observed['NetworkSettings']['Networks']['flower2api-test'] = {'IPAddress': '10.1.0.2'}
                with self.subTest(mode=mode), patch.object(host, 'verify_images', return_value={'account': {'Id': 'new-image'}}), \
                        patch.object(host, 'controls', return_value=controls), \
                        patch('system_update_host.docker', side_effect=[json.dumps([{'Labels': labels,
                            'IPAM': {'Config': [{'Gateway': '10.1.0.1'}]}}]),
                            'original-network', json.dumps([observed]), '', '']) as docker:
                    if mode == 'foreign':
                        with self.assertRaisesRegex(ValueError, '来源或名称'):
                            host._connect_legacy_environments(operation)
                        self.assertEqual(docker.call_count, 3)
                    elif mode == 'stopped':
                        host._connect_legacy_environments(operation)
                        self.assertEqual(docker.call_count, 3)
                    else:
                        host._connect_legacy_environments(operation)
                        if mode == 'running':
                            self.assertEqual(docker.call_args_list[-2].args, ('network', 'connect', '--gw-priority=-1', '--alias',
                                item['Name'].lstrip('/'), 'flower2api-test', 'original-network'))
                        else:
                            self.assertEqual(docker.call_count, 4)
                        self.assertEqual(docker.call_args.args, ('exec', '--env',
                            'V3_MANAGEMENT_ADDRESSES=["10.1.0.1", "10.1.0.2", "10.1.0.3"]',
                            'original-network', 'python3', '/usr/local/bin/v3-network-guard'))


class HostMetadataTests(unittest.TestCase):
    """核对软件字段、账号身份及结构证据的真实持久效果。"""

    def setUp(self) -> None:
        """建立独立双库和合成画像。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ('bench', 'gateway'):
            (self.root / name).mkdir()
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('CREATE TABLE account_environments(environment_id TEXT,name TEXT,account_id INTEGER,fingerprint_json TEXT)')
            database.execute('INSERT INTO account_environments VALUES(?,?,?,?)', ('synthetic', 'synthetic', 1, '{"memory":"1536m","device":"synthetic"}'))
            database.execute('CREATE TABLE accounts(id INTEGER,name TEXT,profile_path TEXT,cc2api_account_id INTEGER)')
            database.execute('INSERT INTO accounts VALUES(1,"synthetic","profiles/synthetic",1)')
            for name in ('account_credential_ownerships', 'local_credential_authorizations'):
                database.execute('CREATE TABLE ' + name + '(account_id INTEGER,record_json TEXT)')
        self.environment = {'version': 'old', 'node_version': 'old-node', 'device_id': 'synthetic-private-device',
            'unknown': {'keep': True}, 'timezone': 'Asia/Tokyo'}
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            database.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,canonical_env TEXT,email TEXT,device_id TEXT,account_uuid TEXT,organization_uuid TEXT)')
            database.execute('CREATE TABLE oauth_account_ownerships(account_id INTEGER,record_json TEXT)')
            database.execute('INSERT INTO accounts(id,canonical_env) VALUES(?,?)', (1, json.dumps(self.environment)))
        self.host = HostDeployment({'state_root': str(self.root / 'updates'), 'data_root': str(self.root),
            'env_file': str(self.root / 'v3.env')})

    def change(self, value: dict) -> None:
        """更新合成画像。:param value: 新值。@return None。"""
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            database.execute('UPDATE accounts SET canonical_env=? WHERE id=1', (json.dumps(value),))

    def test_software_compensation_preserves_identity_unknown_and_absent_fields(self) -> None:
        """仅补偿声明的四个字段，缺失和存在 null 保持区别。@return None。"""
        before = self.host.metadata()
        value = {**self.environment, 'version': 'new', 'version_base': None, 'build_time': 'new-time'}
        self.change(value)
        after = self.host.metadata()
        self.assertEqual(before['identity_sha256'], after['identity_sha256'])
        self.host.restore_software(before['software'], after['software'])
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            restored = json.loads(database.execute('SELECT canonical_env FROM accounts').fetchone()[0])
        self.assertEqual(restored, self.environment)
        self.assertEqual(self.host.metadata(), before)

    def test_software_conflict_rolls_back_transaction(self) -> None:
        """迟到的软件恢复遇到并发变化时事务保持原数据。@return None。"""
        before = self.host.metadata()
        self.change({**self.environment, 'version': 'observed'})
        observed = self.host.metadata()
        self.change({**self.environment, 'version': 'concurrent'})
        with self.assertRaisesRegex(ValueError, '并发变化'):
            self.host.restore_software(before['software'], observed['software'])
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            self.assertEqual(json.loads(database.execute('SELECT canonical_env FROM accounts').fetchone()[0])['version'], 'concurrent')

    def test_identity_and_schema_changes_are_visible(self) -> None:
        """设备、资源和数据库结构变化均能被独立证据识别。@return None。"""
        before = self.host.metadata()
        changed = copy.deepcopy(self.environment)
        changed['device_id'] = 'different'
        self.change(changed)
        self.assertNotEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])
        self.change(self.environment)
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('ALTER TABLE account_environments ADD COLUMN changed TEXT')
        after = self.host.metadata()
        self.assertEqual(after['identity_sha256'], before['identity_sha256'])
        self.assertNotEqual(after['database_schema']['bench'], before['database_schema']['bench'])

    def test_metadata_closes_database_descriptors_before_snapshot(self) -> None:
        """元数据读取结束后释放持库句柄，明确识别仍在运行的读取者。@return None。"""
        gc.collect()
        self.host.metadata()
        assert_quiescent(self.root)
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database:
            database.execute('SELECT * FROM accounts').fetchall()
            with self.assertRaisesRegex(ValueError, '仍有本机进程'):
                assert_quiescent(self.root)
        assert_quiescent(self.root)

    def test_snapshot_restore_retains_registered_role_recovery_and_generation(self) -> None:
        """双库恢复后保留候选角色收口登记，事务回执中断可幂等续接。@return None。"""
        gc.collect()
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database, database:
            for name, kind in [('generation', 'INTEGER DEFAULT 4'), ('container_id', 'TEXT'),
                    ('network_container_id', 'TEXT'), ('sender_container_id', 'TEXT'),
                    ('state', "TEXT DEFAULT 'ready'"), ('isolation_version', 'INTEGER DEFAULT 2')]:
                database.execute('ALTER TABLE account_environments ADD COLUMN ' + name + ' ' + kind)
        operation = {'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()),
            'original': {'release': {'release': 'system-ci-1-1'}}, 'environment_intents': {'synthetic': {'generation': 4}}}
        folder = self.root / 'snapshot'
        create_snapshot(self.root, folder, 'test', operation)
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database, database:
            database.execute("UPDATE account_environments SET generation=5,container_id='candidate-cli',network_container_id='candidate-network',sender_container_id='candidate-sender'")
        self.host.capture_restore_bindings(operation, folder, lambda: None)
        restore_snapshot(self.root, folder, 'test', operation, lambda: None)
        before_receipt = copy.deepcopy(operation)
        with self.assertRaisesRegex(RuntimeError, '合成回执中断'):
            self.host.restore_environment_bindings(operation, Mock(side_effect=RuntimeError('合成回执中断')))
        operation = before_receipt
        self.host.restore_environment_bindings(operation, lambda: None)
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database:
            self.assertEqual(database.execute('SELECT generation,container_id FROM account_environments').fetchone(), (5, 'candidate-cli'))
        operation['environment_restore_bindings_applied'] = False
        with closing(sqlite3.connect(self.root / 'bench/db.sqlite')) as database, database:
            database.execute('UPDATE account_environments SET generation=6')
        with self.assertRaisesRegex(ValueError, '后来或外来'):
            self.host.restore_environment_bindings(operation, lambda: None)

    def test_binding_and_credential_ownership_changes_are_visible(self) -> None:
        """账号绑定和单一凭据所有权属于受保护身份。@return None。"""
        before = self.host.metadata()
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('UPDATE accounts SET cc2api_account_id=2 WHERE id=1')
        self.assertNotEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])
        with sqlite3.connect(self.root / 'bench/db.sqlite') as database:
            database.execute('UPDATE accounts SET cc2api_account_id=1 WHERE id=1')
        self.assertEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])
        with sqlite3.connect(self.root / 'gateway/gateway.sqlite') as database:
            database.execute('INSERT INTO oauth_account_ownerships VALUES(1,?)', ('{"owner":"changed"}',))
        self.assertNotEqual(self.host.metadata()['identity_sha256'], before['identity_sha256'])

    def test_restore_reacquires_released_gate_before_observing_new_work(self) -> None:
        """提交后恢复先重新关门，后来活动保持且切换尚未开始。@return None。"""
        operation = self.prepare_restore_gate('idle')
        self.host.request = Mock(side_effect=[{'active': 0, 'environments': []}, {'active': 1}])
        self.host.verify_images = Mock()
        with self.assertRaisesRegex(ValueError, '恢复前仍有在途'):
            self.host.restore(operation, lambda: None)
        self.assertEqual(read_gate(self.host.gate, 'test')['phase'], 'blocked')
        self.host.verify_images.assert_not_called()

    def test_fenced_restore_can_reach_images_when_candidate_api_is_down(self) -> None:
        """原门禁持续关闭时，可恢复尚未启动的候选控制服务。@return None。"""
        operation = self.prepare_restore_gate('blocked')
        self.host.request = Mock(side_effect=RuntimeError('候选 API 尚未启动'))
        self.host.verify_images = Mock(side_effect=ValueError('到达原版镜像核验'))
        with self.assertRaisesRegex(ValueError, '到达原版镜像核验'):
            self.host.restore(operation, lambda: None)
        self.host.request.assert_not_called()

    def prepare_restore_gate(self, phase: str) -> dict:
        """建立同操作的实际持久门禁。:param phase: 原阶段。@return 恢复输入。"""
        self.host.policy['deployment'] = 'test'
        self.host.gate.mkdir(parents=True)
        operation = {'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()), 'revision': str(uuid.uuid4()),
            'target': {'release': 'system-ci-1-1'}, 'created_at': '2026-11-11T00:00:00Z', 'original': {'selection': {}}}
        atomic_json(self.host.gate / 'admission.json', {'schema_version': 1, 'deployment': 'test',
            'operation_id': operation['operation_id'] if phase == 'blocked' else None, 'epoch': operation['epoch'],
            'revision': operation['revision'], 'phase': phase, 'target_release': 'system-ci-1-1' if phase == 'blocked' else None,
            'created_at': operation['created_at']})
        return operation


if __name__ == '__main__':
    unittest.main()
