"""对本阶段已实现范围执行既有回归，保存实际命令、日志和代码身份。"""
from datetime import datetime, timezone
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time


def main() -> None:
    """不把已实现范围的检查当作固定三十仓全部验收。@return None。"""
    root = Path.cwd()
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--record', default='focused-checks-current.json')
    options = parser.parse_args()
    record_path = Path(__file__).with_name(options.record)
    if (options.attempt < 1 or Path(options.record).name != options.record
            or record_path.suffix != '.json' or record_path.exists()):
        raise ValueError('检查原件必须使用新的本阶段JSON路径及正整数轮次')
    output = root / '.deploy/project-catalog-hundred/stage-03' / ('focused-checks-' + str(options.attempt).zfill(3))
    output.mkdir(parents=True, exist_ok=False)
    checks = [('.', ['.deploy/project-iteration-repairs/venv/bin/python', '-m', 'unittest', 'discover',
            '-s', 'orchestrator', '-p', 'test_project_*.py', '-q']),
        ('deploy/v3', ['python3', '-m', 'unittest', 'test_manage', '-q'])]
    results = []
    for index, (working_directory, arguments) in enumerate(checks, 1):
        started = time.monotonic()
        completed = subprocess.run(arguments, cwd=root/working_directory, capture_output=True, text=True, timeout=900)
        stdout, stderr = output / (str(index) + '-stdout.log'), output / (str(index) + '-stderr.log')
        stdout.write_text(completed.stdout);stderr.write_text(completed.stderr)
        report = {'cwd': working_directory, 'argv': arguments, 'exit_code': completed.returncode,
            'status': 'passed' if completed.returncode == 0 else 'failed', 'elapsed_sec': round(time.monotonic()-started, 6),
            'stdout': str(stdout.relative_to(root)), 'stderr': str(stderr.relative_to(root)),
            'stdout_sha256': sha256(stdout.read_bytes()).hexdigest(), 'stderr_sha256': sha256(stderr.read_bytes()).hexdigest()}
        results.append(report)
        print(json.dumps({key:report[key] for key in ['argv','status','elapsed_sec']},ensure_ascii=False),flush=True)
    paths = ['orchestrator/project_native_regression.py', 'orchestrator/test_project_native_regression.py',
        'deploy/v3/manage.py', 'deploy/v3/test_manage.py', 'images/v3/Dockerfile.dockerignore']
    record = {'recorded_at': datetime.now(timezone.utc).isoformat(),
        'scope': '已实现范围的既有回归；不是R1/R8全部三十仓验收或Check-All通过声明', 'checks': results,
        'source_sha256': {name:sha256((root/name).read_bytes()).hexdigest() for name in paths}}
    (output / 'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    raise SystemExit(0 if all(row['exit_code'] == 0 for row in results) else 1)


if __name__ == '__main__':
    main()
