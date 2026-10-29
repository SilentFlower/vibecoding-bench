"""冻结Click原生分页测试所需的真实Debian less，不安装或替换系统程序。"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen


ROOT = Path.cwd()
ENVIRONMENT = ROOT / '.deploy/project-catalog-hundred/stage-01/drafts/environments/click-py312'
OFFICIAL_BINARY_SHA256 = '3c4ee8ce5e0f625e1169da9584e309c375a8a68e22de5821461d14446825cc1a'
PREFIX = 'https://deb.debian.org/debian/pool/main/l/less/'


def main() -> None:
    """核官方二进制摘要，保留包、许可及匹配源文件。@return None。"""
    directory = ENVIRONMENT / 'artifacts/less'
    directory.mkdir(parents=True, exist_ok=False)
    names = ['less_590-2.1~deb12u2_amd64.deb', 'less_590-2.1~deb12u2.dsc',
        'less_590.orig.tar.gz', 'less_590-2.1~deb12u2.debian.tar.xz']
    downloaded = {}
    for name in names:
        with urlopen(PREFIX + name, timeout=30) as response:
            data = response.read()
        (directory / name).write_bytes(data)
        downloaded[name] = {'url': PREFIX + name, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    package = directory / names[0]
    if downloaded[names[0]]['sha256'] != OFFICIAL_BINARY_SHA256:
        raise ValueError('Debian官方包摘要不符')
    dsc = (directory / names[1]).read_text()
    checksums = dsc.split('Checksums-Sha256:\n', 1)[1].split('Files:', 1)[0]
    for name in names[2:]:
        if downloaded[name]['sha256'] not in checksums:
            raise ValueError('源文件与对应dsc摘要不符')
    archive = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(package)])
    with tarfile.open(fileobj=BytesIO(archive)) as contents:
        for source, destination in [('./usr/bin/less', 'less'),
                ('./usr/share/doc/less/copyright', 'copyright')]:
            member = contents.getmember(source)
            if not member.isfile():
                raise ValueError('Debian包中预期普通文件类型不符')
            data = contents.extractfile(member).read()
            (directory / destination).write_bytes(data)
    profile_path = ENVIRONMENT / 'profile/profile.json'
    profile = json.loads(profile_path.read_text())
    for path in sorted(directory.iterdir()):
        path.chmod(0o644)
        profile['artifacts'].append({'path': str(path.relative_to(ENVIRONMENT)),
            'digest': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size})
    profile['notes'] = 'Click完整原生分页测试需要Debian Bookworm less 590-2.1~deb12u2；制品以数据保存，验证器只在本次/work独占venv复制并赋予执行位，不改系统或挂载权限。保留官方包、许可和匹配源文件。'
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n')
    proof = {'package_version': '590-2.1~deb12u2', 'target': 'Debian 12 amd64',
        'official_package_page': 'https://packages.debian.org/bookworm/less',
        'official_binary_sha256_page': 'https://packages.debian.org/bookworm/amd64/less/download',
        'downloads': downloaded, 'extracted_binary_sha256': hashlib.sha256((directory / 'less').read_bytes()).hexdigest(),
        'copyright_sha256': hashlib.sha256((directory / 'copyright').read_bytes()).hexdigest(),
        'system_installation': False, 'sandbox_permissions_changed': False}
    Path(__file__).with_name('click-pager-provenance.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == '__main__':
    main()
