"""先构建当前候选C扩展，再真实执行双引擎公开CLI回归。"""
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
import json
import os
from pathlib import Path
import unittest


def main() -> None:
    """沿同一可信业务构建入口执行四项真实测试。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    specification = spec_from_file_location('_bench_simplejson_business', Path(__file__).with_name('native_observe.py'))
    observation = module_from_spec(specification)
    specification.loader.exec_module(observation)
    observation.build_source(root)
    import simplejson

    valid = observation.runtime_control()._simplejson_mode(root / 'library', 'c')
    suite = unittest.defaultTestLoader.discover(str(root / 'app'), pattern='test_tool_output.py')
    result = unittest.TextTestRunner(stream=StringIO(), verbosity=2).run(suite)
    failures = [{'test': case.id(), 'message': message[-1000:]}
        for case, message in [*result.failures, *result.errors]]
    print(json.dumps({'candidate_import': valid and Path(simplejson.__file__).resolve() == root / 'library/simplejson/__init__.py',
        'public_tests_passed': result.wasSuccessful() and result.testsRun == 4 and not result.skipped,
        'counts': {'tests': result.testsRun, 'failed': len(result.failures), 'errors': len(result.errors),
            'skipped': len(result.skipped)}, 'failures': failures}, ensure_ascii=False))


if __name__ == '__main__':
    main()
