"""从受版本管理源码生成固定AGY观察资源，完整ELF沿私有制品交付。"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from .storage import SOURCE_SHA


def build_resources(root: Path) -> dict:
    """编译观察器并登记实际资源身份。@param root 当前适配源码目录。@return 构建资源清单。"""
    resources = root / 'resources'
    resources.mkdir(exist_ok=True)
    subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-DOBSERVE_ALL_STOPS=0',
        str(root / 'source/observer.c'), '-lcrypto', '-o', str(resources / 'observer-c')], check=True)
    subprocess.run(['gcc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
        str(root / 'source/relocation_reclaim.c'), '-ldl', '-o', str(resources / 'relocation_reclaim.so')], check=True)
    names = ['observer-c', 'relocation_reclaim.so', 'cascade-config.json', 'telemetry-itabs.json']
    manifest = {'source_sha256': SOURCE_SHA, 'resource_hashes': {
        'resources/' + name: hashlib.sha256((resources / name).read_bytes()).hexdigest() for name in names}}
    (resources / 'admission.json').write_text(json.dumps(manifest, sort_keys=True))
    return manifest


def main() -> None:
    """构建指定的交付副本。@return 无。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    build_resources(args.root)


if __name__ == '__main__':
    main()
