"""并行运行相互隔离的发行校验，全部收口后汇总退出状态。"""
import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from source_layout import source_path


ROOT = Path(__file__).resolve().parents[2]


def suite_commands(python: str) -> dict[str, list[str]]:
    """列出发行原有的三组完整校验，宿主快照保持 root 权限。

    :param python: 已安装项目依赖的 Python 解释器。
    :return: 三组独立进程命令。
    """
    return {
        'host': ['sudo', python, '-m', 'unittest', 'discover', '-s', 'deploy/flower2api', '-p', 'test_system*.py'],
        'orchestrator': [python, '-m', 'unittest', 'discover', '-s', 'services/orchestrator', '-p', 'test_system_update*.py'],
        'publication': [python, '-m', 'unittest', 'test_publication', 'test_database_definitions',
            'test_database_migrations', 'test_database_compatibility', 'test_source_layout',
            'test_legacy_packages', 'test_scratchpad_update_compatibility'],
    }


def run_checks(commands: dict[str, list[str]]) -> bool:
    """同时执行最多三组独立测试，任何失败均阻止后续构建。

    :param commands: 校验名称及完整 argv。
    :return: 所有校验进程成功时为 True；异常和非零退出均为 False。
    """
    environment = {**os.environ, 'PYTHONPATH': os.pathsep.join(
        str(source_path(ROOT, path)) for path in ('orchestrator', 'deploy/v3'))}

    def execute(name: str, arguments: list[str]) -> bool:
        """执行独立进程并记录耗时。:param name: 校验组。:param arguments: argv。:return: 是否成功。"""
        started = time.monotonic()
        try:
            code = subprocess.run(arguments, cwd=ROOT, env=environment).returncode
        except OSError:
            code = 127
        print(json.dumps({'event': 'flower2api-validation', 'suite': name,
            'seconds': round(time.monotonic() - started, 3), 'exit_code': code}), flush=True)
        return code == 0

    # 测试组各用独立临时目录；一组失败也等待其余进程退出，避免后台遗留或漏报。
    with ThreadPoolExecutor(max_workers=3) as executor:
        pending = [executor.submit(execute, name, arguments) for name, arguments in commands.items()]
        results = [future.result() for future in as_completed(pending)]
    return bool(results) and all(results)


def main() -> None:
    """执行并行发行校验入口。:return: None；失败以非零状态退出。"""
    parser = argparse.ArgumentParser(description='并行运行发行校验')
    parser.add_argument('--python', required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run_checks(suite_commands(args.python)) else 1)


if __name__ == '__main__':
    main()
