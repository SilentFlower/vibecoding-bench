"""在候选导出与正式发布前验收镜像自身的AGY模块、固定映像和物理退出。"""
import argparse
import json
from pathlib import Path

import manage
from agy_auth import require_auth_asset
from verify_agy_runtime import native_probe


def verify_images(manifest: Path) -> dict:
    """验证当前同批镜像。@param manifest 本地联合清单。@return 零模型镜像验收证据。"""
    value = json.loads(manifest.read_text())
    require_auth_asset(value.get('agy_auth'))
    manage.inspect_images(manage._manifest_values(manifest))
    for role in ('control', 'account'):
        path = '/app:/usr/local/bin' if role == 'control' else '/opt/v3/python:/usr/local/bin'
        probe = ('import agy_auth,agy_environment,agy_runtime.capture' if role == 'control' else
            'from agy_runtime.storage import verify_resources;verify_resources();import agy_runtime.supervisor')
        manage.command('docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges:true', '--entrypoint', 'python3',
            '-e', 'PYTHONPATH=' + path, value['images'][role]['reference'], '-c', probe)
    account = value['images']['account']['reference']
    normal = native_probe(account, image_package=True)
    crash = native_probe(account, crash=True, image_package=True)
    return {'passed': True, 'normal': normal, 'crash': crash, 'real_model_requests': 0}


def main() -> None:
    """读取当前镜像清单并输出验收结果。@return 无；任一检查失败保持非零状态。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_images(args.manifest), ensure_ascii=False))


if __name__ == '__main__':
    main()
