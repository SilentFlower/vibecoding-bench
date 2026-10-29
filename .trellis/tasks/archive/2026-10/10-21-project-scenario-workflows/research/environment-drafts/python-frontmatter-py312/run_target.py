"""只创建并精确清理本次 python-frontmatter 取证容器。"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path

import docker
from docker.errors import NotFound
from docker.types import LogConfig


ROOT = Path(__file__).resolve().parent
RESEARCH = ROOT.parent.parent
DRAFT = RESEARCH / 'content-drafts/python-frontmatter'
REPOSITORY_ROOT = RESEARCH.parents[3]
IMAGE = 'vibebench-v3-account:v3-project-repairs-local-20261021-e'


def save(name: str, document: dict) -> None:
    """保存本次控制端证据。@param name 文件名。@param document 数据。@return None。"""
    (ROOT / 'evidence' / name).write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')


def main() -> None:
    """在固定镜像和限制中真实运行，不影响任何既有账号容器。@return None。"""
    inputs, evidence = ROOT / 'input', ROOT / 'evidence'
    evidence.chmod(0o777)
    for source, target in [(DRAFT / 'verification/native_observe.py', inputs / 'native_observe.py'),
            (DRAFT / 'verification/reference/consult_example.py', inputs / 'consult_example.py'),
            (DRAFT / 'verification/reference/repair.patch', inputs / 'repair.patch'),
            (REPOSITORY_ROOT / '.deploy/github-100-research/resume-app/python-frontmatter/observe.py', inputs / 'legacy_observe.py')]:
        shutil.copyfile(source, target)
        target.chmod(0o644)
    (evidence / 'revision.txt').write_text('d2977d71638cb451bc06f2af3bb48e09e0dbe8c6\n')
    client = docker.from_env()
    image = client.images.get(IMAGE)
    name = 'bench-scenario-research-fm-' + uuid.uuid4().hex[:12]
    labels = {'vibebench.scenario-research': 'fm', 'vibebench.task': '10-21-project-scenario-workflows',
        'vibebench.research-container': name}
    container = None
    started = time.monotonic()
    result = {'name': name, 'image_tag': IMAGE, 'image_id': image.id, 'labels': labels,
        'created_by': str(Path(__file__).relative_to(REPOSITORY_ROOT)), 'status': 'starting'}
    try:
        container = client.containers.create(image.id, name=name,
            entrypoint=['/usr/local/bin/python3', '-B'], command=['/input/run_container.py'],
            user='1000:1000', working_dir='/work', network_mode='none', read_only=True,
            cap_drop=['ALL'], security_opt=['no-new-privileges'], mem_limit='512m', memswap_limit='512m',
            pids_limit=64, tmpfs={'/work': 'rw,nosuid,nodev,size=1073741824,mode=1777',
                '/tmp': 'rw,nosuid,nodev,size=268435456,mode=1777'},
            volumes={str(DRAFT / 'seed'): {'bind': '/source', 'mode': 'ro'},
                str(ROOT): {'bind': '/offline', 'mode': 'ro'},
                str(inputs): {'bind': '/input', 'mode': 'ro'},
                str(evidence): {'bind': '/evidence', 'mode': 'rw'}},
            environment={'HOME': '/tmp/fm-home', 'PYTHONDONTWRITEBYTECODE': '1',
                'PIP_CONFIG_FILE': '/dev/null', 'PIP_NO_INDEX': '1'}, labels=labels,
            log_config=LogConfig(type='json-file', config={'max-size': '2m', 'max-file': '1'}))
        result['container_id'] = container.id
        save('container.json', result)
        container.start()
        completed = container.wait(timeout=600)
        container.reload()
        (evidence / 'container.log').write_bytes(container.logs(stdout=True, stderr=True))
        actual = container.attrs
        result.update(status='exited', exit_code=completed.get('StatusCode'), elapsed_sec=time.monotonic() - started,
            actual_config={'user': actual['Config']['User'], 'image_id': actual['Image'],
                'network_mode': actual['HostConfig']['NetworkMode'], 'read_only': actual['HostConfig']['ReadonlyRootfs'],
                'memory_bytes': actual['HostConfig']['Memory'], 'memory_swap_bytes': actual['HostConfig']['MemorySwap'],
                'pids_limit': actual['HostConfig']['PidsLimit'], 'cap_drop': actual['HostConfig']['CapDrop'],
                'security_opt': actual['HostConfig']['SecurityOpt'],
                'mounts': [{'source': item['Source'], 'destination': item['Destination'], 'rw': item['RW']}
                    for item in actual['Mounts']]})
        save('container.json', result)
        print(json.dumps({key: result[key] for key in ['name', 'image_id', 'exit_code', 'elapsed_sec']}, ensure_ascii=False))
        if result['exit_code'] != 0:
            raise RuntimeError('取证容器未完成全部阶段；保留原始日志，不标 ready')
    finally:
        if container is not None:
            container.reload()
            if container.name != name or container.labels.get('vibebench.research-container') != name:
                raise RuntimeError('容器归属证明不符，拒绝扩大清理范围')
            identifier = container.id
            container.remove(force=True)
            try:
                client.containers.get(identifier)
            except NotFound:
                save('cleanup.json', {'name': name, 'container_id': identifier, 'removed': True,
                    'scope': '只清理本脚本精确创建并核对归属的一个容器'})
            else:
                raise RuntimeError('本次容器移除后仍存在')


if __name__ == '__main__':
    main()
