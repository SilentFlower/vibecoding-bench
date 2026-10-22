"""逐项目下载精确wheel，避免把不同项目的测试版本合并求解。"""
from argparse import ArgumentParser
import json
from pathlib import Path
import subprocess
import sys


def main() -> None:
    """保留每仓准备日志，失败不改版本或中止其他独立下载。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--projects', nargs='+', required=True)
    parser.add_argument('--attempt', type=int, required=True)
    options = parser.parse_args()
    research = Path(__file__).resolve().parent
    work = Path('.deploy/project-catalog-hundred/stage-03')
    failures = []
    for key in options.projects:
        requirements = research / (key + '-requirements.txt')
        if not requirements.is_file() or requirements.parent != research:
            raise ValueError('缺少精确项目清单')
        evidence = work / 'dependency-preparation' / key / ('download-' + str(options.attempt).zfill(3))
        evidence.mkdir(parents=True, exist_ok=False)
        command = [sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--no-deps',
            '--find-links', str(work / 'wheels'),
            '--dest', str(work / 'wheels'), '-r', str(requirements)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=240)
        (evidence / 'stdout.log').write_text(completed.stdout)
        (evidence / 'stderr.log').write_text(completed.stderr)
        result = {'project': key, 'command': command, 'returncode': completed.returncode,
            'status': 'passed' if completed.returncode == 0 else 'failed'}
        (evidence / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if completed.returncode:
            failures.append(key)
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
