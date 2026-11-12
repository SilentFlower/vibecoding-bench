"""导出固定文件及摘要，正式来源只接纳已提交的干净采集器。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

FILES = ('observer.py', 'http_capture.py', 'client.py', 'broker.py', 'launch.c', 'capture.bpf.c', 'build.py', 'seccomp.json', 'LICENSE.seccomp')


def main() -> None:
    """生成可审核镜像输入。@return None；源码漂移或目的目录含外来文件时拒绝。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--development', action='store_true')
    parser.add_argument('--control-policy-output', type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    repository = source.parents[1]
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repository, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--', str(source)], cwd=repository, text=True)
    if dirty and not args.development:
        raise SystemExit('正式导出要求采集器源码已提交且路径干净')
    args.output.mkdir(parents=True, exist_ok=True)
    if set(p.name for p in args.output.iterdir()) - set(FILES) - {'manifest.json'}:
        raise SystemExit('目的目录包含清单外文件')
    digests = {}
    for name in FILES:
        digests[name] = hashlib.sha256((source / name).read_bytes()).hexdigest()
        shutil.copyfile(source / name, args.output / name)
    manifest = {'schema_version': 1, 'protocol_version': 1, 'source_revision': revision,
        'development': args.development, 'files': digests}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    if args.control_policy_output:
        shutil.copyfile(source / 'seccomp.json', args.control_policy_output)


if __name__ == '__main__':
    main()
