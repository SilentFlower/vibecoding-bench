#!/usr/bin/env python3
"""用真实旧/新镜像和合成两库验证迁移，失败阻止生成发布兼容证据。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import sqlite3
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from threading import Event
from urllib.error import HTTPError

from manage import _local_image_matches
from runtime_files import atomic_json
from system_release import REPO, data_contracts, migration_registries
from system_update_contract import (DOWNLOAD_ROOT, INDEX_LIMIT, MANIFEST_LIMIT, REPOSITORY, fetch_bytes,
    fetch_repository_file, strict_json, validate_index, validate_release, verify_signed)
from system_update_database import create_snapshot, restore_snapshot


BENCH_PROBE = '''
import main
main.init_db()
token = main._make_session_token(main.WEBUI_USER)
if main._verify_session_token(token) != main.WEBUI_USER:
    raise RuntimeError('合成会话读写失败')
c = main.get_db()
try:
    with c:
        value = c.execute("SELECT profile_path FROM accounts WHERE name='migration-proof'").fetchone()
        if value is None:
            c.execute("INSERT INTO accounts(name,profile_path,enabled) VALUES(?,?,0)", ('migration-proof','profiles/synthetic-proof'))
        elif value['profile_path'] != 'profiles/synthetic-proof':
            raise RuntimeError('合成账号来源改变')
finally:
    c.close()
print('bench-read-write-passed')
'''

GATEWAY_PROBE = '''
import json
from urllib.request import Request, urlopen
base='http://127.0.0.1:5674/admin/settings'
headers={'Authorization':'Bearer synthetic-database-proof','Content-Type':'application/json'}
with urlopen(Request(base,headers=headers),timeout=2) as response:
    value=json.load(response)
key='allow_system_role_models'
with urlopen(Request(base,data=json.dumps({key:value[key]}).encode(),headers=headers,method='PUT'),timeout=2) as response:
    response.read()
with urlopen(Request(base,headers=headers),timeout=2) as response:
    after=json.load(response)
if after[key] != value[key]:
    raise RuntimeError('网关合成配置读写失败')
print('gateway-read-write-passed')
'''

GATEWAY_FIXTURE = '''
import sqlite3
c=sqlite3.connect('/data/gateway.sqlite')
try:
    with c:
        row=c.execute("SELECT token,device_id FROM accounts WHERE email='migration-proof@example.invalid'").fetchone()
        if row is None:
            c.execute("INSERT INTO accounts(email,token,device_id,status) VALUES(?,?,?,'disabled')", ('migration-proof@example.invalid','synthetic-token','synthetic-device'))
        elif row != ('synthetic-token','synthetic-device'):
            raise RuntimeError('合成凭据或设备身份改变')
finally:
    c.close()
print('gateway-fixture-passed')
'''


def command(*arguments: str, timeout: int = 300) -> str:
    """执行无 shell 的固定验证命令，错误不回显认证材料。

    :param arguments: 固定命令和已核验参数。
    :param timeout: 单次期限。
    :return: 完整标准输出。
    """
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('真实数据库兼容验证命令失败：' + arguments[0] + '\n' + result.stderr[-1500:])
    return result.stdout


def image_identity(reference: str, expected: str, registry_digest: str) -> str:
    """核对真实镜像身份。:param reference: 精确引用。:param expected: 配置摘要。:param registry_digest: 受信镜像摘要。:return: 本机镜像ID。"""
    actual = json.loads(command('docker', 'image', 'inspect', reference))[0]
    if not _local_image_matches(reference, actual, {'digest': expected, 'config_digest': expected, 'registry_digest': registry_digest}):
        raise ValueError('兼容演练镜像与签名配置摘要不符')
    return actual['Id']


def _container_arguments(directory: Path) -> list[str]:
    return ['--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
        '--pids-limit', '128', '--memory', '768m', '--user', f'{os.getuid()}:{os.getgid()}',
        '--label', 'vibebench.product=v3', '--label', 'vibebench.verification=database-compatibility',
        '--mount', f'type=bind,source={directory},target=/data']


def python_probe(image: str, directory: Path, source: str) -> str:
    """在无网络镜像中运行固定合成验证程序。

    :param image: 核验过的镜像ID。
    :param directory: 独立数据目录。
    :param source: 本脚本固定的程序片段。
    :return: 验证回执。
    """
    identifier = command('docker', 'create', *_container_arguments(directory),
        '--env', 'BENCH_DATA=/data', '--env', 'WEBUI_USER=synthetic-user', '--env', 'WEBUI_PASS=synthetic-password',
        '--env', 'V3_DEPLOYMENT_ID=database-proof', '--entrypoint', 'python3', image, '-c', source).strip()
    try:
        output = command('docker', 'start', '--attach', identifier)
        actual = json.loads(command('docker', 'inspect', identifier))[0]
        if actual['State']['Running'] or actual['State']['ExitCode'] != 0:
            raise RuntimeError('真实数据库程序兼容验证失败')
        return output
    finally:
        command('docker', 'stop', '-t', '5', identifier)
        command('docker', 'rm', identifier)


def gateway_probe(image: str, directory: Path) -> None:
    """启动真实网关并通过实际管理API验证配置读写。

    :param image: 已核验原版或候选镜像ID。
    :param directory: 隔离网关数据目录。
    :return: None。
    """
    name = 'bench-database-proof-' + uuid.uuid4().hex
    identifier = command('docker', 'create', '--name', name, *_container_arguments(directory),
        '--env', 'DATABASE_DRIVER=sqlite', '--env', 'DATABASE_DSN=/data/gateway.sqlite',
        '--env', 'ADMIN_PASSWORD=synthetic-database-proof', '--env', 'SERVER_PORT=5674',
        '--entrypoint', '/app/claude-code-gateway', image).strip()
    try:
        command('docker', 'start', identifier)
        deadline = time.monotonic() + 60
        while True:
            try:
                command('docker', 'exec', identifier, 'python3', '-c', GATEWAY_PROBE, timeout=10)
                break
            except RuntimeError:
                actual = json.loads(command('docker', 'inspect', identifier))[0]
                if not actual['State']['Running'] or time.monotonic() >= deadline:
                    raise RuntimeError('真实网关初始化或配置读写验收失败')
                time.sleep(0.2)
    finally:
        command('docker', 'stop', '-t', '5', identifier)
        command('docker', 'rm', identifier)


def _sources(public_key: str, history_root: Path | None) -> list[tuple[dict, bytes]]:
    if history_root is not None:
        raw = (history_root / 'index.json').read_bytes()
        signature = (history_root / 'index.sig').read_bytes()
    else:
        for channel in ('updates/v3-migrations', 'updates/v3'):
            try:
                ref = strict_json(fetch_bytes(f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/{channel}', 65536))
            except HTTPError as error:
                if error.code != 404 or channel == 'updates/v3':
                    raise
                continue
            commit = ref['object']['sha']
            raw = fetch_repository_file('index.json', commit, INDEX_LIMIT)
            signature = fetch_repository_file('index.sig', commit, 64)
            break
    index = validate_index(verify_signed(raw, signature, public_key, INDEX_LIMIT))
    sources = []
    for entry in index['releases'][:8]:
        if history_root is not None:
            raw = (history_root / entry['release'] / 'system-release.json').read_bytes()
            signature = (history_root / entry['release'] / 'system-release.sig').read_bytes()
        else:
            raw = fetch_bytes(f'{DOWNLOAD_ROOT}/{entry["release"]}/system-release.json', MANIFEST_LIMIT)
            signature = fetch_bytes(f'{DOWNLOAD_ROOT}/{entry["release"]}/system-release.sig', 64)
        if len(raw) != entry['manifest']['size'] or hashlib.sha256(raw).hexdigest() != entry['manifest']['sha256']:
            raise ValueError('兼容演练旧清单与受信目录不符')
        source = validate_release(verify_signed(raw, signature, public_key))
        if source['release'] != entry['release'] or source['sequence'] != entry['sequence']:
            raise ValueError('兼容演练旧版本身份不符')
        sources.append((source, raw))
    if not sources:
        raise ValueError('兼容演练缺少受支持历史发行')
    return sources


def _verify_source(release: dict, raw: bytes, candidate: str, registries: dict,
        contracts: dict, history_root: Path | None, stopped: Event) -> tuple[dict, float]:
    """在独立双库和容器中验证一个历史来源。

    :param release: 已验签的历史发行。
    :param raw: 历史清单原字节。
    :param candidate: 已核验候选镜像ID。
    :param registries: 冻结迁移登记。
    :param contracts: 当前双库合同。
    :param history_root: 可选本地隔离签名历史。
    :param stopped: 任一来源失败后阻止排队任务开始。
    :return: 原证据条目与本来源耗时秒数。
    """
    if stopped.is_set():
        raise CancelledError()
    started = time.monotonic()
    try:
        source = release['control']
        if history_root is None:
            reference = source['reference'].rsplit(':', 1)[0] + '@' + source['registry_digest']
            command('docker', 'pull', reference, timeout=600)
        else:
            reference = source['reference']
        original = image_identity(reference, source['config_digest'], source['registry_digest'])
        with tempfile.TemporaryDirectory(prefix='v3-database-proof-') as temporary:
            root = Path(temporary)
            bench, gateway = root / 'bench', root / 'gateway'
            bench.mkdir()
            gateway.mkdir()
            python_probe(original, bench, BENCH_PROBE)
            gateway_probe(original, gateway)
            python_probe(original, gateway, GATEWAY_FIXTURE)
            operation = {'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()), 'original': {'release': release}}
            snapshot = root / 'snapshot'
            create_snapshot(root, snapshot, 'database-proof', operation)
            for _ in range(2):
                for name, directory in (('bench', bench), ('gateway', gateway)):
                    if name == 'bench':
                        entrypoint, arguments, environment = 'python3', ['-m', 'database_migrations', 'apply'], []
                    else:
                        entrypoint, arguments = '/app/claude-code-gateway', ['database-migrations', 'apply']
                        environment = ['--env', 'DATABASE_DRIVER=sqlite', '--env', 'DATABASE_DSN=/data/gateway.sqlite']
                    identifier = command('docker', 'create', *_container_arguments(directory), *environment,
                        '--entrypoint', entrypoint, candidate, *arguments, '--operation-id', operation['operation_id'],
                        '--target-version', str(len(registries[name]['steps']))).strip()
                    try:
                        body = command('docker', 'start', '--attach', identifier)
                        process = json.loads(command('docker', 'inspect', identifier))[0]
                        if process['State']['Running'] or process['State']['ExitCode'] != 0:
                            raise ValueError('真实数据库迁移程序执行失败')
                    finally:
                        command('docker', 'stop', '-t', '5', identifier)
                        command('docker', 'rm', identifier)
                    actual = strict_json(body.encode())
                    if actual['contract'] != contracts[name] or actual['current_version'] != len(registries[name]['steps']):
                        raise ValueError('真实迁移结果与源码登记不符')
            python_probe(candidate, bench, BENCH_PROBE)
            gateway_probe(candidate, gateway)
            python_probe(candidate, gateway, GATEWAY_FIXTURE)
            python_probe(original, bench, BENCH_PROBE)
            gateway_probe(original, gateway)
            python_probe(original, gateway, GATEWAY_FIXTURE)
            restore_snapshot(root, snapshot, 'database-proof', operation, lambda: None)
            python_probe(original, bench, BENCH_PROBE)
            gateway_probe(original, gateway)
        proof = {'release': release['release'], 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
            'control_digest': source['config_digest'], 'contracts': {name: release['data_compatibility'][name]['contract'] for name in ('bench', 'gateway')},
            'checks': {'upgrade': True, 'candidate_read_write': True, 'previous_read_write': True, 'idempotent': True}}
        return proof, time.monotonic() - started
    except Exception as error:
        # 在线程取下一个排队任务前发布停止意图，收口由各自原有 finally 负责。
        stopped.set()
        error.add_note('兼容演练来源：' + release['release'])
        raise


def verify(manifest: Path, public_key: str, output: Path, *, history_root: Path | None = None,
        workers: int = 1) -> dict:
    """用有限并发执行完整旧库升级与回退，全部成功后写入证据。

    :param manifest: 实际候选联合镜像清单。
    :param public_key: 已配置的发行公钥。
    :param output: 完整证据输出路径。
    :param history_root: 可选本地合成签名历史，生产CI从固定受信目录读取。
    :param workers: 同时验证的来源数，限定1或2，默认沿用串行。
    :return: 按原来源顺序排列、绑定来源及镜像摘要的完整证据。
    """
    if type(workers) is not int or workers not in (1, 2):
        raise ValueError('兼容演练并发数只能为1或2')
    started = time.monotonic()
    build = strict_json(manifest.read_bytes())
    if history_root is None and (build.get('dirty_worktree') is not False or build.get('verification_only')):
        raise ValueError('正式迁移证据需要干净同批生产镜像')
    control = build['images']['control']
    candidate = image_identity(control['reference'], control['config_digest'], control.get('registry_digest', control.get('digest')))
    registries = migration_registries(REPO)
    contracts = data_contracts(REPO)
    sources = _sources(public_key, history_root)
    proofs = [None] * len(sources)
    stopped = Event()
    failure = None
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_verify_source, release, raw, candidate, registries,
            contracts, history_root, stopped): index for index, (release, raw) in enumerate(sources)}
        try:
            for future in as_completed(futures):
                if future.cancelled():
                    continue
                try:
                    proof, seconds = future.result()
                except CancelledError:
                    continue
                except Exception as error:
                    if failure is None:
                        failure = error
                    stopped.set()
                    for pending in futures:
                        pending.cancel()
                else:
                    proofs[futures[future]] = proof
                    print(json.dumps({'event': 'flower2api-database-source', 'release': proof['release'],
                        'seconds': round(seconds, 3)}, ensure_ascii=False), file=sys.stderr, flush=True)
        finally:
            # 主线程中断或单项失败均等待已启动 worker 完成原有容器与目录收口。
            stopped.set()
            for pending in futures:
                pending.cancel()
    if failure is not None:
        raise failure
    if not proofs or any(proof is None for proof in proofs):
        raise ValueError('兼容演练来源未全部完成')
    result = {'schema_version': 1, 'revision': build['parent_revision'],
        'images': {role: build['images'][role]['config_digest'] for role in ('control', 'account')},
        'target_contracts': contracts, 'sources': proofs}
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output, result)
    print(json.dumps({'event': 'flower2api-database-complete', 'workers': workers, 'sources': len(proofs),
        'seconds': round(time.monotonic() - started, 3)}, ensure_ascii=False), file=sys.stderr, flush=True)
    return result


def main() -> None:
    """运行CI隔离验收，签名密钥仅用于导出公钥。@return None。"""
    parser = argparse.ArgumentParser(description='真实镜像数据库升级与回退演练')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-key')
    parser.add_argument('--history-root', type=Path)
    parser.add_argument('--workers', type=int, choices=(1, 2), default=1, help='同时验证的历史来源数，默认串行')
    args = parser.parse_args()
    public_key = args.public_key
    if not public_key:
        private = os.environ.get('V3_SYSTEM_RELEASE_PRIVATE_KEY', '')
        if not private:
            raise ValueError('兼容验证需要明确的发行公钥')
        result = subprocess.run(['openssl', 'pkey', '-pubout', '-outform', 'DER'], input=private.encode(), capture_output=True, timeout=10)
        if result.returncode or len(result.stdout) < 32:
            raise ValueError('兼容验证的发行公钥无效')
        public_key = result.stdout[-32:].hex()
    evidence = verify(args.manifest, public_key, args.output, history_root=args.history_root, workers=args.workers)
    print(json.dumps({'status': 'passed', 'sources': len(evidence['sources']), 'real_model_requests': 0}))


if __name__ == '__main__':
    main()
