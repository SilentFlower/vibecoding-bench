"""执行原生完整集合，同时保存实际节点和严格 doctest 类型。"""
import json
import sys
from pathlib import Path

import frontmatter
import pytest


class CollectionEvidence:
    """封存 pytest 真实收集与逐项结果。

    @param output 证据 JSON 目标。
    """

    def __init__(self, output: Path) -> None:
        """初始化证据。@param output 目标。@return None。"""
        self.output = output
        self.collection = []
        self.reports = []

    def pytest_collection_finish(self, session) -> None:
        """读取 pytest 已收集节点。@param session 实际会话。@return None。"""
        self.collection = [{'nodeid': item.nodeid, 'item_type': type(item).__name__} for item in session.items]

    def pytest_runtest_logreport(self, report) -> None:
        """记录 setup／call／teardown 结果。@param report pytest 报告。@return None。"""
        self.reports.append({'nodeid': report.nodeid, 'when': report.when, 'outcome': report.outcome})

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        """保存实际收集与退出状态。@param session 会话。@param exitstatus 原生状态。@return None。"""
        self.output.write_text(json.dumps({'exit_code': int(exitstatus), 'cwd': str(Path.cwd()),
            'module': frontmatter.__file__, 'collection': self.collection, 'reports': self.reports},
            ensure_ascii=False, indent=2) + '\n')


def main() -> None:
    """在新的进程运行严格 doctest 全套。@return None。"""
    name = sys.argv[1]
    root = Path('/evidence')
    plugin = CollectionEvidence(root / (name + '-collection.json'))
    arguments = ['.', '--doctest-modules', '--doctest-glob', 'README.md', '-q', '-ra',
        '-p', 'no:cacheprovider', '--junitxml=' + str(root / (name + '-tests.xml'))]
    raise SystemExit(pytest.main(arguments, plugins=[plugin]))


if __name__ == '__main__':
    main()
