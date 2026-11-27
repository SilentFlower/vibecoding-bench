#!/usr/local/bin/python3
"""用四个已构建镜像的内置制品验收 V2 排空，所有角色共享仅回环网络。"""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import signal
from socket import if_nameindex
from subprocess import PIPE, Popen, TimeoutExpired, run
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path("/checkout/deploy/flower2api/verify_tui_mixed_images.py")
CONTROL = "/app/claude-code-gateway"
ACCOUNT = "/usr/local/bin/account-sender"
ROLES = {"old-control": CONTROL, "old-account": ACCOUNT, "new-control": CONTROL, "new-account": ACCOUNT}
STATE = Path("/lab")


def require_isolated_container():
    """核验角色使用本次仅回环网络。@return 无。"""
    if not Path("/.dockerenv").exists() or {name for _, name in if_nameindex()} != {"lo"}:
        raise RuntimeError("镜像角色须使用仅回环容器")


def wait_file(path):
    """等待同一夹具对端发布状态。@param path 私有状态文件。@return 完整记录。"""
    deadline = monotonic() + 120
    while monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text())
        sleep(0.05)
    raise RuntimeError(f"镜像角色未完成交接 {path.parent.name}/{path.name}")


def publish(path, value):
    """原子发布夹具进程信息。@param path 私有状态路径。@param value JSON 记录。@return 无。"""
    staged = path.with_suffix(".tmp")
    staged.write_text(json.dumps(value))
    staged.replace(path)


def proxy(role):
    """将夹具的本地进程调用交给指定镜像。@param role 固定角色。@return 真实进程退出状态。"""
    require_isolated_container()
    state = STATE / "peers" / role
    signal.signal(signal.SIGTERM, lambda *_: (state / "stop").touch())
    publish(state / "start.json", {"environment": dict(os.environ), "cwd": os.getcwd()})
    return wait_file(state / "exit.json")


def peer(role):
    """在角色镜像内启动其固定入口。@param role 固定角色。@return 该进程状态。"""
    require_isolated_container()
    state = STATE / "peers" / role
    launch = wait_file(state / "start.json")
    folder = Path(launch["cwd"])
    # 控制端须在共享的本次数据库目录中启动，账号端使用镜像原工作目录。
    workdir = folder if ROLES[role] == CONTROL and folder.is_relative_to(STATE) else None
    status = 1
    try:
        with Popen([ROLES[role]], cwd=workdir, env=launch["environment"]) as process:
            while process.poll() is None:
                if (state / "stop").exists():
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except TimeoutExpired:
                        process.kill()
                        process.wait()
                    break
                sleep(0.05)
            status = process.returncode
    finally:
        publish(state / "exit.json", status)
    return status


def check_package(image, role):
    """核对已安装的额外 CA 验证镜像。@param image 镜像引用。@param role control 或 account。@return 镜像身份。"""
    raw = run(["docker", "image", "inspect", image], check=True, text=True, stdout=PIPE).stdout
    (inspection,) = json.loads(raw)
    labels = inspection["Config"].get("Labels") or {}
    revision = labels.get("org.opencontainers.image.revision", "")
    if (labels.get("vibebench.role") != role or labels.get("vibebench.verification") != "extra-ca"
            or not re.fullmatch(r"[0-9a-f]{40}", revision)):
        raise ValueError(f"需要同批带隔离验证 CA 的 {role} 镜像")
    return {"id": inspection["Id"], "revision": revision}


def verify_images(images, cli, *, context_keep_all=None):
    """用已安装的旧、新制品各启动一套实际角色。@param images 固定角色镜像。@param cli 固定 CLI 卷。
    @param context_keep_all 可选，测试显式保留全部思考的模型。@return 脱敏证据。
    """
    identities = {role: check_package(image, role.split("-", 1)[1]) for role, image in images.items()}
    old, new = (identities[role]["revision"] for role in ("old-control", "new-control"))
    if old == new or old != identities["old-account"]["revision"] or new != identities["new-account"]["revision"]:
        raise ValueError("需要不同批次及各自同批的控制端与账号镜像")
    with TemporaryDirectory(prefix="tui-mixed-images-") as directory, ExitStack() as stack:
        root = Path(directory)
        root.chmod(0o755)
        for path in ("run", "native", "flows", "bin", "peers"):
            (root / path).mkdir(mode=0o700 if path in {"native", "flows"} else 0o755)
        for role in images:
            private = root / "peers" / role
            private.mkdir(mode=0o700)
            if ROLES[role] == ACCOUNT:
                os.chown(private, 1001, 1001)
            (root / "bin" / role).symlink_to(SCRIPT)
        mounts = ["-v", f"{ROOT}:/checkout:ro", "-v", f"{root}:/lab",
                  "-v", f"{root / 'run'}:/run/v3", "-v", f"{root / 'native'}:/native",
                  "-v", f"{root / 'flows'}:/flows/api", "-v", f"{cli}:/cli:ro"]
        containers = []

        def start(network, image, entrypoint, args, user):
            command = ["docker", "run", "--detach", "--pull", "never", "--init", "--network", network,
                       "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777", "--user", user, *mounts,
                       "--entrypoint", entrypoint, image, *args]
            identifier = run(command, check=True, text=True, stdout=PIPE).stdout.strip()
            containers.append(identifier)
            stack.callback(run, ["docker", "rm", "-f", identifier], stdout=PIPE, stderr=PIPE)
            return identifier

        anchor = start("none", identities["new-account"]["id"], "sleep", ["infinity"], "0:0")
        for role, identity in identities.items():
            start("container:" + anchor, identity["id"], "/usr/local/bin/python3", ["-I", str(SCRIPT), "--peer", role],
                  "1001:1001" if ROLES[role] == ACCOUNT else "0:0")
        command = ["docker", "exec", anchor, "python3", "-B", "/checkout/deploy/flower2api/verify_tui_cold_history.py",
                   "--shared-state", str(STATE), "--gateway", "/lab/bin/new-control", "--sender", "/lab/bin/new-account",
                   "--mixed-image-peers", "/lab/bin/old-control", "/lab/bin/old-account"]
        if context_keep_all:
            command.extend(["--mixed-context-keep-all", context_keep_all])
        result = run(command, text=True, stdout=PIPE)
        if result.returncode:
            for identifier in containers[1:]:
                run(["docker", "logs", identifier], stdout=sys.stderr, check=False)
            result.check_returncode()
        proof = json.loads(result.stdout.splitlines()[-1])
        return {**proof, "installed_images": identities}


def main():
    """读入两个发行的本地验证制品。@return 进程状态。"""
    if Path(sys.argv[0]).name in ROLES:
        return proxy(Path(sys.argv[0]).name)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer", choices=ROLES, help=argparse.SUPPRESS)
    for role in ROLES:
        parser.add_argument("--" + role)
    parser.add_argument("--cli", type=Path)
    parser.add_argument("--mixed-context-keep-all", choices=("claude-sonnet-4-6", "claude-opus-5-5"))
    args = parser.parse_args()
    if args.peer:
        return peer(args.peer)
    images = {role: getattr(args, role.replace("-", "_")) for role in ROLES}
    if not all(images.values()) or args.cli is None:
        parser.error("须同时提供两个发行的四个镜像和固定 CLI 目录")
    print(json.dumps(verify_images(images, args.cli.resolve(strict=True), context_keep_all=args.mixed_context_keep_all),
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
