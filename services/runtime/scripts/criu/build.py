"""构建固定 CRIU 4.2 与封存 memfd 执行体恢复补丁。"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

VERSION = '4.2'
ARCHIVE_SHA256 = '0c6e51af878e63df7391e6dffbbe5f0ced429bc9f1e5a603020bfd2503065c39'
ARCHIVE_URL = 'https://codeload.github.com/checkpoint-restore/criu/tar.gz/refs/tags/v4.2'
PATCH = Path(__file__).resolve().parents[2] / 'native/criu/memfd-executable.patch'
PATCH_SHA256 = '5a2d61a6666fd0b50dc089776a00b355df1258aa0ab6f8392f38a33d54dbfa92'


def digest(path: Path) -> str:
    """流式计算文件摘要。@param path 本地文件。@return 小写 SHA256。"""
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def verify_archive(archive: Path) -> None:
    """核对固定来源归档。@param archive 待检查归档。@return 校验成功返回，无效时抛错。"""
    if not archive.is_file() or digest(archive) != ARCHIVE_SHA256:
        raise ValueError('CRIU 来源归档 SHA256 不匹配')


def run(command: list[str], cwd: Path, environment: dict[str, str], log) -> None:
    """有界执行固定构建命令。@param command 参数数组。@param cwd 工作目录。@param environment 构建环境。@param log 私有构建日志。@return 成功返回，失败抛错。"""
    try:
        subprocess.run(command, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        log.flush()
        tail = '\n'.join(Path(log.name).read_text(errors='replace').splitlines()[-12:])[-3000:]
        raise RuntimeError('CRIU 构建步骤失败：' + tail) from error


def build(output: Path, archive: Path | None = None, dependency_prefix: Path | None = None, patch: Path | None = None) -> dict:
    """生成固定恢复工具及来源清单。@param output 全新输出目录。@param archive 已有来源归档，省略时下载固定地址。@param dependency_prefix 可选私有开发依赖前缀。@param patch 镜像包内的同摘要补丁。@return 构建清单。"""
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('固定 CRIU 配方仅支持 Linux x64')
    if output.exists() or output.is_symlink():
        raise FileExistsError('CRIU 输出目录必须全新')
    if archive is not None:
        verify_archive(archive)
    patch = (patch or PATCH).resolve()
    if digest(patch) != PATCH_SHA256:
        raise ValueError('CRIU 补丁 SHA256 不匹配')
    output.mkdir(mode=0o700, parents=False)
    completed = False
    try:
        with tempfile.TemporaryDirectory(prefix='.criu-build-', dir=output) as temporary:
            work = Path(temporary)
            if archive is None:
                archive = work / 'criu-v4.2.tar.gz'
                with urlopen(ARCHIVE_URL, timeout=40) as response, archive.open('wb') as target:
                    shutil.copyfileobj(response, target)
                verify_archive(archive)
            with tarfile.open(archive) as source:
                source.extractall(work, filter='data')
            source_root = work / 'criu-4.2'
            environment = {**os.environ, 'LANG': 'C.UTF-8', 'SOURCE_DATE_EPOCH': '0'}
            if dependency_prefix is not None:
                dependency_prefix = dependency_prefix.resolve(strict=True)
                libraries = dependency_prefix / 'usr/lib/x86_64-linux-gnu'
                include = dependency_prefix / 'usr/include'
                environment.update({
                    'PATH': str(dependency_prefix / 'usr/bin') + ':' + environment['PATH'],
                    'LD_LIBRARY_PATH': str(libraries), 'LIBRARY_PATH': str(libraries),
                    'CPATH': str(include), 'PKG_CONFIG_LIBDIR': str(libraries / 'pkgconfig'),
                    'PKG_CONFIG_SYSROOT_DIR': str(dependency_prefix),
                })
                # 上游描述符生成规则固定写 /usr/include；私有依赖只改变构建时的包含目录。
                makefile = source_root / 'images/Makefile'
                makefile.write_text(makefile.read_text().replace('--proto_path=/usr/include', '--proto_path=' + str(include)))
            with (output / 'build.log').open('w') as log:
                run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], source_root, environment, log)
                flags = '-ffile-prefix-map=' + str(work) + '=/criu-build'
                run(['make', '-j' + str(min(4, os.cpu_count() or 1)), 'criu', 'WERROR=1', 'USERCFLAGS=' + flags],
                    source_root, environment, log)
            executable = output / 'criu'
            shutil.copyfile(source_root / 'criu/criu', executable)
            executable.chmod(0o755)
            checked = subprocess.run([str(executable), '--version'], capture_output=True, text=True,
                                     env=environment, check=True, timeout=10)
            if checked.stdout.strip() != 'Version: ' + VERSION:
                raise ValueError('CRIU 构建版本不匹配')
            compiler = subprocess.run(['gcc', '-dumpfullversion'], capture_output=True, text=True,
                                      env=environment, check=True, timeout=10).stdout.strip()
            licenses = output / 'licenses'
            licenses.mkdir()
            shutil.copyfile(source_root / 'COPYING', licenses / 'CRIU-COPYING')
            shutil.copyfile(source_root / 'images/LICENSE', licenses / 'CRIU-images-LICENSE')
            configuration = source_root / 'include/common/config.h'
            manifest = {'schema_version': 1, 'source_version': VERSION, 'source_url': ARCHIVE_URL,
                        'archive_sha256': ARCHIVE_SHA256, 'patch_sha256': digest(patch),
                        'binary_sha256': digest(executable), 'binary_bytes': executable.stat().st_size,
                        'platform': 'linux-x64', 'compiler': 'gcc-' + compiler,
                        'source_date_epoch': 0, 'memfd_executable_restore': 1,
                        'configuration_sha256': digest(configuration),
                        'configuration': configuration.read_text()}
            (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            (output / 'build.log').chmod(0o600)
            completed = True
            return manifest
    finally:
        if not completed:
            shutil.rmtree(output)


def main() -> None:
    """解析显式构建参数并输出安全清单。@return 成功输出清单，失败退出。"""
    parser = argparse.ArgumentParser(description='构建固定 CRIU 4.2 恢复工具')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--dependency-prefix', type=Path)
    parser.add_argument('--patch', type=Path)
    arguments = parser.parse_args()
    manifest = build(arguments.out.absolute(), arguments.archive, arguments.dependency_prefix, arguments.patch)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
