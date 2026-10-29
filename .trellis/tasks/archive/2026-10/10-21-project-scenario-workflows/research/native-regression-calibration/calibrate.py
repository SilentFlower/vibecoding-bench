"""创建、轮询及精确清理本任务新 wrapper 校准容器，每次 Docker wait 至多一秒。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import uuid
from pathlib import Path

import docker
from docker.errors import NotFound
from docker.types import LogConfig


ROOT = Path(__file__).resolve().parent
RESEARCH = ROOT.parent
IMAGE_ID = 'sha256:d055c5f0035c8fb3f204ed97d6f774a38afdb3515f5503f7fa028adb6a5e908d'
WRAPPER = RESEARCH / 'content-drafts/shared/native_regression.py'
PROJECTS = ['python-frontmatter', 'pydantic-settings', 'typer']


def save(path: Path, document: object) -> None:
    """保存本次持久登记。@param path 路径。@param document 数据。@return None。"""
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')


def start(project: str) -> None:
    """创建一个精确命名容器并立即返回。@param project 项目。@return None。"""
    client = docker.from_env()
    client.images.get(IMAGE_ID)
    environment = RESEARCH / 'environment-drafts' / (project + '-py312')
    profile = json.loads((environment / 'profile/profile.json').read_text())
    for artifact in profile['artifacts']:
        if hashlib.sha256((environment / artifact['path']).read_bytes()).hexdigest() != artifact['digest']:
            raise ValueError('已有离线制品摘要不匹配')
    token = uuid.uuid4().hex[:10]
    directory = ROOT / project / ('run-' + token)
    inputs, evidence = directory / 'input', directory / 'evidence'
    inputs.mkdir(parents=True)
    evidence.mkdir()
    evidence.chmod(0o777)
    shutil.copyfile(WRAPPER, inputs / 'native_regression.py')
    shutil.copyfile(ROOT / 'calibration_runner.py', inputs / 'calibration_runner.py')
    save(inputs / 'profile.json', profile)
    save(inputs / 'request.json', {'project': project})
    draft = RESEARCH / 'content-drafts' / project
    if project == 'python-frontmatter':
        shutil.copyfile(draft / 'verification/reference/repair.patch', inputs / 'reference.patch')
    elif project == 'pydantic-settings':
        shutil.copyfile(draft / 'verification/reference-union.patch', inputs / 'reference.patch')
    name = 'bench-scenario-research-reg-' + project + '-' + token
    resources = profile['regression']
    labels = {'vibebench.research-container': name, 'vibebench.task': '10-21-project-scenario-workflows',
        'vibebench.scenario-regression': project}
    container = client.containers.create(IMAGE_ID, name=name,
        entrypoint=['/usr/local/bin/python3', '-B'], command=['/input/calibration_runner.py'],
        user='1000:1000', working_dir='/work', network_mode='none', read_only=True,
        cap_drop=['ALL'], security_opt=['no-new-privileges'], mem_limit=f"{resources['memory_mb']}m",
        memswap_limit=f"{resources['memory_mb']}m", pids_limit=resources['pids_limit'],
        tmpfs={'/work': 'rw,exec,nosuid,nodev,size=1610612736,mode=1777',
            '/tmp': 'rw,nosuid,nodev,size=268435456,mode=1777'},
        volumes={str(draft / 'seed'): {'bind': '/source', 'mode': 'ro'},
            str(draft / 'seed/library'): {'bind': '/baseline/library', 'mode': 'ro'},
            str(environment): {'bind': '/offline', 'mode': 'ro'},
            str(inputs): {'bind': '/input', 'mode': 'ro'}, str(evidence): {'bind': '/evidence', 'mode': 'rw'}},
        environment={'HOME': '/tmp/regression-home', 'TMPDIR': '/work/tmp', 'PYTHONDONTWRITEBYTECODE': '1',
            'PIP_CONFIG_FILE': '/dev/null', 'PIP_NO_INDEX': '1'}, labels=labels,
        log_config=LogConfig(type='json-file', config={'max-size': '2m', 'max-file': '1'}))
    record = {'name': name, 'container_id': container.id, 'project': project, 'image_id': IMAGE_ID,
        'wrapper_sha256': hashlib.sha256(WRAPPER.read_bytes()).hexdigest(), 'resources': resources,
        'status': 'created', 'directory': str(directory.relative_to(ROOT))}
    save(directory / 'container.json', record)
    latest_path = ROOT / 'latest.json'
    latest = json.loads(latest_path.read_text()) if latest_path.exists() else {}
    latest[project] = str(directory.relative_to(ROOT))
    save(latest_path, latest)
    container.start()
    record['status'] = 'running'
    save(directory / 'container.json', record)
    print(json.dumps(record, ensure_ascii=False))


def status(project: str) -> None:
    """只查询已登记容器，退出后精确清理。@param project 项目。@return None。"""
    latest = json.loads((ROOT / 'latest.json').read_text())
    directory = ROOT / latest[project]
    path = directory / 'container.json'
    record = json.loads(path.read_text())
    if record.get('removed'):
        print(json.dumps(record, ensure_ascii=False))
        return
    client = docker.from_env()
    container = client.containers.get(record['container_id'])
    if container.name != record['name'] or container.labels.get('vibebench.research-container') != record['name']:
        raise RuntimeError('登记容器归属不符，不扩大查询或清理')
    container.reload()
    if container.status not in ('exited', 'dead'):
        progress = []
        for line in container.logs(tail=2).decode(errors='replace').splitlines():
            try:
                item = json.loads(line)
                progress.append({key: item[key] for key in ('step', 'actual_status', 'elapsed_sec') if key in item})
            except ValueError:
                progress.append({'message': line[-512:]})
        print(json.dumps({'project': project, 'status': container.status, 'progress': progress}, ensure_ascii=False))
        return
    completed = container.wait(timeout=1)
    (directory / 'evidence/container.log').write_bytes(container.logs(stdout=True, stderr=True))
    attrs = container.attrs
    record.update(status='exited', exit_code=completed.get('StatusCode'), oom_killed=attrs['State'].get('OOMKilled'),
        config={'network_mode': attrs['HostConfig']['NetworkMode'], 'read_only_root': attrs['HostConfig']['ReadonlyRootfs'],
            'uid': attrs['Config']['User'], 'memory_bytes': attrs['HostConfig']['Memory'],
            'pids_limit': attrs['HostConfig']['PidsLimit'], 'tmpfs': attrs['HostConfig']['Tmpfs']})
    container.remove(force=True)
    try:
        client.containers.get(record['container_id'])
    except NotFound:
        record['removed'] = True
    else:
        raise RuntimeError('本次容器删除后仍存在')
    save(path, record)
    print(json.dumps(record, ensure_ascii=False))


def main() -> None:
    """按明确项目启动或查询，不启动模型。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'status'])
    parser.add_argument('projects', nargs='+', choices=PROJECTS)
    options = parser.parse_args()
    for project in options.projects:
        (start if options.action == 'start' else status)(project)


if __name__ == '__main__':
    main()
