"""只在本机 Unix Docker socket 上新建临时 PostgreSQL，验证后清理自建容器。"""
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    """验证新调度的 PG 原子合同，不使用外部或现有业务数据库。"""
    context = json.loads(subprocess.run(['docker', 'context', 'inspect'], capture_output=True, text=True, check=True).stdout)[0]
    endpoint = context.get('Endpoints', {}).get('docker', {}).get('Host', '')
    if not endpoint.startswith('unix://'):
        raise RuntimeError('只允许本机 Unix socket 的隔离验证')
    docker = ['docker', '--host', endpoint]
    name = 'v3-scheduling-pg-' + uuid.uuid4().hex[:10]
    created = False
    try:
        subprocess.run(docker + ['run', '--pull=never', '--rm', '-d', '--name', name, '--label', 'codex.task=v3-stable-session-smart-scheduling', '--cpus', '1', '--memory', '256m', '--pids-limit', '128', '-e', 'POSTGRES_PASSWORD=synthetic-scheduling-test', '-e', 'POSTGRES_DB=scheduling_test', '-p', '127.0.0.1::5432', 'postgres:16-alpine'], check=True, capture_output=True, text=True)
        created = True
        for _ in range(80):
            if subprocess.run(docker + ['exec', name, 'pg_isready', '-U', 'postgres'], capture_output=True).returncode == 0:
                break
            time.sleep(.25)
        else:
            raise RuntimeError('临时 PostgreSQL 未就绪')
        port = subprocess.run(docker + ['port', name, '5432/tcp'], capture_output=True, text=True, check=True).stdout.strip().rsplit(':', 1)[1]
        env = os.environ.copy()
        env['CC2API_SCHEDULING_TEST_POSTGRES_DSN'] = f'postgres://postgres:synthetic-scheduling-test@127.0.0.1:{port}/scheduling_test'
        log = HERE / 'postgres-check.log'
        with log.open('w') as output:
            result = subprocess.run(['cargo', 'test', '--locked', '--test', 'v3_scheduling_test', 'postgres_concurrent_binding_and_budget_rollback', '--', '--ignored', '--exact'], cwd=HERE.parents[3] / 'cc2api', env=env, stdout=output, stderr=subprocess.STDOUT)
        content = log.read_text()
        print('\n'.join(content.splitlines()[-32:]))
        assert result.returncode == 0 and '1 passed' in content, 'PostgreSQL 合同未通过'
        (HERE / 'postgres-check-result.json').write_text(json.dumps({'passed': True, 'database': '独立本机临时 PostgreSQL', 'test': 'postgres_concurrent_binding_and_budget_rollback'}, ensure_ascii=False, indent=2) + '\n')
    finally:
        if created:
            subprocess.run(docker + ['rm', '-f', name], capture_output=True)
            print('已清理本任务新建的 PostgreSQL 容器。')


if __name__ == '__main__':
    main()
