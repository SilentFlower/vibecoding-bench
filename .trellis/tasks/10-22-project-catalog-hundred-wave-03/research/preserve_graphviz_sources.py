"""保留Graphviz与相关弱互惠运行库的精确Debian对应源码和补丁。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
import re
from shutil import copyfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen


SOURCES = {'graphviz', 'libtool', 'glib2.0', 'pango1.0', 'fribidi', 'gts', 'libde265',
    'libheif', 'libthai', 'libdatrie', 'x265', 'util-linux', 'libselinux', 'cairo', 'graphite2'}


def main() -> None:
    """按来源版本下载完整原件，不将源码存在冒充可重复构建。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-03')
    origin = work / 'graphviz-system-artifacts-attempt-003'
    provenance = json.loads((origin / 'provenance.json').read_text())
    output = work / 'graphviz-corresponding-sources'
    output.mkdir(parents=True, exist_ok=False)
    versions = {row['source_package']: row['source_version'] for row in provenance['files']}

    def download(package: str) -> dict:
        """核官方描述和每个源码文件SHA。@param package 已观察来源包。@return 来源证据。"""
        version = versions[package].split(':', 1)[-1]
        prefix = package[:4] if package.startswith('lib') else package[0]
        directory = output / package
        directory.mkdir()
        filename = package + '_' + version + '.dsc'
        failures, descriptor, base = [], None, None
        for root in ('https://deb.debian.org/debian', 'https://security.debian.org/debian-security'):
            base = root + '/pool/main/' + prefix + '/' + package + '/'
            try:
                descriptor = urlopen(base + quote(filename), timeout=45).read()
                break
            except HTTPError as error:
                failures.append({'url': base + quote(filename), 'status': error.code})
        if descriptor is None:
            raise ValueError('精确源码描述不可获取：' + package + ' ' + version)
        (directory / filename).write_bytes(descriptor)
        artifacts = [{'path': 'artifacts/graphviz-source/' + package + '/' + filename,
            'digest': sha256(descriptor).hexdigest(), 'size': len(descriptor)}]
        checksums = descriptor.decode().split('Checksums-Sha256:\n', 1)[1].split('\nFiles:', 1)[0]
        for checksum, size, name in re.findall(r'^ ([0-9a-f]{64}) (\d+) (\S+)$', checksums, re.M):
            if Path(name).name != name or not name.startswith(package + '_'):
                raise ValueError('源码描述越界文件')
            raw = urlopen(base + quote(name), timeout=60).read()
            if len(raw) != int(size) or sha256(raw).hexdigest() != checksum:
                raise ValueError('源码SHA与官方描述不符：' + name)
            (directory / name).write_bytes(raw)
            artifacts.append({'path': 'artifacts/graphviz-source/' + package + '/' + name,
                'digest': checksum, 'size': len(raw)})
        if len(artifacts) < 2:
            raise ValueError('缺少实际源码原件')
        result = {'source_package': package, 'version': versions[package], 'descriptor_url': base + quote(filename),
            'artifacts': artifacts, 'earlier_http_failures': failures}
        (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        return result

    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        for future in as_completed([executor.submit(download, package) for package in sorted(SOURCES)]):
            result = future.result()
            results.append(result)
            print(json.dumps({'source_package': result['source_package'], 'files': len(result['artifacts'])}), flush=True)
    artifacts = [row for result in results for row in result['artifacts']]
    report = {'status': 'passed', 'sources': sorted(results, key=lambda row: row['source_package']),
        'artifacts': artifacts, 'binaries_rebuilt': False,
        'scope': '观察版本对应的官方完整源码和Debian补丁；其余依赖版权/许可原文及来源包版本保存在制品来源证据中，不作重构建声明'}
    (output / 'provenance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for key in ('transitions', 'python-statemachine'):
        environment = work / 'drafts/environments' / (key + '-py312')
        profile_path = environment / 'profile/profile.json'
        profile = json.loads(profile_path.read_text())
        for row in artifacts:
            relative = Path(row['path']).relative_to('artifacts/graphviz-source')
            target = environment / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ValueError('拒绝覆盖既有源码制品')
            copyfile(output / relative, target)
            target.chmod(0o644)
        profile['artifacts'] += artifacts
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'preserved', 'source_packages': len(results), 'files': len(artifacts),
        'bytes': sum(row['size'] for row in artifacts)}))


if __name__ == '__main__':
    main()
