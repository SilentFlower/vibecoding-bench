"""准备与目标Debian12匹配的离线gettext，不向系统安装程序。"""
from hashlib import sha256
from argparse import ArgumentParser
import json
from pathlib import Path
import re
from shutil import copyfile
from urllib.request import urlopen


def main() -> None:
    """核官方包SHA，保留三程序、两共享库、许可和对应源码。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-03')
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, default=1)
    options = parser.parse_args()
    prepared = work / 'gettext-debian-preparation'
    package = prepared / 'gettext_0.21-12_amd64.deb'
    assert sha256(package.read_bytes()).hexdigest() == '8c1f9d43575373ce311f51d00a13afbb4888d63aa559a93a3472f5d77513b60c'
    destination = work / ('gettext-system-artifacts' if options.attempt == 1
        else 'gettext-system-artifacts-attempt-' + str(options.attempt).zfill(3))
    destination.mkdir(parents=True, exist_ok=False)
    rows = []

    def preserve(source: Path, relative: str, executable: bool = False) -> dict:
        """复制已核普通原件。@param source 原件。@param relative 制品路径。@param executable 执行位。@return 身份。"""
        assert not source.is_symlink() and source.is_file()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(source, target)
        target.chmod(0o755 if executable else 0o644)
        row = {'path': 'artifacts/' + relative, 'digest': sha256(target.read_bytes()).hexdigest(), 'size': target.stat().st_size}
        rows.append(row)
        return row

    executables = []
    for name in ('msgfmt', 'msgmerge', 'xgettext'):
        row = preserve(prepared / 'root/usr/bin' / name, 'gettext-bin/' + name, True)
        executables.append([name, row['path'], row['digest']])
    libraries = []
    for name in ('libgettextsrc-0.21.so', 'libgettextlib-0.21.so'):
        row = preserve(prepared / 'root/usr/lib/x86_64-linux-gnu' / name, 'gettext-libs/' + name)
        libraries.append({'path': row['path'], 'sha256': row['digest']})
    manifest = destination / 'gettext-libs/libraries.json'
    manifest.write_text(json.dumps({'schema': 1, 'libraries': libraries}, indent=2) + '\n')
    rows.append({'path': 'artifacts/gettext-libs/libraries.json', 'digest': sha256(manifest.read_bytes()).hexdigest(), 'size': manifest.stat().st_size})
    preserve(prepared / 'root/usr/share/doc/gettext/copyright', 'licenses/gettext-copyright')
    preserve(Path('/usr/share/common-licenses/GPL-3'), 'licenses/gettext-GPL-3')
    preserve(package, 'gettext-source/gettext_0.21-12_amd64.deb')
    base = 'https://deb.debian.org/debian/pool/main/g/gettext/'
    descriptor = urlopen(base + 'gettext_0.21-12.dsc', timeout=60).read()
    source_root = destination / 'gettext-source'
    (source_root / 'gettext_0.21-12.dsc').write_bytes(descriptor)
    rows.append({'path': 'artifacts/gettext-source/gettext_0.21-12.dsc', 'digest': sha256(descriptor).hexdigest(), 'size': len(descriptor)})
    downloads = []
    for expected, size, name in re.findall(r'^ ([0-9a-f]{64}) (\d+) (\S+)$', descriptor.decode(), re.M):
        if name not in ('gettext_0.21.orig.tar.xz', 'gettext_0.21.orig.tar.xz.asc', 'gettext_0.21-12.debian.tar.xz'):
            raise ValueError('来源描述中出现未审核文件')
        data = urlopen(base + name, timeout=60).read()
        assert len(data) == int(size) and sha256(data).hexdigest() == expected
        (source_root / name).write_bytes(data)
        rows.append({'path': 'artifacts/gettext-source/' + name, 'digest': expected, 'size': len(data)})
        downloads.append({'url': base + name, 'sha256': expected, 'size': len(data)})
    assert len(downloads) == 3
    record = {'status': 'prepared_pending_target_validation', 'package': 'gettext', 'version': '0.21-12',
        'official_checksum_page': 'https://packages.debian.org/bookworm/amd64/gettext/download',
        'package_sha256': sha256(package.read_bytes()).hexdigest(), 'executables': executables,
        'system_libraries': ['artifacts/gettext-libs/libraries.json', sha256(manifest.read_bytes()).hexdigest()],
        'artifacts': rows, 'source_downloads': downloads, 'system_installed': False,
        'target_image_replaced': False, 'scope': '固定官方Debian包原件与对应源码；当前镜像完整原生另验'}
    (destination / 'provenance.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: record[key] for key in ('status', 'executables', 'system_libraries')}))


if __name__ == '__main__':
    main()
