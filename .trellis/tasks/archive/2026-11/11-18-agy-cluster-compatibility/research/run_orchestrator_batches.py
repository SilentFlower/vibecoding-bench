"""将同一 unittest discover 集合按模块分组，在独立进程中完整复验。"""
import argparse
import json
import sys
import time
import unittest
from collections import defaultdict
from pathlib import Path


def _flatten(suite):
    """展开发现结果并保留测试顺序。@param suite 原测试集合。@return 用例迭代器。"""
    for entry in suite:
        if isinstance(entry, unittest.TestSuite):
            yield from _flatten(entry)
        else:
            yield entry


def main() -> int:
    """运行一个互斥模块批次并记录全部用例身份。@return unittest 退出码。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=int, required=True)
    parser.add_argument('--batches', type=int, default=4)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.batch < args.batches:
        parser.error('批次编号超出范围')
    discovered = list(_flatten(unittest.defaultTestLoader.discover('services/orchestrator')))
    modules = defaultdict(list)
    for case in discovered:
        modules[case.__class__.__module__].append(case)
    groups = [[] for _ in range(args.batches)]
    loads = [0] * args.batches
    # 模块内的夹具和生命周期留在同一进程，集群文件系统场景按较高权重分散。
    weighted = sorted(modules, key=lambda name: (-len(modules[name]) * (2 if name.startswith('test_cluster_') else 1), name))
    for name in weighted:
        group = min(range(args.batches), key=lambda index: (loads[index], index))
        groups[group].extend(modules[name])
        loads[group] += len(modules[name]) * (2 if name.startswith('test_cluster_') else 1)
    selected = groups[args.batch]
    ids = [case.id() for case in selected]
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    report = {'batch': args.batch, 'batches': args.batches, 'discovered': len(discovered),
        'selected': ids, 'run': result.testsRun, 'seconds': round(time.monotonic() - started, 3),
        'passed': result.wasSuccessful(), 'failures': [case.id() for case, _ in result.failures],
        'errors': [case.id() for case, _ in result.errors],
        'skipped': [{'case': case.id(), 'reason': reason} for case, reason in result.skipped]}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
