"""实际Docker中的临时文件转存、内存盘减量和真实CLI续跑验证。"""
import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import docker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/orchestrator'))
from cli_scratchpad import SCRATCHPAD_STORE, SCRATCHPAD_TARGET, prepare_scratchpad_mount, preserve_cli_scratchpad, restore_cli_scratchpad
from storage_maintenance import tree_inventory


_WRITE = """import os,pathlib,sys
root=pathlib.Path('/tmp/claude-1000');root.mkdir(mode=0o700,exist_ok=True)
for session in ('session-a','session-b','session-c'):
 p=root/sys.argv[1]/session/'scratchpad';p.mkdir(parents=True)
 (p/'marker').write_text(sys.argv[1]+'_'+session+'_first')
 with (p/'payload').open('wb') as f:
  for _ in range(8):f.write(b'x'*1024*1024)
 (p/'payload').chmod(0o640);os.utime(p/'payload',(1234567890,1234567890))
 (p/'link').symlink_to('marker')
"""
_MEMORY = """import json,pathlib
rows=dict(line.split() for line in pathlib.Path('/sys/fs/cgroup/memory.stat').read_text().splitlines())
print(json.dumps({key:int(rows[key]) for key in ('anon','file','shmem')}))
"""


def verify(image: str, cli: Path, output: Path, performance_pairs: int = 0) -> dict:
    """在私有数据根中运行实际挂载与合成会话验证。

    :param image: 已存在的本地账号镜像。
    :param cli: 已核验的官方Linux CLI二进制。
    :param output: 全新报告文件。
    :param performance_pairs: sender性能对照配对次数，0仅验证功能。
    :return: 验证事实及测量口径。
    """
    client = docker.from_env()
    root = Path(tempfile.mkdtemp(prefix='scratchpad-storage-verify-'))
    deployment = 'scratchpad-' + uuid.uuid4().hex[:12]
    containers, volume_names = [], set()
    created_image = None
    report = {'root': str(root), 'checks': [], 'image': image}

    def execute(container, script, arguments=()):
        result = container.exec_run(['python3', '-I', '-c', script, *arguments])
        if result.exit_code:
            raise ValueError('隔离容器验证失败：' + result.output.decode(errors='replace')[-3000:])
        return result.output.decode().strip()

    def runtime(data, node=None):
        data.mkdir(parents=True, exist_ok=True, mode=0o700)
        return SimpleNamespace(client=client, data=data, host_data=data, deployment=deployment,
            image=created_image.id, node_key=node, _root=lambda row: data / 'environments' / row['environment_id'])

    def start(current, row, account, mounted, image_override=None):
        environment = current._root(row)
        environment.mkdir(parents=True, exist_ok=True, mode=0o700)
        home = environment / 'home'
        home.mkdir(mode=0o700, exist_ok=True)
        os.chown(home, 1000, 1000)
        control = environment / 'runtime/cli'
        control.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chown(control, 0, 1000)
        scratchpad_mount = prepare_scratchpad_mount(current, row) if mounted else None
        mounts = [scratchpad_mount] if scratchpad_mount is not None else []
        volume_names.update(mount['Source'] for mount in mounts)
        container = client.containers.run(image_override or created_image.id, name='bench-' + deployment + '-' + uuid.uuid4().hex[:8],
            entrypoint=['python3', '-I', '-c', 'import time;time.sleep(900)'], detach=True,
            user='1000:1000', network_mode='none', cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
            read_only=True, mem_limit='768m', memswap_limit='768m', nano_cpus=1_000_000_000,
            tmpfs={'/tmp': 'rw,noexec,nosuid,nodev,size=128m,mode=1777'}, mounts=mounts,
            volumes={str(home): {'bind': '/home/node', 'mode': 'rw'},
                str(control): {'bind': '/run/v3', 'mode': 'rw'},
                str(cli): {'bind': '/fixture-claude', 'mode': 'ro'}},
            environment={'HOME': '/home/node'}, labels={'vibebench.product': 'v3', 'vibebench.deployment': deployment})
        containers.append(container)
        restore_cli_scratchpad(current, row, container, fresh=True)
        return container

    def cli_probe(container, session, path, turn, mode):
        script = Path(__file__).with_name('scratchpad_cli_fixture.py').read_text()
        value = json.loads(execute(container, script, ('/fixture-claude', session, path, turn, mode)))
        if value['session_id'] != session or value['is_error'] or value['requests'] < 2:
            raise ValueError('真实CLI会话身份或工具执行不符')
        return value

    try:
        base = client.containers.create(image, name='bench-' + deployment + '-image')
        containers.append(base)
        created_image = base.commit(repository='bench-' + deployment, tag='fixture',
            conf={'Labels': {**(client.images.get(image).attrs['Config'].get('Labels') or {}), 'vibebench.cli-scratchpad-protocol': '1'}})
        local = runtime(root / 'local')
        row = {'environment_id': 'a' * 32, 'generation': 1}
        first = start(local, row, 'account-a', False)
        execute(first, _WRITE, ('account-a',))
        before = json.loads(execute(first, _MEMORY))
        session = str(uuid.uuid4())
        path = SCRATCHPAD_TARGET + '/account-a/session-a/scratchpad/marker'
        initial = cli_probe(first, session, path, 'first', 'new')
        if 'account-a_session-a_first' not in initial['result']:
            raise ValueError('真实CLI首次读取内容不符')
        preserve_cli_scratchpad(local, row, first)
        changed_path = SCRATCHPAD_TARGET + '/account-a/session-a/scratchpad/after-snapshot'
        execute(first, "from pathlib import Path;Path(__import__('sys').argv[1]).write_text('latest-content')", (changed_path,))
        restore_cli_scratchpad(local, row, first)
        if execute(first, "from pathlib import Path;print(Path(__import__('sys').argv[1]).read_text())", (changed_path,)) != 'latest-content':
            raise ValueError('原启动中的最新文件未保全')
        if (local._root(row) / SCRATCHPAD_STORE / 'restore.json').exists():
            raise ValueError('原启动被误标记为待恢复')
        preserve_cli_scratchpad(local, row, first)
        first.stop(timeout=2)
        first.start()
        snapshot = (local._root(row) / SCRATCHPAD_STORE / 'legacy.json').read_bytes()
        try:
            preserve_cli_scratchpad(local, row, first)
        except ValueError as error:
            if '尚未恢复到本次启动' not in str(error):
                raise
        else:
            raise ValueError('重启后的空内存盘绕过了旧快照保护')
        if (local._root(row) / SCRATCHPAD_STORE / 'legacy.json').read_bytes() != snapshot:
            raise ValueError('重启后的转存覆盖了原快照')
        restore_cli_scratchpad(local, row, first)
        if execute(first, "from pathlib import Path;print(Path(__import__('sys').argv[1]).read_text())", (changed_path,)) != 'latest-content':
            raise ValueError('重启后未恢复最新转存文件')
        restored = cli_probe(first, session, path, 'legacy-restore', 'resume')
        if 'account-a_session-a_first' not in restored['result']:
            raise ValueError('旧CLI原实例续跑不符')
        preserve_cli_scratchpad(local, row, first)
        first.remove(force=True)
        converted = start(local, row, 'account-a', True)
        after = json.loads(execute(converted, _MEMORY))
        if before['shmem'] - after['shmem'] < 23 * 1024 * 1024:
            raise ValueError('内存盘减量未达到样本要求')
        execute(converted, "from pathlib import Path;Path(__import__('sys').argv[1]).write_text('account-a_session-a_second')", (path,))
        resumed = cli_probe(converted, session, path, 'disk-resume', 'resume')
        if 'account-a_session-a_second' not in resumed['result']:
            raise ValueError('迁盘后真实CLI未读取当前文件')
        other = {'environment_id': 'b' * 32, 'generation': 1}
        second = start(local, other, 'account-b', True)
        execute(second, _WRITE, ('account-b',))
        other_session = str(uuid.uuid4())
        second_result = cli_probe(second, other_session, SCRATCHPAD_TARGET + '/account-b/session-a/scratchpad/marker', 'other', 'new')
        if 'account-b_session-a_first' not in second_result['result'] or 'account-a_session-a_second' in second_result['result']:
            raise ValueError('跨账号内容归属不符')
        report.update(before=before, after=after, tmpfs_reduction_bytes=before['shmem'] - after['shmem'],
            cli_sessions=[session, other_session], checks=['实际安全挂载', '三会话文件转存', '同次启动新增文件及转存重试', '重启后先恢复再允许转存', '旧CLI停止后恢复',
                '真实CLI原会话迁盘续跑', '两账号内容归属', 'tmpfs刚性占用减量'])
        expected = tree_inventory(local._root(row) / SCRATCHPAD_STORE / 'data')
        converted.remove(force=True)
        for name in list(volume_names):
            volume = client.volumes.get(name)
            if volume.attrs['Labels']['vibebench.environment'] == row['environment_id']:
                volume.remove()
        recreated = start(local, row, 'account-a', True)
        if tree_inventory(local._root(row) / SCRATCHPAD_STORE / 'data') != expected:
            raise ValueError('重新建立卷后的文件内容不符')
        reread = cli_probe(recreated, session, path, 'recreated-volume', 'resume')
        if 'account-a_session-a_second' not in reread['result']:
            raise ValueError('重新建立卷后的会话续跑不符')
        report['checks'].append('删除重建容器及卷后的原会话续跑')
        original_image = local.image
        if (client.images.get(image).attrs['Config'].get('Labels') or {}).get('vibebench.cli-scratchpad-protocol') == '1':
            raise ValueError('回退验收需要尚未声明迁盘能力的原账号镜像')
        recreated.remove(force=True)
        try:
            # 兼容管理端根据已登记的磁盘资料挂载原路径，旧账号镜像继续沿原UID运行。
            local.image = image
            recreated = start(local, row, 'account-a', True, image_override=image)
            rollback = cli_probe(recreated, session, path, 'compatible-rollback', 'resume')
            if 'account-a_session-a_second' not in rollback['result']:
                raise ValueError('兼容版本配原账号镜像的会话恢复不符')
            report['rollback_image'] = client.images.get(image).id
            report['checks'].append('兼容管理端配原账号镜像回退续跑')
        finally:
            local.image = original_image
        fallback_row = {'environment_id': 'd' * 32, 'generation': 1}
        legacy = start(local, fallback_row, 'account-d', False)
        execute(legacy, _WRITE, ('account-d',))
        fallback_session = str(uuid.uuid4())
        fallback_path = SCRATCHPAD_TARGET + '/account-d/session-a/scratchpad/marker'
        cli_probe(legacy, fallback_session, fallback_path, 'fallback-first', 'new')
        preserve_cli_scratchpad(local, fallback_row, legacy)
        legacy.remove(force=True)
        with patch('cli_scratchpad._disk_supported', return_value=False):
            fallback = start(local, fallback_row, 'account-d', True)
        continued = cli_probe(fallback, fallback_session, fallback_path, 'fallback-resume', 'resume')
        if 'account-d_session-a_first' not in continued['result']:
            raise ValueError('能力不足时原会话续跑失败')
        if any(item['Destination'] == SCRATCHPAD_TARGET for item in fallback.attrs.get('Mounts', [])):
            raise ValueError('能力不足时未沿用原tmpfs')
        preserve_cli_scratchpad(local, fallback_row, fallback)
        report['checks'].append('能力不足沿用tmpfs并在新CLI续跑原会话')
        if performance_pairs:
            from scratchpad_sender_benchmark import measure_sender_performance
            baseline_row = {'environment_id': 'c' * 32, 'generation': 1}
            baseline = start(local, baseline_row, 'account-c', False)
            controls = {'tmpfs': local._root(baseline_row) / 'runtime/cli',
                'disk': local._root(row) / 'runtime/cli'}
            report['sender_performance'] = measure_sender_performance(client, created_image.id,
                root, baseline, recreated, controls, pairs=performance_pairs)
            report['checks'].append('真实原生sender与同宿主CLI写入的交错性能测量')
        report['passed'] = True
    finally:
        cleanup = []
        for container in reversed(containers):
            try:
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
            except Exception as error:
                cleanup.append(type(error).__name__)
        for name in volume_names:
            try:
                client.volumes.get(name).remove()
            except docker.errors.NotFound:
                pass
            except Exception as error:
                cleanup.append(type(error).__name__)
        if created_image is not None:
            client.images.remove(created_image.id)
        report['cleanup_errors'] = cleanup
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x') as destination:
            json.dump(report, destination, ensure_ascii=False, indent=2)
            destination.write('\n')
    return report


def main() -> None:
    """读取本地镜像、官方CLI和全新报告位置。:return: None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--cli', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--performance-pairs', type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(verify(args.image, args.cli.resolve(strict=True), args.output, args.performance_pairs), ensure_ascii=False))


if __name__ == '__main__':
    main()
