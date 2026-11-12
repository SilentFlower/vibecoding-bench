"""对实际修改后的作业监督器执行隔离 Docker 验证。"""
import ast
import argparse
import json
import tempfile
import time
import uuid
from pathlib import Path

import docker


def main() -> None:
    """创建无账号数据的临时 CLI 容器并验证兄弟作业隔离。@return None。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--image',required=True)
    parser.add_argument('--report',type=Path,required=True)
    arguments = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix='verify-cli-jobs-')
    review = Path(temporary.name)
    control = Path(__file__).resolve().parents[2]/'images/account/cli-control.py'
    ast.parse(control.read_text())
    fixture = review / 'job-writer.py'
    fixture.write_text('''import os,sys,time
from pathlib import Path
label=sys.argv[1]
if os.fork()==0:
 os.setsid()
 if os.fork(): os._exit(0)
 with open('/work/'+label+'.daemon','ab',buffering=0) as stream:
  while True:
   stream.write(b'x');time.sleep(0.02)
with open('/work/'+label+'.main','ab',buffering=0) as stream:
 while True:
  stream.write(b'x');time.sleep(0.02)
''')
    fixture.chmod(0o644)
    client = docker.from_env()
    container = client.containers.run(arguments.image,
        name='bench-cli-job-control-'+uuid.uuid4().hex[:12],
        entrypoint=['python3', '-I', '/usr/local/bin/v3-cli-control'], command=['idle'],
        detach=True, network_mode='none', user='1000:1000', read_only=True, cap_drop=['ALL'],
        security_opt=['no-new-privileges'], mem_limit='128m', pids_limit=64,
        nano_cpus=500000000, tmpfs={'/work': 'rw,nosuid,nodev,size=8m,mode=1777'},
        volumes={str(control): {'bind': '/review/cli-control.py', 'mode': 'ro'},
            str(fixture): {'bind': '/review/job-writer.py', 'mode': 'ro'}},
        labels={'vibebench.verification': 'cli-job-control'})
    try:
        proofs = {}
        for label in ('A', 'B'):
            source = 'test-' + label
            command = ['python3', '-I', '/review/cli-control.py', 'supervise', '--source', source,
                '--proof', '/work/'+label+'.proof', '--ready', '/work/'+label+'.ready',
                '--result', '/work/'+label+'.result', '--', 'python3', '-I', '/review/job-writer.py', label]
            execution = client.api.exec_create(container.id, command, workdir='/work')
            client.api.exec_start(execution['Id'], detach=True)
            deadline = time.monotonic() + 10
            while True:
                answer = container.exec_run(['cat', '/work/'+label+'.proof'])
                if answer.exit_code == 0:
                    proofs[label] = json.loads(answer.output)
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('监督器证明未就绪：'+str(client.api.exec_inspect(execution['Id'])))
                time.sleep(0.05)
            proof = proofs[label]
            assert proof['parent'] == 0, proof
            result = container.exec_run(['python3', '-c',
                'import sys,pathlib;pathlib.Path(sys.argv[1]).write_text(sys.argv[2])',
                '/work/'+label+'.ready', json.dumps(proof)])
            assert result.exit_code == 0

        def operate(label: str, operation: str, wrong: bool = False):
            """调用实际内核控制入口。@param label 作业。@param operation 操作。@param wrong 旧证明。@return 控制结果。"""
            proof = proofs[label]
            result = container.exec_run(['python3', '-I', '/review/cli-control.py', operation,
                '--source', proof['source'], '--pid', str(proof['pid']),
                '--started', str(proof['started'] + int(wrong))])
            if wrong:
                return result.exit_code != 0
            if result.exit_code:
                raise RuntimeError(result.output.decode())
            return json.loads(result.output)

        def sizes() -> dict:
            """读取合成写入量。@return 两作业普通／脱离进程组的写入量。"""
            result = container.exec_run(['python3', '-c',
                "import json,pathlib;print(json.dumps({p.name:p.stat().st_size for p in pathlib.Path('/work').glob('*') if p.suffix in ('.main','.daemon')}))"])
            assert result.exit_code == 0
            return json.loads(result.output)

        deadline = time.monotonic() + 8
        while len(sizes()) < 4:
            if time.monotonic() > deadline:
                raise RuntimeError('合成项目写入未开始')
            time.sleep(0.05)
        refused = operate('A', 'stop-job', True)
        frozen = operate('A', 'freeze')
        before = sizes()
        time.sleep(0.3)
        after = sizes()
        stable = all(after[key] == before[key] for key in ('A.main', 'A.daemon'))
        sibling = all(after[key] > before[key] for key in ('B.main', 'B.daemon'))
        operate('A', 'resume')
        time.sleep(0.2)
        resumed = sizes()['A.main'] > after['A.main']
        stopped = operate('A', 'stop-job')
        before = sizes()
        time.sleep(0.2)
        after = sizes()
        isolated = all(after[key] == before[key] for key in ('A.main', 'A.daemon')) and all(
            after[key] > before[key] for key in ('B.main', 'B.daemon'))
        result = {'stale_pid_proof_refused': refused, 'paused_writers_stable': stable,
            'sibling_continues': sibling, 'resumed': resumed,
            'stopped_without_sibling_damage': isolated,
            'frozen_processes': len(frozen['processes']), 'stop_result': stopped}
        assert all((refused, stable, sibling, resumed, isolated)), result
        operate('B', 'stop-job')
        arguments.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        container.remove(force=True)
        temporary.cleanup()


if __name__ == '__main__':
    main()
