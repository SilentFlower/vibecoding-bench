"""从固定官方npm来源构建并严格核验CI所需的280分发体。"""
import argparse
import base64
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parent / 'orchestrator'))
from native_sender import BYTES_280, SHA256_280

URL = 'https://registry.npmjs.org/@anthropic-ai/claude-code-linux-x64/-/claude-code-linux-x64-2.1.280.tgz'
INTEGRITY = 'dJHWFrDSIZ26hdLucnK3ehLmzdzYl3MsPC1RzUctAUaYnZlH5kfAZxnK8qYRAQ89GX3OPrLsnFdt/QnP+0Ck6Q=='
SOURCE_SHA256 = '1e08503dbdf3c2cb0d706d32f3408277388d1c76ef108673e8fe42c1b322925b'


def verify(path: Path) -> None:
    """核对最终制品，缓存命中也执行。@param path 分发体路径。@return None。"""
    if path.stat().st_size != BYTES_280 or hashlib.sha256(path.read_bytes()).hexdigest() != SHA256_280:
        raise ValueError('CI的280运行时制品身份不匹配')


def main() -> None:
    """准备固定制品，官方程序仅在隔离构建器内执行。@return None。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    output = args.directory.resolve() / 'ccrb-runtime'
    if output.exists():
        verify(output)
        return
    with tempfile.TemporaryDirectory(prefix='ccrb-ci-source-') as temporary:
        root = Path(temporary)
        archive = root / 'official.tgz'
        digest = hashlib.sha512()
        with urllib.request.urlopen(URL, timeout=60) as response, archive.open('xb') as target:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 160 * 1024 ** 2:
                    raise ValueError('官方来源归档超过已知预算')
                digest.update(chunk)
                target.write(chunk)
        if base64.b64encode(digest.digest()).decode() != INTEGRITY:
            raise ValueError('官方npm来源完整性不符')
        source = root / 'claude'
        with tarfile.open(archive, 'r:gz') as package:
            member = package.getmember('package/claude')
            if not member.isfile() or member.size != 233709640:
                raise ValueError('官方来源文件布局不符')
            # 只读取精确成员，归档中的路径和链接均不会写入宿主目录。
            with package.extractfile(member) as original, source.open('xb') as target:
                shutil.copyfileobj(original, target)
        if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
            raise ValueError('官方来源执行文件摘要不符')
        source.chmod(0o555)
        subprocess.run(['bun', 'scripts/build-runtime.ts', '--source', str(source), '--out', str(output)],
            cwd=PROJECT, check=True)
    verify(output)


if __name__ == '__main__':
    main()
