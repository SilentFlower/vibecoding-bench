#!/usr/bin/env python3
"""v3 两镜像的联合构建、冲突检查及受限启停入口。"""
import argparse
import hashlib
import gzip
import shutil
import tempfile
import tarfile
import json
import os
import re
import shlex
import socket
import sqlite3
import subprocess
import sys
import uuid
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[2]
COMPOSE = Path(__file__).with_name("compose.yml")
# 独立部署脚本复用镜像内的纯预算模块，避免预检和容器解释不同单位。
sys.path.insert(0, str(REPO / "orchestrator"))
from resource_budget import account_limits


def command(*arguments: str, capture: bool = False, environment=None) -> str:
    """以 argv 执行命令，秘密不写入命令行或输出。

    :param arguments: 完整 argv
    :param capture: 是否捕获 stdout
    :param environment: 进程环境
    :return: 捕获内容或空字符串
    """
    result = subprocess.run(arguments, cwd=REPO, env=environment, check=True,
        stdout=subprocess.PIPE if capture else None, text=True)
    return result.stdout or ""


def load_environment(path: Path) -> dict:
    """读取受限 .env 格式，拒绝 shell 语法与重复键。

    :param path: 配置文件
    :return: 配置值；不执行配置内容
    """
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, raw = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"V3_[A-Z0-9_]+", key) or key in values:
            raise ValueError("配置包含未知格式或重复键")
        parts = shlex.split(raw, comments=False)
        if len(parts) > 1:
            raise ValueError("配置值含空格时需要加引号")
        values[key] = parts[0] if parts else ""
    return values


def inspect_images(values: dict) -> dict:
    """检查两个角色镜像与联合版本清单完全一致。

    :param values: 部署配置
    :return: 版本清单
    """
    manifest = json.loads(Path(values["V3_RELEASE_MANIFEST"]).read_text())
    if manifest.get("schema") != 3:
        raise ValueError("版本清单格式不匹配")
    if values.get("V3_RELEASE", manifest["release"]) != manifest["release"]:
        raise ValueError("配置批次与清单不一致")
    values["V3_RELEASE"] = manifest["release"]
    for role in ("control", "account"):
        name = values[f"V3_{role.upper()}_IMAGE"]
        if name.endswith(":latest") or ":v3-" not in name:
            raise ValueError("必须使用独立 v3 批次标签，禁止 latest")
        info = json.loads(command("docker", "image", "inspect", name, capture=True))[0]
        entry = manifest["images"][role]
        labels = info["Config"]["Labels"] or {}
        if entry["reference"] != name or not _image_matches(info, entry):
            raise ValueError("镜像 digest 与清单不匹配")
        if entry.get("platform") and entry["platform"] != info.get("Os", "") + "/" + info.get("Architecture", ""):
            raise ValueError("镜像平台与清单不匹配")
        if labels.get("vibebench.product") != "v3" or labels.get("vibebench.role") != role:
            raise ValueError("镜像产品或角色不匹配")
        for label, key in (("release", "release"), ("parent-revision", "parent_revision"), ("gateway-revision", "gateway_revision")):
            if labels.get("vibebench." + label) != manifest[key]:
                raise ValueError("镜像构建批次不匹配")
    return manifest


