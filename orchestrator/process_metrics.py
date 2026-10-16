"""读取账号容器的真实内存上限与官方 CLI 进程 RSS，不产生上游请求。"""
import argparse
import ctypes
import fcntl
import json
import os
import re
import stat
import tempfile
import time
from pathlib import Path


PROCESS_SOURCE = "v3:procfs:cli"
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?")


def process_executable(process: Path) -> Path:
    """以账号文件身份读取真实 procfs 的 exe，再恢复管理身份核对缓存。

    :param process: 当前 PID 的 procfs 目录。
    :return: 内核提供的可执行文件路径。
    """
    if process.parent != Path('/proc') or os.geteuid() != 0:
        return (process / 'exe').resolve(strict=True)
    # Docker 默认没有 SYS_PTRACE；只在 readlink 期间匹配 CLI 的 fsuid，避免扩大容器能力。
    libc = ctypes.CDLL(None)
    setfsuid, setfsgid = libc.setfsuid, libc.setfsgid
    setfsuid.argtypes, setfsuid.restype = [ctypes.c_uint], ctypes.c_int
    setfsgid.argtypes, setfsgid.restype = [ctypes.c_uint], ctypes.c_int
    previous_gid = setfsgid(1000)
    previous = setfsuid(1000)
    try:
        if setfsuid(0xFFFFFFFF) != 1000 or setfsgid(0xFFFFFFFF) != 1000:
            raise PermissionError('无法使用账号文件身份读取进程来源')
        target = os.readlink(process / 'exe')
    finally:
        setfsuid(previous)
        setfsgid(previous_gid)
        if setfsuid(0xFFFFFFFF) != previous or setfsgid(0xFFFFFFFF) != previous_gid:
            raise RuntimeError('无法恢复进程观察的文件身份')
    return Path(target).resolve(strict=True)


def memory_limit(cgroup: Path = Path("/sys/fs/cgroup")) -> int:
    """读取当前 cgroup 的限制，零仅表示明确的无限制。

    :param cgroup: 当前容器可见的 cgroup 挂载目录。
    :return: 字节上限；缺失或损坏时抛出 ValueError。
    """
    for relative in ("memory.max", "memory/memory.limit_in_bytes", "memory.limit_in_bytes"):
        path = cgroup / relative
        if not path.is_file():
            continue
        value = path.read_text().strip()
        if value == "max":
            return 0
        if value.isdecimal() and int(value) > 0:
            # cgroup v1 用接近 LONG_MAX 的值表示无限制，不能作为真实 RAM 展示。
            return 0 if int(value) >= 1 << 60 else int(value)
        raise ValueError("容器内存限制格式损坏")
    raise ValueError("无法读取实际容器内存限制")


def cli_processes(proc: Path = Path("/proc"), cli: Path = Path("/cli")) -> list[tuple[str, int]]:
    """只识别管理缓存内由账号用户运行的官方原生 CLI。

    :param proc: 当前 PID 命名空间的 procfs。
    :param cli: root 管理的官方版本缓存。
    :return: 官方 CLI 版本和 RSS 字节数；进程退出竞态忽略。
    """
    samples = []
    cache = cli.resolve()
    for process in proc.iterdir():
        if not process.name.isdecimal():
            continue
        try:
            before = (process / "stat").read_text().rsplit(")", 1)[1].split()
            if before[0] == "Z":
                continue
            executable = process_executable(process)
            relative = executable.relative_to(cache)
            parts = relative.parts
            if len(parts) != 6 or not _VERSION.fullmatch(parts[0]) or parts[1:] != (
                    "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"):
                continue
            metadata = executable.stat()
            if metadata.st_uid != 0 or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH) or not (cache / parts[0] / ".ready").is_file():
                continue
            status = dict(line.split(":", 1) for line in (process / "status").read_text().splitlines() if ":" in line)
            if [int(value) for value in status["Uid"].split()][:2] != [1000, 1000]:
                continue
            rss = status["VmRSS"].split()
            after = (process / "stat").read_text().rsplit(")", 1)[1].split()
            # 同时核对启动时刻，避免 PID 复用把另外一个进程的 RSS 混进样本。
            if before[19] != after[19] or rss[1] != "kB" or not rss[0].isdecimal() or int(rss[0]) <= 0:
                continue
            samples.append((parts[0], int(rss[0]) * 1024))
        except (OSError, ValueError, IndexError, KeyError):
            continue
    return samples


