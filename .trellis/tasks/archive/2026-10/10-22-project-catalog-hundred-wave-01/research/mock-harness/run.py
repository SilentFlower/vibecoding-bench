#!/usr/bin/env python3
"""建立本次内部网络及空数据试跑，保留证据后只清理本次容器和网络。"""
import argparse
import hashlib
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import docker
from docker.types import IPAMConfig, IPAMPool

REPOSITORY = Path.cwd()
sys.path.insert(0, str(REPOSITORY/'deploy/v3'))
from run_local_verification import scenario_loopback_forward


def write_json(path: Path, value: dict) -> None:
    """写入本次运行资料。@param path 目标。@param value 资料。@return None。"""
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def main() -> None:
    """执行正式内容的隔离模拟试跑。@return None；失败时非零退出。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--evidence-dir', required=True, type=Path)
    parser.add_argument('--timeout-sec', default=9000, type=int)
    parser.add_argument('--account-runtime-overlay', type=Path)
    args = parser.parse_args()
    args.bundle = args.bundle.resolve(strict=True)
    args.evidence_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.evidence_dir = args.evidence_dir.resolve()
    manifest = json.loads(args.manifest.read_text())
    write_json(args.evidence_dir/'manifest.json', manifest)
    overlay = None
    if args.account_runtime_overlay is not None:
        if args.account_runtime_overlay.is_symlink():
            raise ValueError('本地修复覆盖必须是普通文件，不能是链接')
        overlay = args.account_runtime_overlay.resolve(strict=True)
        if not overlay.is_file() or overlay.name != 'account_runtime.py':
            raise ValueError('仅支持单个 account_runtime.py 的明确本地修复覆盖')
    source_identity = {'base_release': manifest['release'], 'base_parent_revision': manifest['parent_revision'],
        'account_runtime_overlay': {'enabled': overlay is not None,
            'sha256': hashlib.sha256(overlay.read_bytes()).hexdigest() if overlay is not None else None,
            'host_path': str(overlay) if overlay is not None else None,
            'container_path': '/app/account_runtime.py' if overlay is not None else None},
        'local_fix_not_deployed': overlay is not None}
    source_overlay = {'module': 'account_runtime.py',
        'sha256': source_identity['account_runtime_overlay']['sha256'], 'base_release': manifest['release'],
        'deployed': False} if overlay is not None else None
    source_identity['source_overlay'] = source_overlay
    source_identity['catalog_override'] = json.loads((args.bundle/'fixtures/catalog-identity.json').read_text())
    pilot = args.bundle
    assert (pilot/'fixtures/mock_cli.py').is_file() and (pilot/'fixtures/recipes.json').is_file()
    client = docker.from_env()
    for role in ('control', 'account'):
        image = client.images.get(manifest['images'][role]['reference'])
        expected = manifest['images'][role]['registry_digest']
        assert any(item.endswith('@'+expected) for item in image.attrs.get('RepoDigests', [])), (role, '镜像摘要不符')
        assert image.attrs['Architecture'] == 'amd64' and image.attrs['Os'] == 'linux'
    deployment = 'mock-formal-'+uuid.uuid4().hex[:12]
    labels = {'vibebench.product': 'v3', 'vibebench.deployment': deployment}
    used = [ipaddress.ip_network(item['Subnet']) for existing in client.networks.list()
        for item in existing.attrs.get('IPAM', {}).get('Config') or [] if item.get('Subnet')]
    routes = json.loads(subprocess.check_output(['ip', '-j', 'route', 'show']))
    used.extend(ipaddress.ip_network(item['dst']) for item in routes if item.get('dst') not in (None, 'default'))
    network = None
    for index in range(200, 250):
        subnet = ipaddress.ip_network(f'10.232.{index}.0/24')
        if any(subnet.overlaps(item) for item in used if item.version == 4):
            continue
        try:
            network = client.networks.create('vibebench-v3-'+deployment, internal=True, labels=labels,
                ipam=IPAMConfig(pool_configs=[IPAMPool(subnet=str(subnet))]))
            break
        except docker.errors.APIError as error:
            if 'Pool overlaps' not in str(error):
                raise
    if network is None:
        raise RuntimeError('没有可用的独立验证子网')
    containers, runner, result = [], None, None
    root = Path(tempfile.mkdtemp(prefix='runtime-', dir=args.evidence_dir))
    token_file = args.evidence_dir/'service-token'
    service_token = uuid.uuid4().hex+uuid.uuid4().hex
    token_file.write_text(service_token)
    token_file.chmod(0o600)
    verifier_identity = hashlib.sha256(json.dumps(str(root/'data'), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

    def owned_containers():
        """只枚举本次随机部署和本次数据根的原生验证容器。@return 唯一容器列表。"""
        owned = client.containers.list(all=True, filters={'label': [
            'vibebench.product=v3', 'vibebench.deployment='+deployment]})
        native = client.containers.list(all=True, filters={'label': [
            'vibebench.project-verifier=native', 'vibebench.verifier-root='+verifier_identity]})
        return list({item.id: item for item in owned+native}.values())

    try:
        fixtures = root/'fixtures'
        shutil.copytree(REPOSITORY/'deploy/v3/fixtures', fixtures)
        shutil.copy2(pilot/'fixtures/mock_cli.py', fixtures/'mock_cli.py')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=api.anthropic.com', '-addext', 'subjectAltName=DNS:api.anthropic.com',
            '-keyout', str(root/'native-usage.key'), '-out', str(root/'native-usage.crt')],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        mock = client.containers.run(manifest['images']['control']['reference'], ['/fixtures/mock_network.py'],
            entrypoint='python', detach=True, network=network.name, labels={**labels, 'vibebench.role': 'verification'},
            volumes={str(fixtures): {'bind': '/fixtures', 'mode': 'ro'}, str(root): {'bind': '/fixtures-data', 'mode': 'rw'}})
        mock.reload()
        proxy = mock.attrs['NetworkSettings']['Networks'][network.name]['IPAddress']
        environment = {'PYTHONPATH': '/app:/source/deploy/v3', 'V3_DEPLOYMENT_ID': deployment,
            'V3_RELEASE': manifest['release'], 'V3_ACCOUNT_IMAGE': manifest['images']['account']['reference'],
            'V3_NETWORK': network.name, 'VERIFY_HOST_ROOT': str(root), 'VERIFY_SOURCE_ROOT': str(REPOSITORY),
            'V3_WORKER_SCRIPT': '/opt/v3/worker.sh', 'V3_ACCOUNT_MEMORY': '1536m', 'V3_ACCOUNT_SWAP': '2048m',
            'VERIFY_PROJECT_SCENARIOS_ONLY': '1', 'V3_INTERNAL_TOKEN': service_token,
            'WEBUI_DIR': '/webui', 'WEBUI_USER': '', 'WEBUI_PASS': '', 'PER_ACCOUNT_CONCURRENCY': '2',
            'VERIFY_SOURCE_IDENTITY': json.dumps(source_identity, ensure_ascii=False)}
        runner_volumes = {str(REPOSITORY): {'bind': '/source', 'mode': 'ro'},
            str(pilot/'library'): {'bind': '/repo/project_library', 'mode': 'ro'},
            str(Path(__file__).resolve().parent): {'bind': '/harness', 'mode': 'ro'}, str(pilot/'fixtures'): {'bind': '/pilot', 'mode': 'ro'},
            str(fixtures): {'bind': '/fixtures', 'mode': 'ro'}, str(root): {'bind': '/verify', 'mode': 'rw'},
            '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'rw'}}
        if overlay is not None:
            runner_volumes[str(overlay)] = {'bind': '/app/account_runtime.py', 'mode': 'ro'}
        runner = client.containers.run(manifest['images']['control']['reference'], ['/harness/run_formal.py', '--proxy-ip', proxy],
            entrypoint='python', detach=True, network=network.name, labels={**labels, 'vibebench.role': 'orchestrator'},
            environment=environment, volumes=runner_volumes)
        runner.reload()
        address = runner.attrs['NetworkSettings']['Networks'][network.name]['IPAddress']
        write_json(args.evidence_dir/'runtime.json', {'deployment': deployment, 'runner_id': runner.id,
            'network': network.name, 'internal': True, 'root': str(root), 'release': manifest['release'],
            'verifier_identity': verifier_identity, 'model_calls': 0, 'source_identity': source_identity,
            'source_overlay': source_overlay})
        with scenario_loopback_forward(address) as base_url:
            connection = {'base_url': base_url, 'service_token_file': str(token_file), 'batch_ids': [],
                'browser_ready_file': str(root/'browser-ready.json'), 'browser_done_file': str(root/'browser-done.json'),
                'db_path': str(root/'data/scenario.sqlite'), 'evidence_dir': str(args.evidence_dir),
                'expected_selected_task_counts': [stage['count'] for stage in json.loads((pilot/'fixtures/stages.json').read_text())], 'synthetic': True,
                'source_identity': source_identity}
            write_json(args.evidence_dir/'connection.json', connection)
            print('隔离模拟试跑已启动；连接资料：'+str(args.evidence_dir/'connection.json'), flush=True)
            deadline = time.monotonic()+args.timeout_sec
            published = False
            while time.monotonic() < deadline:
                runner.reload()
                if not published and (root/'browser-ready.json').exists():
                    ready = json.loads((root/'browser-ready.json').read_text())
                    connection.update(batch_ids=ready['batch_ids'], stages=ready['stages'])
                    write_json(args.evidence_dir/'connection.json', connection)
                    print('本批新增内容模拟完成，等待只读浏览器；连接资料已更新。', flush=True)
                    published = True
                if runner.status != 'running':
                    result = runner.wait(timeout=30)
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError('本次隔离验证超过外层截止时间')
        if result['StatusCode'] != 0:
            raise RuntimeError('隔离验证运行器失败，退出码 '+str(result['StatusCode']))
    finally:
        # 先停止唯一标签范围的写入者，才能复制数据库和清理目录。
        for instance in owned_containers():
            try:
                instance.stop(timeout=2)
            except docker.errors.NotFound:
                pass
        for instance in owned_containers():
            role = instance.labels.get('vibebench.role', 'native')
            try:
                (args.evidence_dir/(role+'-'+instance.short_id+'.log')).write_bytes(instance.logs())
            except docker.errors.NotFound:
                pass
        if runner is not None:
            try:
                (args.evidence_dir/'runner.log').write_bytes(runner.logs())
            except docker.errors.NotFound:
                pass
        if (root/'evidence').exists():
            shutil.copytree(root/'evidence', args.evidence_dir/'evidence', dirs_exist_ok=True, symlinks=True)
        for path in root.glob('*.json'):
            shutil.copy2(path, args.evidence_dir/path.name)
        for name in ('tls.jsonl', 'usage-calls.jsonl'):
            path = root/name
            if path.exists():
                shutil.copy2(path, args.evidence_dir/name)
        if not (args.evidence_dir/'evidence/private-synthetic.sqlite').exists() and (root/'data/scenario.sqlite').exists():
            import sqlite3
            with sqlite3.connect(root/'data/scenario.sqlite') as source, sqlite3.connect(args.evidence_dir/'failure-private-synthetic.sqlite') as saved:
                source.backup(saved)
            (args.evidence_dir/'failure-private-synthetic.sqlite').chmod(0o600)
        removed = []
        for instance in owned_containers():
            removed.append(instance.id)
            instance.remove(force=True)
        network.remove()
        token_file.unlink(missing_ok=True)
        shutil.rmtree(root)
        write_json(args.evidence_dir/'cleanup.json', {'status': 'passed', 'deployment': deployment,
            'removed_container_ids': removed, 'removed_network': network.name, 'remaining_owned_containers': len(owned_containers()),
            'runtime_removed': not root.exists(), 'temporary_token_removed': not token_file.exists(),
            'real_model_calls': 0, 'production_touched': False})
    print('已保留隔离模拟证据并清理本次资源：'+str(args.evidence_dir), flush=True)


if __name__ == '__main__':
    main()
