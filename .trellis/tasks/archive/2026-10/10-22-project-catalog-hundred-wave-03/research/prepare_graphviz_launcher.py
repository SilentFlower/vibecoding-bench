"""为会清除GVBINDIR的pydot准备固定启动器，保留原始二进制原件。"""
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile


def main() -> None:
    """仅恢复工具自己的插件定位环境，不改原测试或目标系统。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-03')
    launcher = '#!/bin/sh\n# 为清理环境的调用方恢复固定插件定位。\nGVBINDIR=/offline/artifacts/graphviz-libs\nexport GVBINDIR\nexec /offline/artifacts/graphviz-bin/original/dot "$@"\n'.encode("utf-8")
    checksum = sha256(launcher).hexdigest()
    original_sha = '419049c248ab2b4830da209e93ae98a5bdb9580e12057f547bb31c0a336153da'
    for key in ('transitions', 'python-statemachine'):
        environment = work / 'drafts/environments' / (key + '-py312')
        path = environment / 'artifacts/graphviz-bin/dot'
        if sha256(path.read_bytes()).hexdigest() != original_sha:
            raise ValueError('原Graphviz工具身份不符，拒绝覆盖')
        original = path.parent / 'original/dot'
        original.parent.mkdir(exist_ok=False)
        if original.exists():
            raise ValueError('原件目标已存在')
        copyfile(path, original)
        original.chmod(0o755)
        path.write_bytes(launcher)
        path.chmod(0o755)
        profile_path = environment / 'profile/profile.json'
        profile = json.loads(profile_path.read_text())
        profile['artifacts'] = [{**row, 'digest': checksum, 'size': len(launcher)}
            if row['path'] == 'artifacts/graphviz-bin/dot' else row for row in profile['artifacts']]
        profile['artifacts'].append({'path': 'artifacts/graphviz-bin/original/dot', 'digest': original_sha,
            'size': original.stat().st_size})
        if key == 'python-statemachine':
            wheel = next((work / 'wheels').glob('sphinxcontrib_mermaid-2.1.1-*.whl'))
            with ZipFile(wheel) as archive:
                metadata = archive.read('sphinxcontrib_mermaid-2.1.1.dist-info/METADATA').decode()
                if 'Name: sphinxcontrib-mermaid\n' not in metadata or 'Version: 2.1.1\n' not in metadata:
                    raise ValueError('实际wheel元数据不符')
            target = environment / 'artifacts' / wheel.name
            if target.exists():
                raise ValueError('拒绝覆盖wheel')
            copyfile(wheel, target)
            profile['requirements'].append('sphinxcontrib-mermaid==2.1.1')
            profile['artifacts'].append({'path': 'artifacts/' + wheel.name,
                'digest': sha256(wheel.read_bytes()).hexdigest(), 'size': wheel.stat().st_size})
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n')
    record = {'launcher_sha256': checksum, 'original_binary_sha256': original_sha,
        'scope': 'pydot4.0.1仅传PATH/LD_LIBRARY_PATH/SYSTEMROOT；固定启动器恢复原插件定位，参数原样交给原始dot',
        'script': launcher.decode(), 'production_touched': False}
    Path(__file__).with_name('graphviz-launcher-provenance.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'launcher_sha256': checksum, 'original_binary_sha256': original_sha}))


if __name__ == '__main__':
    main()