def validate_process_metrics(value: dict, environment_id: str, version: str) -> dict:
    """核对跨进程/服务传递的实测指标，不填补未知数据。

    :param value: canonical_process 载荷。
    :param environment_id: 当前环境归属。
    :param version: 当前 CLI 版本。
    :return: 已校验的原载荷；无效值抛出 ValueError。
    """
    if not isinstance(value, dict) or not isinstance(value.get("observation"), dict):
        raise ValueError("进程指标缺少已确认来源")
    observed = value["observation"]
    limit = value.get("constrained_memory")
    count = observed.get("sample_count")
    if (observed.get("source") != PROCESS_SOURCE or observed.get("environment_id") != environment_id
            or not re.fullmatch(r"[a-f0-9]{32}", environment_id) or observed.get("cli_version") != version
            or not _VERSION.fullmatch(version) or type(limit) is not int or not 0 <= limit < 1 << 53
            or type(count) is not int or not 0 <= count < 1 << 53):
        raise ValueError("进程指标来源、版本或内存限制不匹配")
    observed_at = observed.get("observed_at")
    sampled_at = observed.get("sampled_at")
    rss = [observed.get(key) for key in ("rss_bytes", "rss_min_bytes", "rss_max_bytes")]
    if type(observed_at) not in (int, float) or not 0 < observed_at <= time.time() + 60:
        raise ValueError("进程指标观察时间无效")
    if count == 0:
        if sampled_at is not None or any(item is not None for item in rss):
            raise ValueError("未采集的 CLI 不能带有 RSS 数值")
    elif (type(sampled_at) not in (int, float) or not 0 < sampled_at <= observed_at
            or any(type(item) is not int or not 0 < item < 1 << 53 for item in rss)
            or not rss[1] <= rss[0] <= rss[2]):
        raise ValueError("CLI RSS 样本损坏")
    return value


def sample_process_metrics(root: Path = Path("/run/v3"), proc: Path = Path("/proc"),
                           cli: Path = Path("/cli"), cgroup: Path = Path("/sys/fs/cgroup")) -> dict:
    """在私有锁内更新有界观察文件，采样失败不覆盖旧证据。

    :param root: root 私有 runtime 目录。
    :param proc: 容器 procfs。
    :param cli: 官方 CLI 缓存。
    :param cgroup: 容器 cgroup。
    :return: 最新私有观察记录。
    """
    environment_id = json.loads((root / "sender.json").read_text())["binding"]["environment_id"]
    if not isinstance(environment_id, str) or not re.fullmatch(r"[a-f0-9]{32}", environment_id):
        raise ValueError("进程观察的环境归属无效")
    return merge_process_metrics(root, environment_id, memory_limit(cgroup), cli_processes(proc, cli))


def merge_process_metrics(root: Path, environment_id: str, limit: int, samples: list) -> dict:
    """将受控内核采样合并为管理端私有观察，保持原锁与持久格式。

    :param root: 不向 CLI 开放的管理端 runtime。
    :param environment_id: 管理端已核对的环境 ID。
    :param limit: CLI 实际 cgroup RAM 上限。
    :param samples: 只读采样器返回的版本和 RSS 二元组。
    :return: 原子持久化后的观察记录。
    """
    if not re.fullmatch(r"[a-f0-9]{32}", environment_id) or type(limit) is not int or not 0 <= limit < 1 << 53:
        raise ValueError("采样环境或内存限制无效")
    if not isinstance(samples, list) or any(not isinstance(item, (tuple, list)) or len(item) != 2
            or not isinstance(item[0], str) or not _VERSION.fullmatch(item[0])
            or type(item[1]) is not int or not 0 < item[1] < 1 << 53 for item in samples):
        raise ValueError("CLI 内核采样格式无效")
    path = root / "process-metrics.json"
    with (root / "process-metrics.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        value = {"schema": 1, "source": PROCESS_SOURCE, "environment_id": environment_id, "versions": {}}
        if path.exists():
            if path.is_symlink():
                raise ValueError("进程观察文件不能是链接")
            value = json.loads(path.read_text())
            if (not isinstance(value, dict) or value.get("schema") != 1 or value.get("source") != PROCESS_SOURCE
                    or value.get("environment_id") != environment_id or not isinstance(value.get("versions"), dict)
                    or len(value["versions"]) > 32):
                raise ValueError("进程观察文件损坏或归属冲突")
        now = time.time()
        for version, sample in value["versions"].items():
            validate_process_metrics({"constrained_memory": limit, "observation": {
                "source": PROCESS_SOURCE, "environment_id": environment_id, "cli_version": version,
                "observed_at": now, **sample}}, environment_id, version)
        for version, rss in samples:
            previous = value["versions"].get(version, {})
            value["versions"][version] = {"sampled_at": now, "sample_count": previous.get("sample_count", 0) + 1,
                "rss_bytes": rss, "rss_min_bytes": min(previous.get("rss_min_bytes", rss), rss),
                "rss_max_bytes": max(previous.get("rss_max_bytes", rss), rss)}
        if len(value["versions"]) > 32:
            oldest = min(value["versions"], key=lambda version: value["versions"][version]["sampled_at"])
            del value["versions"][oldest]
        value.update(observed_at=now, constrained_memory=limit)
        descriptor, name = tempfile.mkstemp(prefix="process-metrics.", dir=root)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w") as output:
                os.chmod(temporary, 0o600)
                json.dump(value, output, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return value


def main() -> None:
    """导出当前版本可用的真实指标；不启动 CLI。

    :return: None；标准输出仅包含指标 JSON。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("read",))
    parser.add_argument("version")
    args = parser.parse_args()
    if not _VERSION.fullmatch(args.version):
        raise ValueError("CLI 版本格式无效")
    value = sample_process_metrics()
    sample = value["versions"].get(args.version, {"sample_count": 0, "sampled_at": None,
        "rss_bytes": None, "rss_min_bytes": None, "rss_max_bytes": None})
    result = {"constrained_memory": value["constrained_memory"], "observation": {
        "source": PROCESS_SOURCE, "environment_id": value["environment_id"], "cli_version": args.version,
        "observed_at": value["observed_at"], **sample}}
    validate_process_metrics(result, value["environment_id"], args.version)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
