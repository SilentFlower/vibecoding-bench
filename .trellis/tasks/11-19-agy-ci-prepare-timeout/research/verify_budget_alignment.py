"""在独立源码夹具中延迟换代或shutdown退役，对照探针与生命周期预算。"""
import argparse
import io
import json
import subprocess
import tempfile
import time
from contextlib import redirect_stderr
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

from docker.models.containers import ContainerCollection
import verify_agy_runtime as current


def main() -> None:
    """执行零模型慢退役对照。@return 无；对照前提或结论不符保持非零状态。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shutdown', action='store_true', help='对照物理退出观察窗口')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='agy-budget-fixture-') as temporary:
        package = Path(temporary)
        container = subprocess.check_output(['docker', 'create', '--entrypoint', '/bin/true',
            '--label', 'vibebench.test-task=agy-ci-prepare-timeout', args.image], text=True).strip()
        try:
            subprocess.run(['docker', 'cp', container + ':/opt/v3/python/agy_runtime', str(package / 'agy_runtime')], check=True)
            subprocess.run(['docker', 'cp', container + ':/usr/local/bin/runtime_files.py', str(package / 'runtime_files.py')], check=True)
        finally:
            subprocess.run(['docker', 'rm', container], check=True, stdout=subprocess.DEVNULL)
        path = package / 'agy_runtime/kernel.py'
        source = path.read_text()
        marker = '        self.ready=False\n'
        assert source.count(marker) == 1
        condition = "reason=='shutdown' and self.owner.cfg['credential_generation']==2" if args.shutdown else "self.owner.cfg['credential_generation']==1"
        source = source.replace(marker, "        fixture_begin=time.monotonic()\n        if " + condition + ":time.sleep(45)\n" + marker)
        marker = '        return evidence\n'
        assert source.count(marker) == 1
        source = source.replace(marker, "        if " + condition + ":Path('/state/fixture-retire-seconds.json').write_text(str(time.monotonic()-fixture_begin))\n" + marker)
        path.write_text(source)
        # 固定原失败版本，后续修复完成后仍可重跑同一个预算对照。
        revision = 'c462479a9800f71b1badd14b1f3832482608a09b' if args.shutdown else '1435bb2a1c263430d5854f93fff598d3c0e95532'
        source = subprocess.check_output(['git', 'show', revision + ':deploy/flower2api/verify_agy_runtime.py'], text=True)
        baseline_path = package / 'baseline_probe.py'
        baseline_path.write_text(source)
        spec = spec_from_file_location('agy_budget_baseline_probe', baseline_path)
        baseline = module_from_spec(spec)
        spec.loader.exec_module(baseline)
        if args.shutdown:
            assert source.count('time.monotonic()+15') == 1 and current.SHUTDOWN_SECONDS == 90
        else:
            assert source.count('time.time()+45') == source.count('time.monotonic()+50') == 1
        assert current.PREPARE_SECONDS == 120
        original = ContainerCollection.run
        results = {}
        baseline_name, aligned_name = ('baseline_15s', 'aligned_90s') if args.shutdown else ('baseline_45s', 'aligned_120s')
        for name, module in [(baseline_name, baseline), (aligned_name, current)]:
            facts = {}

            def run(manager, *items, **options):
                """保留合成退役时长并沿原删除路径收口。@param manager 容器集合。@param items 原参数。@param options 原选项。@return 本次隔离容器。"""
                state = next(Path(key) for key, value in options['volumes'].items() if value['bind'] == '/state')
                value = original(manager, *items, **options)
                remove = value.remove

                def cleanup(*items, **options):
                    """读取固定标量后回收容器。@param items 原参数。@param options 原选项。@return 原删除结果。"""
                    path = state / 'fixture-retire-seconds.json'
                    facts['retire_seconds'] = float(path.read_text()) if path.exists() else None
                    return remove(*items, **options)

                value.remove = cleanup
                return value

            started = time.monotonic()
            error = io.StringIO()
            with patch.object(module, 'source_path', return_value=package), \
                    patch.object(ContainerCollection, 'run', new=run), redirect_stderr(error):
                try:
                    value = module.native_probe(args.image, image_package=False)
                    facts.update(passed=value['passed'], credential_generations=value['credential_generations'],
                        image_decode_calls=value['image_decode_calls'], terminated=value['terminated'], model_submissions=value['model_submissions'])
                    facts['prepare_seconds'] = value.get('prepare_seconds')
                    if args.shutdown:
                        facts['shutdown_seconds'] = value['shutdown_seconds']
                        facts['shutdown_deadline_seconds'] = value['shutdown_deadline_seconds']
                except ValueError as failure:
                    facts.update(passed=False, error=str(failure))
                    facts['evidence'] = json.loads(error.getvalue().splitlines()[0])
            facts['seconds'] = round(time.monotonic() - started, 3)
            results[name] = facts
            print(json.dumps({'mode': name, **facts}, ensure_ascii=False), flush=True)
        assert results[baseline_name]['passed'] is False
        assert results[baseline_name]['evidence']['credential_generation'] == 2
        assert results[aligned_name]['passed'] is True
        assert 45 <= results[aligned_name]['retire_seconds'] <= 60
        assert results[aligned_name]['model_submissions'] == 0
        if args.shutdown:
            assert 45 <= results[aligned_name]['shutdown_seconds'] <= 90
            assert results[baseline_name]['evidence']['phase'] == 'status'
            recorded = json.loads(Path(__file__).with_name('root-validation.json').read_text())
            assert results[baseline_name]['evidence'] == recorded['import_fix_validation']['formal_ci']['diagnostic']
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'passed': True, 'scope': '源码挂载的受控慢退出夹具' if args.shutdown else '源码挂载的受控慢退役夹具', 'results': results}, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
