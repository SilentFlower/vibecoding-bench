"""从固定官方npm来源构建并严格核验CI所需的280／293分发体。"""
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parent / 'orchestrator'))
from native_sender import BYTES, BYTES_280, SHA256, SHA256_280

SOURCES = {
    '2.1.280': {'integrity': 'dJHWFrDSIZ26hdLucnK3ehLmzdzYl3MsPC1RzUctAUaYnZlH5kfAZxnK8qYRAQ89GX3OPrLsnFdt/QnP+0Ck6Q==',
        'source_sha256': '1e08503dbdf3c2cb0d706d32f3408277388d1c76ef108673e8fe42c1b322925b', 'source_bytes': 233709640,
        'sha256': SHA256_280, 'bytes': BYTES_280,
        'image_sha256': 'b5ffd54de383a71681043e554156451e3ce277e67e2a4bf04da815a029caee63', 'image_bytes': 111603784},
    '2.1.293': {'integrity': 'tYTbeVuhqD0TW2WJs90Tq+JaKLLnrX5JuxYTLG3pxf4Vr3QMonqsMLu4hZkgVSfEDPZhneFuDDgULQ3/FZzAIw==',
        'source_sha256': '8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978', 'source_bytes': 252755128,
        'sha256': SHA256, 'bytes': BYTES,
        'image_sha256': '0404cca64e0e08ffe347379c543bb83dcc4b36d46cea1c1b6c570c8af14ccb56', 'image_bytes': 112852152},
}


def verify(path: Path, source_version: str = '2.1.280') -> None:
    """校验制品、官方来源、执行映像及当前构建输入。

    :param path: 分发体及相邻构建报告路径。
    :param source_version: 本平台固定的官方版本。
    :return: None；缓存损坏和输入漂移均明确失败。
    """
    identity = SOURCES[source_version]
    if path.stat().st_size != identity['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != identity['sha256']:
        raise ValueError(f'CI的{source_version}运行时制品身份不匹配')
    report_path = Path(str(path) + '.manifest.json')
    if report_path.stat().st_size > 2 * 1024 ** 2:
        raise ValueError('运行时构建报告超过预算')
    report = json.loads(report_path.read_bytes())
    if (report.get('schema_version') != 1 or report.get('source') != {'version': source_version, 'sha256': identity['source_sha256']}
            or report.get('launcher') != {'sha256': identity['sha256'], 'bytes': identity['bytes']}
            or report.get('image') != {'sha256': identity['image_sha256'], 'bytes': identity['image_bytes']}):
        raise ValueError('运行时构建报告来源或制品身份不匹配')
    recipe = report.get('recipe', {})
    builder = (PROJECT / 'scripts/build-runtime.ts').read_text()
    base = re.search(r'const BRIDGE_SOURCES = \[(.*?)\];', builder)
    extra = re.search(r'const bridgePaths = \[\.\.\.BRIDGE_SOURCES, (.*?)\];', builder)
    if not base or not extra:
        raise ValueError('构建输入声明已改变，请同步CI核验合同')
    paths = re.findall(r"'([^']+)'", base[1] + ', ' + extra[1])
    expected = {name: hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() for name in paths}
    if recipe.get('version') != 10 or not expected or recipe.get('bridge_sources') != expected:
        raise ValueError('运行时缓存构建输入与当前仓库不一致，请重新验收固定制品')


def _download_tool(url: str, path: Path, digest: str) -> None:
    # Python下载器提供明确的读取超时；固定SDK在交给构建器之前再次按其原配方核验。
    with urllib.request.urlopen(url, timeout=60) as response, path.open('xb') as target:
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 8 * 1024 ** 2:
                raise ValueError('固定构建工具超过归档预算')
            target.write(chunk)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('固定构建工具来源摘要不匹配')


def main() -> None:
    """准备固定制品，官方程序仅在隔离构建器内执行。@return None。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--source-version', choices=tuple(SOURCES), default='2.1.280')
    args = parser.parse_args()
    identity = SOURCES[args.source_version]
    url = f'https://registry.npmjs.org/@anthropic-ai/claude-code-linux-x64/-/claude-code-linux-x64-{args.source_version}.tgz'
    args.directory.mkdir(parents=True, exist_ok=True)
    output = args.directory.resolve() / 'ccrb-runtime'
    if output.exists():
        verify(output, args.source_version)
        return
    with tempfile.TemporaryDirectory(prefix='ccrb-ci-source-') as temporary:
        root = Path(temporary)
        archive = root / 'official.tgz'
        digest = hashlib.sha512()
        with urllib.request.urlopen(url, timeout=60) as response, archive.open('xb') as target:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 160 * 1024 ** 2:
                    raise ValueError('官方来源归档超过已知预算')
                digest.update(chunk)
                target.write(chunk)
        if base64.b64encode(digest.digest()).decode() != identity['integrity']:
            raise ValueError('官方npm来源完整性不符')
        source = root / 'claude'
        with tarfile.open(archive, 'r:gz') as package:
            member = package.getmember('package/claude')
            if not member.isfile() or member.size != identity['source_bytes']:
                raise ValueError('官方来源文件布局不符')
            # 只读取精确成员，归档中的路径和链接均不会写入宿主目录。
            with package.extractfile(member) as original, source.open('xb') as target:
                shutil.copyfileobj(original, target)
        if hashlib.sha256(source.read_bytes()).hexdigest() != identity['source_sha256']:
            raise ValueError('官方来源执行文件摘要不符')
        source.chmod(0o555)
        release = 'https://github.com/ip7z/7zip/releases/download/26.05/'
        tool_archive, sdk = root / '7zip-tool.tar.xz', root / '7zip-sdk.tar.xz'
        _download_tool(release + '7z2605-linux-x64.tar.xz', tool_archive,
            '22cf82fcc6eb7474f1d5bb4f02c0f8ebd573a718089d6833dc30f8350a3b232e')
        _download_tool(release + '7z2605-src.tar.xz', sdk,
            '0b6080b8c3e7a579161d2d495224c0e51c467576cb4c7048b0ab485ef44cc22e')
        tool = root / '7zz'
        with tarfile.open(tool_archive, 'r:xz') as archive:
            member = archive.getmember('7zz')
            if not member.isfile() or member.size > 8 * 1024 ** 2:
                raise ValueError('固定构建工具归档布局不符')
            with archive.extractfile(member) as original, tool.open('xb') as target:
                shutil.copyfileobj(original, target)
        tool.chmod(0o555)
        subprocess.run(['bun', 'scripts/build-runtime.ts', '--source', str(source), '--out', str(output),
            '--sevenzip', str(tool), '--sdk', str(sdk)], cwd=PROJECT, check=True)
    verify(output, args.source_version)


if __name__ == '__main__':
    main()
