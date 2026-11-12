"""在构建机编译只读探针；运行机只需已有内核能力及 libbpf。"""
import platform
from pathlib import Path
import subprocess


def main() -> None:
    """编译固定 x64 UAPI 探针。@return None；编译失败直接退出。"""
    if platform.machine() != 'x86_64':
        raise SystemExit('当前探针仅准入 Linux x64')
    root = Path(__file__).resolve().parent
    subprocess.run(['clang', '-O2', '-g', '-target', 'bpf',
                    '-I/usr/include/x86_64-linux-gnu', '-Wall', '-Werror',
                    '-c', str(root / 'capture.bpf.c'), '-o', str(root / 'capture.bpf.o')], check=True)


if __name__ == '__main__':
    main()
