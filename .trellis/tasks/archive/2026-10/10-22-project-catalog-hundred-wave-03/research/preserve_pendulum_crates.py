"""按固定Cargo.lock保留Rust依赖原始crate及全部随附许可。"""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from shutil import copyfile
import tarfile
import tomllib


def main() -> None:
    """核缓存原件与锁定SHA，不下载或编译新实现。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-03')
    project = work / 'drafts/projects/pendulum'
    lock = project / 'seed/library/rust/Cargo.lock'
    packages = [row for row in tomllib.loads(lock.read_text())['package'] if 'checksum' in row]
    output = work / 'pendulum-rust-dependency-source.tar'
    if output.exists():
        raise ValueError('拒绝覆盖依赖来源归档')
    licenses = project / 'seed/app/rust-licenses'
    licenses.mkdir(exist_ok=False)
    rows = []
    with tarfile.open(output, 'w') as outer:
        for package in packages:
            name = package['name'] + '-' + package['version']
            originals = list(Path('/root/.cargo/registry/cache').glob('*/' + name + '.crate'))
            if len(originals) != 1:
                raise ValueError('精确锁定crate原件不唯一：' + name)
            raw = originals[0].read_bytes()
            if sha256(raw).hexdigest() != package['checksum']:
                raise ValueError('crate摘要与Git锁定不符：' + name)
            info = tarfile.TarInfo(name + '.crate')
            info.mode, info.mtime, info.size = 0o644, 0, len(raw)
            outer.addfile(info, BytesIO(raw))
            preserved = []
            with tarfile.open(fileobj=BytesIO(raw), mode='r:gz') as archive:
                metadata = tomllib.loads(archive.extractfile(name + '/Cargo.toml').read().decode())['package']
                for member in archive.getmembers():
                    path = Path(member.name)
                    if not member.isfile() or path.is_absolute() or '..' in path.parts or path.parts[0] != name:
                        continue
                    if not any(part.upper().startswith(('LICENSE', 'COPYING', 'NOTICE', 'COPYRIGHT')) for part in path.parts[1:]):
                        continue
                    content = archive.extractfile(member).read()
                    destination = licenses / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                    preserved.append({'path': str(destination.relative_to(project)), 'sha256': sha256(content).hexdigest()})
            if not preserved:
                raise ValueError('依赖缺少随附许可原件：' + name)
            rows.append({'name': package['name'], 'version': package['version'], 'crate_sha256': package['checksum'],
                'declared_license': metadata.get('license'), 'licenses': preserved})
        record = json.dumps({'cargo_lock_sha256': sha256(lock.read_bytes()).hexdigest(), 'packages': rows,
            'scope': '精确锁定依赖的完整发布源码及随附许可；不声称已记录历史编译器或本轮重构建'}, ensure_ascii=False, indent=2).encode() + b'\n'
        info = tarfile.TarInfo('provenance.json');info.mode, info.mtime, info.size = 0o644, 0, len(record)
        outer.addfile(info, BytesIO(record))
    environment = work / 'drafts/environments/pendulum-py312'
    destination = environment / 'artifacts/pendulum-rust-dependencies.tar'
    copyfile(output, destination)
    destination.chmod(0o644)
    profile_path = environment / 'profile/profile.json'
    profile = json.loads(profile_path.read_text())
    profile['artifacts'].append({'path': 'artifacts/' + destination.name,
        'digest': sha256(output.read_bytes()).hexdigest(), 'size': output.stat().st_size})
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n')
    Path(__file__).with_name('pendulum-rust-licenses.json').write_bytes(record)
    print(json.dumps({'packages': len(rows), 'license_files': sum(len(row['licenses']) for row in rows),
        'archive_sha256': sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
