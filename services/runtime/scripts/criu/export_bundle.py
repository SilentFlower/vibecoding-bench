"""导出恢复器源码与固定构建入口，供账号镜像按自身ABI构建。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

FILES = ('controller.py', 'entry.py', 'entropy.py', 'protocol.py', 'shared_image.py', 'supervisor.py', 'launch.c', 'memfd-executable.patch')


def main() -> None:
    """生成全新镜像输入目录。@return 无。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    runtime = Path(__file__).resolve().parents[2]
    source = runtime / 'native/criu'
    arguments.output.mkdir(parents=True, exist_ok=False)
    for name in FILES:
        shutil.copyfile(source / name, arguments.output / name)
    for name in ('build.py', 'package.py'):
        shutil.copyfile(Path(__file__).with_name(name), arguments.output / name)
    shutil.copyfile(runtime / 'native/tls-observer/seccomp.json', arguments.output / 'seccomp.json')
    shutil.copyfile(runtime / 'native/tls-observer/LICENSE.seccomp', arguments.output / 'LICENSE.seccomp')
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in arguments.output.iterdir()}
    (arguments.output / 'source-manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    main()
