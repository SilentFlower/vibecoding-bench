"""复现真实原生准备入口的256／512MB差异，记录OOM而不误算业务失败。"""
from hashlib import sha256
from argparse import ArgumentParser
import json
from pathlib import Path
import sys
import time

from docker import from_env
from docker.errors import NotFound


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_verifier import _NATIVE_EXECUTE


def main() -> None:
    """只验证合成原版任务，冻结资源及清理证据。@return None。"""
    work = ROOT / '.deploy/project-catalog-hundred/stage-02'
    project = work / 'drafts/projects/tqdm'
    environment = work / 'drafts/environments/tqdm-py312'
    profile = json.loads((environment / 'profile/profile.json').read_text())
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, required=True)
    options = parser.parse_args()
    execute = _NATIVE_EXECUTE.replace('if prepared.returncode or installed.returncode:',
        'print(json.dumps({"pip_returncode":installed.returncode,"pip_stderr":installed.stderr.decode(errors="replace")[-2000:],'
        '"memory_events":pathlib.Path("/sys/fs/cgroup/memory.events").read_text()}),file=sys.stderr)\n'
        'if prepared.returncode or installed.returncode:')
    client = from_env()
    for memory in (256, 512):
        directory = work / 'resource-probes' / ('attempt-' + str(options.attempt).zfill(3)) / ('tqdm-business-' + str(memory))
        directory.mkdir(parents=True, exist_ok=False)
        (directory / 'verification').mkdir()
        (directory / 'native.json').write_text(json.dumps({'script': 'verification/native_observe.py',
            'args': ['TQ-U01'], 'python_paths': ['library', 'app'], 'requirements': profile['requirements']}))
        (directory / 'answer.txt').write_text('')
        container, started = None, time.monotonic()
        report = {'memory_mb': memory, 'pids_limit': 64, 'image': 'ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1',
            'network': 'none', 'user': '1000:1000', 'read_only': True, 'account_credentials_mounted': False,
            'native_execute_sha256': sha256(_NATIVE_EXECUTE.encode()).hexdigest(),
            'probe_execute_sha256': sha256(execute.encode()).hexdigest(), 'real_model_calls': 0}
        try:
            container = client.containers.create(report['image'], entrypoint=['python3','-I','-B','-c'], command=[execute],
                user='1000:1000', working_dir='/work', network_mode='none', read_only=True,
                cap_drop=['ALL'], security_opt=['no-new-privileges'],
                mem_limit=str(memory)+'m', memswap_limit=str(memory)+'m', pids_limit=64,
                tmpfs={'/work':'rw,exec,nosuid,nodev,size=1073741824,mode=1777','/tmp':'rw,nosuid,nodev,size=67108864,mode=1777'},
                volumes={str(project/'seed'):{'bind':'/source','mode':'ro'}, str(directory):{'bind':'/request-data','mode':'ro'},
                    str(project/'verification'):{'bind':'/request-data/verification','mode':'ro'},
                    str(environment):{'bind':'/offline','mode':'ro'}},
                environment={'HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1','PIP_CONFIG_FILE':'/dev/null'},
                labels={'vibebench.verification':'tqdm-resource-probe'})
            container.start()
            status = container.wait(timeout=90)
            container.reload()
            output, errors = container.logs(stdout=True,stderr=False), container.logs(stdout=False,stderr=True)
            (directory/'stdout.log').write_bytes(output)
            (directory/'stderr.log').write_bytes(errors)
            ready = output.startswith(b'VIBEBENCH_NATIVE_READY_V1\n')
            actual = json.loads(output.split(b'\n',1)[1]) if ready else None
            report.update(returncode=status['StatusCode'], oom_killed=container.attrs['State']['OOMKilled'],
                bootstrap_ready=ready, actual=actual, status='passed' if status['StatusCode']==0 and ready and all(actual.values()) else 'failed')
        finally:
            if container is not None:
                identity=container.id
                container.remove(force=True)
                try:
                    client.containers.get(identity)
                except NotFound:
                    report['container_removed']=True
            report['elapsed_sec']=time.monotonic()-started
            (directory/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(report,ensure_ascii=False),flush=True)
    client.close()


if __name__ == '__main__':
    main()
