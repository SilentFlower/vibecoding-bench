"""复用固定的 AGY 已处理执行映像，为构建准备可核验的输入。"""
import argparse
import hashlib
import json
import lzma
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

from source_layout import source_path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(source_path(REPO, 'orchestrator')))
from agy_auth import SOURCE_BYTES, SOURCE_SHA256

TAG = 'agy-runtime-1.5.9-v1'
ASSET = 'agy-execution-linux-x64.xz'
ARCHIVE_BYTES = 80922084
ARCHIVE_SHA256 = '22ade718c0914d0a7ea14cac1e1575a78e0c8a7b337f49f3ff5c729291f7cfea'
URL = f'https://github.com/SilentFlower/vibecoding-bench/releases/download/{TAG}/{ASSET}'
BLOCK = 1024 * 1024


def _regular(path: Path, size: int) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != size:
        raise ValueError('AGY处理产物的文件类型或长度不符')


def _decode(archive: Path, output: Path) -> None:
    _regular(archive, ARCHIVE_BYTES)
    compressed, image = hashlib.sha256(), hashlib.sha256()
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=512 * 1024 ** 2)
    total, packed = 0, 0
    with archive.open('rb') as source, output.open('xb') as target:
        os.chmod(output, 0o600)
        while block := source.read(BLOCK):
            packed += len(block)
            if packed > ARCHIVE_BYTES or decoder.eof:
                raise ValueError('AGY处理产物包含超量或尾随内容')
            compressed.update(block)
            while True:
                decoded = decoder.decompress(block, max_length=BLOCK)
                block = b''
                total += len(decoded)
                if total > SOURCE_BYTES:
                    raise ValueError('AGY执行映像超过固定长度')
                image.update(decoded)
                target.write(decoded)
                if decoder.eof:
                    if decoder.unused_data:
                        raise ValueError('AGY处理产物包含尾随内容')
                    break
                if decoder.needs_input:
                    break
        if (not decoder.eof or packed != ARCHIVE_BYTES or total != SOURCE_BYTES
                or compressed.hexdigest() != ARCHIVE_SHA256 or image.hexdigest() != SOURCE_SHA256):
            raise ValueError('AGY处理产物或执行映像身份不符')
        target.flush()
        os.fsync(target.fileno())
    output.chmod(0o755)


def artifact_manifest() -> dict:
    """返回固定处理产物的双层身份。@return 仅包含分发与执行映像元数据。"""
    return {'schema_version': 1, 'source_version': '1.5.9',
        'archive': {'name': ASSET, 'bytes': ARCHIVE_BYTES, 'sha256': ARCHIVE_SHA256},
        'image': {'bytes': SOURCE_BYTES, 'sha256': SOURCE_SHA256}}


def export_artifact(source: Path, output: Path) -> dict:
    """独占导出已核验附件。@param source 现有XZ处理产物。@param output 全新附件目录。@return 固定身份清单。"""
    if output.exists() or output.is_symlink():
        raise ValueError('AGY附件目录已存在')
    _regular(source, ARCHIVE_BYTES)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.agy-export-', dir=output.parent) as temporary:
        root = Path(temporary)
        staged = root / 'complete'
        staged.mkdir(mode=0o700)
        shutil.copyfile(source, staged / ASSET)
        _decode(staged / ASSET, root / 'verified-image')
        value = artifact_manifest()
        (staged / 'agy-artifact.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        os.rename(staged, output)
    return value


def prepare(directory: Path, source: Path | None = None) -> Path:
    """从现有处理产物或自有缓存准备镜像输入。@param directory 构建私有目录。@param source 可选现有XZ。@return 已核验执行体路径。"""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / 'agy-1.5.9'
    if source is None and (target.exists() or target.is_symlink()):
        _regular(target, SOURCE_BYTES)
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != SOURCE_SHA256:
                raise ValueError('AGY构建输入缓存身份不符')
        target.chmod(0o755)
        return target.resolve()
    cached = directory / ASSET
    with tempfile.TemporaryDirectory(prefix='.agy-prepare-', dir=directory) as temporary:
        root = Path(temporary)
        archive = source if source is not None else cached
        downloaded = source is None and not (cached.exists() or cached.is_symlink())
        if downloaded:
            archive = root / ASSET
            with urlopen(URL, timeout=60) as response, archive.open('xb') as output:
                os.chmod(archive, 0o600)
                count = 0
                while block := response.read(BLOCK):
                    count += len(block)
                    if count > ARCHIVE_BYTES:
                        raise ValueError('AGY处理产物下载超过固定长度')
                    output.write(block)
        binary = root / 'image'
        _decode(archive, binary)
        # 两层身份均成功后发布缓存，下载中断和解码失败只留下临时文件。
        if downloaded:
            os.replace(archive, cached)
        os.replace(binary, target)
    return target.resolve()


def main() -> None:
    """执行处理产物导出或CI准备。@return 无；校验失败保持非零退出。"""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    export = commands.add_parser('export')
    export.add_argument('--source', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    build = commands.add_parser('prepare')
    build.add_argument('--directory', type=Path, required=True)
    build.add_argument('--source', type=Path)
    args = parser.parse_args()
    if args.action == 'export':
        print(json.dumps(export_artifact(args.source, args.output), ensure_ascii=False))
        return
    binary = prepare(args.directory, args.source)
    if os.environ.get('GITHUB_ENV'):
        if '\n' in str(binary) or '\r' in str(binary):
            raise ValueError('AGY构建输入路径无效')
        with Path(os.environ['GITHUB_ENV']).open('a') as stream:
            stream.write('V3_AGY_AUTH_ASSET=' + str(binary) + '\n')
    print(json.dumps({'prepared': True, 'source': 'processed_artifact', 'sha256': SOURCE_SHA256}))


if __name__ == '__main__':
    main()