def preflight(values: dict) -> Path:
    """拒绝旧资源重叠、端口占用和不匹配版本。

    :param values: 部署配置
    :return: 独立数据根的规范路径
    """
    deployment = values["V3_DEPLOYMENT_ID"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", deployment):
        raise ValueError("部署标识不合法")
    for key in ("V3_INTERNAL_TOKEN", "V3_SESSION_SECRET", "V3_ADMIN_PASSWORD"):
        if len(values.get(key, "")) < 32:
            raise ValueError(f"{key} 至少需要 32 字符")
    supplied = Path(values["V3_DATA_ROOT"])
    root = supplied.resolve()
    if not supplied.is_absolute() or root in (Path("/"), Path("/srv"), REPO) or "v3" not in root.name:
        raise ValueError("请使用独立且名称含 v3 的绝对数据目录")
    ids = command("docker", "ps", "-aq", capture=True).split()
    containers = json.loads(command("docker", "inspect", *ids, capture=True)) if ids else []
    port = int(values.get("V3_HOST_PORT", "18080"))
    address = values.get("V3_BIND_ADDRESS", "127.0.0.1")
    for container in containers:
        labels = container["Config"].get("Labels") or {}
        own = labels.get("vibebench.product") == "v3" and labels.get("vibebench.deployment") == deployment
        for mount in container.get("Mounts", []):
            source = Path(mount["Source"]).resolve()
            if not own and (source == root or source in root.parents or root in source.parents):
                raise ValueError("数据挂载与其它部署重叠")
        name = container["Name"].lstrip("/")
        account_prefix = "v3-" + hashlib.sha256(deployment.encode()).hexdigest()[:12] + "-account-"
        if (name.startswith(f"vibebench-v3-{deployment}-") or name.startswith(account_prefix)) and not own:
            raise ValueError("容器名称被其它部署占用")
        for bindings in (container.get("HostConfig", {}).get("PortBindings") or {}).values():
            for binding in bindings or []:
                if int(binding.get("HostPort") or 0) == port and binding.get("HostIp", "") in ("", "0.0.0.0", "::", address):
                    raise ValueError("宿主端口已被容器发布，拒绝启动")
    network_name = f"vibebench-v3-{deployment}"
    networks = [json.loads(line) for line in command("docker", "network", "ls", "--format", "{{json .}}", capture=True).splitlines()]
    for network in networks:
        if network["Name"] == network_name:
            info = json.loads(command("docker", "network", "inspect", network_name, capture=True))[0]
            labels = info.get("Labels") or {}
            if labels.get("vibebench.product") != "v3" or labels.get("vibebench.deployment") != deployment:
                raise ValueError("网络名称被其它部署占用")
    # up 仅在端口空闲时执行；已运行实例使用 status 检查，避免掩盖配置漂移。
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((address, port))
    inspect_images(values)
    marker = root / ".v3-deployment.json"
    if marker.exists():
        if json.loads(marker.read_text()).get("deployment") != deployment:
            raise ValueError("数据目录属于其它部署")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("非空数据目录缺少 v3 归属标记，拒绝接管")
    memory = {line.split(":", 1)[0]: int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith(("MemAvailable:", "SwapFree:"))}
    active_limit = int(values.get("V3_MAX_ACTIVE_ACCOUNTS", "1"))
    account_memory, total_memory = account_limits(values.get("V3_ACCOUNT_MEMORY", "4g"), values.get("V3_ACCOUNT_SWAP", "0"))
    database = root / "bench/db.sqlite"
    if database.is_file():
        if not database.resolve().is_relative_to(root):
            raise ValueError("数据库路径不属于本部署")
        with sqlite3.connect("file:" + quote(str(database), safe="/") + "?mode=ro", uri=True) as connection:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='account_environments'").fetchone():
                # 已有账号保留首次限额；下调全局配置不能让预检低估下一次唤醒的额度。
                for saved, in connection.execute("SELECT fingerprint_json FROM account_environments"):
                    fingerprint = json.loads(saved)
                    ram, combined = account_limits(fingerprint["mem"], fingerprint.get("swap", "0"))
                    if ram > account_memory or combined - ram > total_memory - account_memory:
                        raise ValueError("已有账号固化预算超过当前配置，请提高部署预算后再启动")
    if active_limit < 1 or float(values.get("V3_ACCOUNT_CPUS", "2")) <= 0:
        raise ValueError("账号 CPU、内存或活跃环境预算无效")
    # 余量独立于 swap；默认 4g 仍要求 5g，显式的小预算不再被固定 5g 挡住。
    minimum = max(int(values.get("V3_MIN_FREE_MEMORY_BYTES", "0")), active_limit * account_memory + 1024**3)
    if memory.get("MemAvailable", 0) < minimum:
        raise ValueError("宿主可用内存不足，拒绝启动")
    swap = total_memory - account_memory
    if swap:
        if memory.get("SwapFree", 0) < active_limit * swap:
            raise ValueError("宿主空闲 swap 不足，拒绝启动")
        if json.loads(command("docker", "info", "--format", "{{json .SwapLimit}}", capture=True)) is not True:
            raise ValueError("Docker 不支持 swap 限额，拒绝启动")
    return root


def build(release: str, manifest_path: Path) -> None:
    """构建两个最终镜像，完成后生成可核对的联合清单。

    :param release: 仅用于 v3 的唯一批次名
    :param manifest_path: 新清单路径
    :return: None
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", release):
        raise ValueError("批次名不合法")
    parent = command("git", "rev-parse", "HEAD", capture=True).strip()
    gateway = command("git", "-C", "cc2api", "rev-parse", "HEAD", capture=True).strip()
    dirty = bool(command("git", "status", "--porcelain", capture=True).strip())
    if manifest_path.exists():
        raise ValueError("版本清单已经存在，禁止覆盖批次")
    with tempfile.TemporaryDirectory(prefix="vibebench-v3-source-") as temporary:
        snapshot = Path(temporary)
        folders = ("cc2api/src", "cc2api/vendor", "cc2api/craftls", "cc2api/web", "images/account",
            "images/sidecar", "images/worker", "images/v3", "orchestrator", "webui")
        ignored = shutil.ignore_patterns(".git", "target", "node_modules", "__pycache__", ".env", ".env.*", "*.log")
        for relative in folders:
            shutil.copytree(REPO / relative, snapshot / relative, ignore=ignored)
        for relative in ("cc2api/Cargo.toml", "cc2api/Cargo.lock", "topics.md"):
            (snapshot / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, snapshot / relative)
        digest = hashlib.sha256()
        for path in sorted(item for item in snapshot.rglob("*") if item.is_file()):
            digest.update(str(path.relative_to(snapshot)).encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        source_hash = digest.hexdigest()
        images = {}
        for role in ("control", "account"):
            reference = f"vibebench-v3-{role}:v3-{release}"
            if subprocess.run(["docker", "image", "inspect", reference], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                raise ValueError("批次镜像标签已经存在，禁止覆盖")
            command("docker", "build", "-f", str(snapshot / "images/v3/Dockerfile"), "--target", role,
                "--build-arg", f"V3_RELEASE={release}", "--build-arg", f"V3_PARENT_REV={parent}",
                "--build-arg", f"V3_GATEWAY_REV={gateway}", "-t", reference, str(snapshot))
            info = json.loads(command("docker", "image", "inspect", reference, capture=True))[0]
            images[role] = {"reference": reference, "digest": info["Id"],
                "config_digest": _image_config_digest(reference),
                "platform": info["Os"] + "/" + info["Architecture"]}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("x") as output:
        json.dump({"schema": 3, "bridge_protocol": 1, "layout_version": 1, "default_cli_version": "2.1.280",
            "release": release, "parent_revision": parent, "gateway_revision": gateway,
            "dirty_worktree": dirty, "source_content_sha256": source_hash, "images": images}, output, indent=2)
        output.write("\n")


def _manifest_values(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    return {"V3_RELEASE_MANIFEST": str(manifest_path),
        **{f"V3_{role.upper()}_IMAGE": manifest["images"][role]["reference"] for role in ("control", "account")}}


def _write_new_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        # link 以独占方式发布完整文件；不能用 replace 覆盖另一个已完成批次。
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_config_digest(reference: str) -> str:
    # containerd 的 Id 可以是 OCI 索引；归档中的原始 config 字节才有跨 daemon 的稳定哈希。
    process = subprocess.Popen(["docker", "save", reference], cwd=REPO, stdout=subprocess.PIPE)
    configs, manifests = {}, []
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for item in archive:
                if not item.isfile() or item.size > 4 * 1024**2:
                    continue
                if item.name == "manifest.json":
                    manifests = json.load(archive.extractfile(item))
                elif item.name.endswith(".json") or item.name.startswith("blobs/sha256/"):
                    payload = archive.extractfile(item).read()
                    try:
                        value = json.loads(payload)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if isinstance(value, dict) and isinstance(value.get("rootfs"), dict) and "architecture" in value:
                        configs[item.name] = "sha256:" + hashlib.sha256(payload).hexdigest()
        if process.wait() != 0:
            raise ValueError("镜像配置归档导出失败")
        entries = [item for item in manifests if reference in (item.get("RepoTags") or [])]
        if len(entries) != 1 or entries[0].get("Config") not in configs:
            raise ValueError("无法从镜像归档核对唯一的原始配置")
        return configs[entries[0]["Config"]]
    except tarfile.TarError as error:
        raise ValueError("镜像配置归档格式不匹配") from error
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def _image_matches(info: dict, entry: dict) -> bool:
    if info["Id"] == entry["digest"]:
        return True
    config = entry.get("config_digest")
    if not config or not re.fullmatch(r"sha256:[0-9a-f]{64}", config):
        return False
    # classic store 用 config ID，containerd 可用 OCI 索引 ID；两者均由发布清单固定。
    registry = entry.get("registry_digest")
    return info["Id"] == config or bool(registry and (
        info["Id"] == registry or (info.get("Descriptor") or {}).get("digest") == registry))


def _check_local_reference(reference: str, expected: dict) -> None:
    result = subprocess.run(["docker", "image", "inspect", reference], cwd=REPO,
        capture_output=True, text=True, check=False)
    if result.returncode == 0:
        if not _image_matches(json.loads(result.stdout)[0], expected):
            raise ValueError("本地批次标签指向其它镜像，拒绝覆盖")
    elif "No such image" not in result.stderr:
        raise ValueError("无法核对本地镜像，拒绝继续")


def publish(manifest_path: Path, output_path: Path, bundle_path: Path,
            namespace: str = "ghcr.io/silentflower") -> dict:
    """将当前 v3 Action 的同批镜像发布到 GHCR，最后才生成完整交付清单。

    :param manifest_path: 已完成构建的本地清单
    :param output_path: 全新发布清单路径
    :param bundle_path: 全新同批镜像包路径
    :param namespace: 当前 Action 仓库 owner 的 GHCR namespace
    :return: 已发布的联合清单；失败保留发布标记，必须使用新 attempt 重跑
    """
    manifest = json.loads(manifest_path.read_text())
    expected_release = "ci-" + os.environ.get("GITHUB_RUN_ID", "") + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "").lower()
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/v3"
            or not re.fullmatch(r"ci-[1-9][0-9]*-[1-9][0-9]*", expected_release)
            or manifest.get("release") != expected_release
            or manifest.get("parent_revision") != os.environ.get("GITHUB_SHA")
            or os.environ.get("GITHUB_REPOSITORY", "").lower() != owner + "/vibecoding-bench"
            or namespace != "ghcr.io/" + owner or not re.fullmatch(r"ghcr.io/[a-z0-9][a-z0-9-]*", namespace)):
        raise ValueError("发布必须使用当前 v3 Action 的仓库、提交与唯一 run/attempt 批次")
    if manifest.get("dirty_worktree") is not False:
        raise ValueError("不能发布含未提交修改或来源未知的批次")
    paths = [manifest_path.resolve(), output_path.resolve(), bundle_path.resolve()]
    if len(set(paths)) != 3 or output_path.exists() or bundle_path.exists():
        raise ValueError("发布清单和镜像包必须使用全新独立路径")
    started = output_path.with_name(output_path.name + ".started")
    if started.exists():
        raise ValueError("本批次已经开始发布，请使用新的 Action attempt 重跑")
    inspect_images(_manifest_values(manifest_path))
    references = {role: f"{namespace}/vibebench-v3-{role}:v3-{manifest['release']}" for role in ("control", "account")}
    for role, reference in references.items():
        _check_local_reference(reference, manifest["images"][role])
    # GitHub 重跑增加 attempt；本次标记防止进程重试复用同批标签覆盖部分发布。
    _write_new_json(started,
        {"release": manifest["release"], "parent_revision": manifest["parent_revision"]})
    published = {**manifest, "images": {}}
    for role, reference in references.items():
        entry = manifest["images"][role]
        command("docker", "tag", entry["reference"], reference)
        command("docker", "push", reference)
        info = json.loads(command("docker", "image", "inspect", reference, capture=True))[0]
        repository = reference.rsplit(":", 1)[0]
        digests = {value[len(repository) + 1:] for value in info.get("RepoDigests", [])
            if value.startswith(repository + "@")}
        if info["Id"] != entry["digest"] or len(digests) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", next(iter(digests), "")):
            raise ValueError("推送后镜像配置 ID 或仓库 digest 无法核对")
        config_digest = entry.get("config_digest") or _image_config_digest(entry["reference"])
        published["images"][role] = {**entry, "reference": reference,
            "config_digest": config_digest, "registry_digest": next(iter(digests))}
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=bundle_path.name + ".", dir=bundle_path.parent)
    process = None
    try:
        with os.fdopen(descriptor, "wb") as output:
            process = subprocess.Popen(["docker", "save", *references.values()], cwd=REPO, stdout=subprocess.PIPE)
            try:
                with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as archive:
                    shutil.copyfileobj(process.stdout, archive, length=1024 * 1024)
                if process.wait() != 0:
                    raise ValueError("同批镜像包生成失败")
                output.flush()
                os.fsync(output.fileno())
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        os.link(temporary, bundle_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    published["bundle"] = {"name": bundle_path.name, "sha256": _file_sha256(bundle_path), "size": bundle_path.stat().st_size}
    _write_new_json(output_path, published)
    return published


def _published_manifest(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != 3 or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", manifest.get("release", "")):
        raise ValueError("发布清单格式或批次不匹配")
    for role in ("control", "account"):
        entry = manifest["images"][role]
        reference = entry["reference"]
        if not re.fullmatch(r"ghcr.io/[a-z0-9][a-z0-9-]*/vibebench-v3-" + role + ":v3-" + re.escape(manifest["release"]), reference):
            raise ValueError("发布镜像引用不属于指定 v3 角色和批次")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry.get("registry_digest", "")):
            raise ValueError("发布清单缺少有效仓库 digest")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry.get("digest", "")):
            raise ValueError("发布清单缺少有效本地镜像 ID")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry.get("config_digest", "")):
            raise ValueError("发布清单缺少有效原始配置 digest")
    return manifest


def pull(manifest_path: Path) -> None:
    """按仓库 digest 下载两镜像，核对后建立受控批次标签。

    :param manifest_path: 完整的发布清单
    :return: None；认证、下载或身份核对失败时停止
    """
    manifest = _published_manifest(manifest_path)
    for role in ("control", "account"):
        entry = manifest["images"][role]
        reference = entry["reference"]
        _check_local_reference(reference, entry)
    for role in ("control", "account"):
        entry = manifest["images"][role]
        pinned = entry["reference"].rsplit(":", 1)[0] + "@" + entry["registry_digest"]
        command("docker", "pull", pinned)
        info = json.loads(command("docker", "image", "inspect", pinned, capture=True))[0]
        if not _image_matches(info, entry):
            raise ValueError("下载镜像配置 ID 与发布清单不匹配")
        command("docker", "tag", pinned, entry["reference"])
    inspect_images(_manifest_values(manifest_path))


def load_bundle(manifest_path: Path, bundle_path: Path) -> None:
    """验证同批包的 SHA256 后加载，不需要服务器保存仓库凭据。

    :param manifest_path: 完整发布清单
    :param bundle_path: 与清单匹配的压缩镜像包
    :return: None；包或镜像身份不符时停止
    """
    manifest = _published_manifest(manifest_path)
    bundle = manifest.get("bundle") or {}
    if (bundle.get("name") != bundle_path.name or bundle.get("size") != bundle_path.stat().st_size
            or not re.fullmatch(r"[0-9a-f]{64}", bundle.get("sha256", ""))
            or _file_sha256(bundle_path) != bundle["sha256"]):
        raise ValueError("同批镜像包名称、大小或 SHA256 不匹配")
    for role in ("control", "account"):
        entry = manifest["images"][role]
        _check_local_reference(entry["reference"], entry)
    command("docker", "load", "--input", str(bundle_path))
    inspect_images(_manifest_values(manifest_path))


def _owned_root(values: dict, stopped: bool = False) -> Path:
    deployment = values["V3_DEPLOYMENT_ID"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", deployment):
        raise ValueError("部署标识不合法")
    configured = Path(values["V3_DATA_ROOT"])
    root = configured.resolve()
    if not configured.is_absolute() or configured != root:
        raise ValueError("数据根必须为非链接的绝对路径")
    marker = root / ".v3-deployment.json"
    if not marker.is_file() or json.loads(marker.read_text()).get("deployment") != deployment:
        raise ValueError("数据目录归属不匹配")
    if stopped and command("docker", "ps", "-q", "--filter", "label=vibebench.product=v3",
            "--filter", f"label=vibebench.deployment={deployment}", capture=True).strip():
        raise ValueError("请先 stop 本部署")
    return root


def status(values: dict) -> dict:
    """展示本部署全部容器、账号占用和实际镜像 ID，不输出服务秘密。

    :param values: 当前部署配置
    :return: 只读状态摘要，同时以 JSON 打印
    """
    manifest = inspect_images(values)
    root = _owned_root(values)
    ids = command("docker", "ps", "-aq", "--filter", "label=vibebench.product=v3",
        "--filter", f"label=vibebench.deployment={values['V3_DEPLOYMENT_ID']}", capture=True).split()
    inspected = json.loads(command("docker", "inspect", *ids, capture=True)) if ids else []
    containers = []
    for item in inspected:
        labels = item["Config"].get("Labels") or {}
        if labels.get("vibebench.product") != "v3" or labels.get("vibebench.deployment") != values["V3_DEPLOYMENT_ID"]:
            continue
        role = labels.get("vibebench.role", "unknown")
        expected = manifest["images"]["account" if role == "account" else "control"]
        containers.append({"id": item["Id"], "name": item["Name"].lstrip("/"), "role": role,
            "environment_id": labels.get("vibebench.environment"), "status": item["State"]["Status"],
            "image_digest": item["Image"], "matches_release": _image_matches({"Id": item["Image"]}, expected)})
    environments = []
    database = root / "bench/db.sqlite"
    if database.is_file():
        if not database.resolve().is_relative_to(root):
            raise ValueError("数据库路径不属于本部署")
        with sqlite3.connect("file:" + quote(str(database), safe="/") + "?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='account_environments'").fetchone():
                environments = [dict(row) for row in connection.execute("SELECT e.environment_id,e.name,e.account_id,e.generation,e.container_id,e.state,a.cc2api_account_id FROM account_environments e LEFT JOIN accounts a ON a.id=e.account_id ORDER BY e.name")]
    host = values.get("V3_BIND_ADDRESS", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    for environment in environments:
        container = next((item for item in containers if item["id"] == environment["container_id"]), None)
        environment["container_status"] = container["status"] if container else "missing"
        environment["image_digest"] = container["image_digest"] if container else None
        environment["occupancy"] = {"active": None, "waiting": None, "lease": None, "available": False}
        account_id = environment.pop("cc2api_account_id")
        if account_id is not None:
            request = urllib.request.Request(f"http://{host}:{values.get('V3_HOST_PORT', '18080')}/admin/runtime/accounts/{int(account_id)}/lease",
                headers={"Authorization": "Bearer " + values["V3_ADMIN_PASSWORD"]})
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(request, timeout=2) as response:
                    snapshot = json.loads(response.read(65536))
                lease = snapshot.get("lease")
                environment["occupancy"] = {"active": snapshot["active"], "waiting": snapshot.get("waiting", 0),
                    "lease": {key: lease.get(key) for key in ("owner", "generation", "phase", "expires_at")} if lease else None, "available": True}
            except (OSError, ValueError, KeyError):
                pass
        else:
            environment["occupancy"] = {"active": 0, "waiting": 0, "lease": None, "available": True}
        if re.fullmatch(r"[a-f0-9]{32}", environment["environment_id"]):
            execution = root / "bench/environments" / environment["environment_id"] / "runtime/execution.json"
            if execution.is_file() and execution.resolve().is_relative_to(root):
                proof = json.loads(execution.read_text())
                environment["execution"] = {key: proof.get(key) for key in ("source", "phase")}
    result = {"deployment": values["V3_DEPLOYMENT_ID"], "release": manifest["release"],
        "images": manifest["images"], "containers": containers, "environments": environments}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def import_offline(values: dict, source: Path, apply: bool = False) -> dict:
    """在停机的独立 v3 库导入白名单历史元数据，默认只演练并回滚。

    :param values: 当前部署配置
    :param source: 去凭据 JSON；不接收代理、profile、正文、AT 或 RT
    :param apply: 显式保存元数据；所有账号保持停用且不建立上游绑定
    :return: 创建与幂等跳过数量，不包含来源记录正文
    """
    root = _owned_root(values, stopped=True)
    if source.stat().st_size > 1024 * 1024:
        raise ValueError("离线资料超过大小上限")
    payload = json.loads(source.read_text())
    if not isinstance(payload, dict) or set(payload) != {"schema", "source_id", "accounts", "tasks", "runs"} or type(payload["schema"]) is not int or payload["schema"] != 1:
        raise ValueError("离线资料格式不匹配")
    source_id = payload["source_id"]
    if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", source_id):
        raise ValueError("离线来源标识无效")
    contracts = {"accounts": ({"legacy_id", "name"}, {"enabled", "deleted"}),
        "tasks": ({"legacy_id", "account_legacy_id", "topic_no", "title"}, set()),
        "runs": ({"id", "task_legacy_id", "account_legacy_id", "status"}, set())}
    for kind, (required, optional) in contracts.items():
        records = payload[kind]
        if not isinstance(records, list):
            raise ValueError("离线记录必须为列表")
        identifiers = set()
        for record in records:
            if not isinstance(record, dict) or not required <= set(record) or set(record) - required - optional:
                raise ValueError("离线记录包含未允许字段；凭据、代理和正文不能导入")
            for key, value in record.items():
                if key in ("legacy_id", "id", "name", "task_legacy_id", "account_legacy_id"):
                    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
                        raise ValueError("离线记录标识无效")
                elif key in ("enabled", "deleted") and type(value) is not bool:
                    raise ValueError("离线启停状态必须为布尔值")
                elif key == "topic_no" and (type(value) is not int or value < 1):
                    raise ValueError("离线题号必须为正整数")
                elif key == "title" and (not isinstance(value, str) or len(value) > 500):
                    raise ValueError("离线标题无效")
                elif key == "status" and value not in ("done", "failed", "stopped", "queued", "running", "stopping", "quota_wait"):
                    raise ValueError("离线运行状态无效")
            identifier = record["id" if kind == "runs" else "legacy_id"]
            if identifier in identifiers:
                raise ValueError("离线记录标识重复")
            identifiers.add(identifier)
    database = root / "bench/db.sqlite"
    if not database.is_file() or not database.resolve().is_relative_to(root):
        raise ValueError("请先初始化并停止本部署，数据库必须属于 v3")
    counts = {"created": 0, "skipped": 0, "dry_run": not apply}
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    mapping = {}
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS v3_offline_imports(source_id TEXT,kind TEXT,legacy_id TEXT,digest TEXT NOT NULL,target_id TEXT NOT NULL,PRIMARY KEY(source_id,kind,legacy_id))")
        for kind in contracts:
            for record in payload[kind]:
                legacy_id = record["id" if kind == "runs" else "legacy_id"]
                digest = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                existing = connection.execute("SELECT digest,target_id FROM v3_offline_imports WHERE source_id=? AND kind=? AND legacy_id=?", (source_id, kind, legacy_id)).fetchone()
                if existing:
                    if existing["digest"] != digest:
                        raise ValueError("离线记录已导入但内容改变，拒绝覆盖")
                    target_id = existing["target_id"]
                    counts["skipped"] += 1
                elif kind == "accounts":
                    if connection.execute("SELECT 1 FROM accounts WHERE name=?", (record["name"],)).fetchone():
                        raise ValueError("账号名已存在且不属于本次离线来源，拒绝接管")
                    cursor = connection.execute("INSERT INTO accounts(name,profile_path,enabled,warmup_enabled,deleted_at) VALUES(?,?,0,0,?)",
                        (record["name"], "/data/profiles/" + record["name"], time.time() if record.get("deleted") else None))
                    target_id = str(cursor.lastrowid)
                    counts["created"] += 1
                elif kind == "tasks":
                    account_id = mapping.get(("accounts", record["account_legacy_id"]))
                    if not account_id:
                        raise ValueError("历史任务缺少本来源账号")
                    cursor = connection.execute("INSERT INTO tasks(topic_no,title,prompt,account_id,status,deleted_at) VALUES(?,?,'',?,'archived',?)",
                        (record["topic_no"], record["title"], int(account_id), time.time()))
                    target_id = str(cursor.lastrowid)
                    counts["created"] += 1
                else:
                    account_id = mapping.get(("accounts", record["account_legacy_id"]))
                    task_id = mapping.get(("tasks", record["task_legacy_id"]))
                    if not account_id or not task_id:
                        raise ValueError("历史运行缺少本来源任务或账号")
                    task_account = connection.execute("SELECT account_id FROM tasks WHERE id=?", (int(task_id),)).fetchone()
                    if task_account["account_id"] != int(account_id):
                        raise ValueError("历史任务与运行账号归属不一致")
                    run_status = record["status"] if record["status"] in ("done", "failed", "stopped") else "stopped"
                    connection.execute("INSERT INTO runs(id,task_id,account_id,status) VALUES(?,?,?,?)", (record["id"], int(task_id), int(account_id), run_status))
                    target_id = record["id"]
                    counts["created"] += 1
                mapping[kind, legacy_id] = target_id
                if not existing:
                    connection.execute("INSERT INTO v3_offline_imports VALUES(?,?,?,?,?)", (source_id, kind, legacy_id, digest, target_id))
        if apply:
            connection.commit()
        else:
            connection.rollback()
    finally:
        connection.close()
    return counts


def backup(values: dict, destination: Path) -> None:
    """仅在本部署全部停止后保存持久目录和一致的 SQLite 快照。

    :param values: 当前部署配置
    :param destination: 全新且与数据根分离的绝对备份目录
    :return: None；不停机、不覆盖任何已有目录
    """
    deployment = values["V3_DEPLOYMENT_ID"]
    root = _owned_root(values, stopped=True)
    target = destination.resolve()
    if not destination.is_absolute() or target.exists() or target == root or root in target.parents or target in root.parents:
        raise ValueError("备份必须使用数据根以外的全新绝对目录")
    manifest = inspect_images(values)
    target.mkdir(mode=0o700, parents=True)
    try:
        shutil.copytree(root, target / "data", symlinks=True)
        for relative in ("gateway/gateway.sqlite", "bench/db.sqlite"):
            source = root / relative
            if not source.exists():
                continue
            output = target / "data" / relative
            for suffix in ("", "-wal", "-shm"):
                Path(str(output) + suffix).unlink(missing_ok=True)
            # 使用 SQLite backup API 而非只复制主文件，保留尚未 checkpoint 的合法事务。
            with sqlite3.connect("file:" + quote(str(source), safe="/") + "?mode=ro", uri=True) as current:
                with sqlite3.connect(output) as snapshot:
                    current.backup(snapshot)
            output.chmod(0o600)
        (target / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (target / ".v3-backup.json").write_text(json.dumps({"deployment": deployment,
            "source_root": str(root), "layout_version": manifest["layout_version"],
            "bridge_protocol": manifest["bridge_protocol"], "release": manifest["release"]}) + "\n")
    except Exception:
        shutil.rmtree(target)
        raise
    print("v3 停机备份完成：" + str(target))


def main() -> None:
    """执行指定操作；stop 只收口匹配 v3 标签的账号和 Compose 服务。

    :return: None
    """
    parser = argparse.ArgumentParser(description="v3 联合镜像管理")
    parser.add_argument("action", choices=("build", "publish", "pull", "load", "check", "up", "status", "stop", "backup", "import-offline"))
    parser.add_argument("--env", type=Path)
    parser.add_argument("--release")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--namespace", default="ghcr.io/silentflower")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.action == "build":
        build(args.release or uuid.uuid4().hex, args.manifest or REPO / "releases" / "v3.json")
        return
    if args.action in ("publish", "pull", "load"):
        if not args.manifest:
            parser.error("镜像交付操作需要 --manifest")
        if args.action == "publish":
            if not args.output or not args.bundle:
                parser.error("publish 需要 --output 和 --bundle")
            publish(args.manifest, args.output, args.bundle, args.namespace)
        elif args.action == "pull":
            pull(args.manifest)
        else:
            if not args.bundle:
                parser.error("load 需要 --bundle")
            load_bundle(args.manifest, args.bundle)
        return
    if not args.env:
        parser.error("此操作需要 --env")
    values = load_environment(args.env)
    if args.action == "import-offline":
        if not args.source:
            parser.error("import-offline 需要 --source")
        print(json.dumps(import_offline(values, args.source, args.apply), ensure_ascii=False))
        return
    if args.action == "backup":
        if not args.backup_dir:
            parser.error("backup 需要 --backup-dir")
        backup(values, args.backup_dir)
        return
    environment = dict(os.environ, **values)
    compose = ["docker", "compose", "--env-file", str(args.env.resolve()), "-f", str(COMPOSE)]
    if args.action in ("check", "up"):
        root = preflight(values)
        if args.action == "check":
            print("v3 版本、数据归属、端口和资源预检通过")
            return
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for child in ("gateway", "bench"):
            (root / child).mkdir(exist_ok=True, mode=0o700)
        (root / ".v3-deployment.json").write_text(json.dumps({"deployment": values["V3_DEPLOYMENT_ID"]}))
        environment.update(values)
        command(*compose, "up", "-d", environment=environment)
    elif args.action == "status":
        status(values)
    else:
        deployment = values["V3_DEPLOYMENT_ID"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", deployment):
            raise ValueError("部署标识不合法")
        # 调度器先收口 CLI 租约，此时网关仍可用；随后关闭发送器和网关。
        # 只认产品/部署/角色标签，不通过 Compose 项目名接管其它容器。
        for role in ("orchestrator", "account", "gateway"):
            ids = command("docker", "ps", "-q", "--filter", "label=vibebench.product=v3",
                "--filter", f"label=vibebench.deployment={deployment}",
                "--filter", f"label=vibebench.role={role}", capture=True).split()
            if ids:
                command("docker", "stop", *ids)
        # 不删除网络：已停止的固定账号容器仍引用该网络；数据和容器均保留。


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(f"v3 操作失败：{detail}", file=sys.stderr)
        sys.exit(1)
