"""以断网合成探针验证失败证据与原生两代准备，输出仅含受控结果。"""
import argparse
import io
import json
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from docker.models.containers import ContainerCollection
from verify_agy_runtime import native_probe


def main() -> None:
    """验证单个隔离场景。@return 无；断言失败保持非零状态。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--mode', choices=('fault', 'normal', 'crash'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode != 'fault':
        value = native_probe(args.image, image_package=True, crash=args.mode == 'crash')
    else:
        original = ContainerCollection.run

        def run(manager, *items, **options):
            """只替换本次合成执行体路径以注入启动失败。@param manager Docker容器集合。@param items 原参数。@param options 原选项。@return 隔离容器。"""
            source = next(Path(name) for name, value in options['volumes'].items() if value['bind'] == '/state')
            path = source / 'supervisor.json'
            config = json.loads(path.read_text())
            config['binary_path'] = '/usr/local/bin/synthetic-missing-runtime'
            path.write_text(json.dumps(config))
            return original(manager, *items, **options)

        output = io.StringIO()
        with patch.object(ContainerCollection, 'run', new=run), redirect_stderr(output):
            try:
                native_probe(args.image, image_package=True)
            except ValueError as error:
                original_error = str(error)
            else:
                raise AssertionError('合成执行体缺失应拒绝')
        evidence = json.loads(output.getvalue().strip())
        assert evidence['phase'] == 'prepared' and evidence['credential_generation'] == 1
        assert evidence['capture_failed'] == [], evidence
        # 原worker失败后已回收私有材料；公开分类及资源状态仍应完整。
        assert evidence['runtime']['stages']['worker_config'] == 0, evidence
        assert evidence['error_codes'] == {'worker_start_failed': 1}, evidence
        assert 'synthetic-missing-runtime' not in json.dumps(evidence)
        value = {'passed': True, 'original_error': original_error, 'evidence': evidence, 'real_model_requests': 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': value['passed'], 'mode': args.mode, 'real_model_requests': 0}))


if __name__ == '__main__':
    main()
