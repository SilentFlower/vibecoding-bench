"""v3 单账号固定容器、执行句柄和服务间传输登记。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import threading
import time
import tempfile
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from socket import SHUT_WR
from typing import Callable
from urllib.parse import quote, unquote, urlsplit

from docker.errors import NotFound
from resource_budget import account_limits


NETWORK_INSPECTION_MODES = {"passthrough", "quota", "capture"}


def locale_for_timezone(timezone: str | None) -> str:
    """
    为显式时区选择同地区的可用 locale。

    :param timezone: IANA 时区名；空值使用英语回退
    :return: 账号镜像已生成的 UTF-8 locale
    """
    value = timezone or "UTC"
    if value == "Asia/Tokyo":
        return "ja_JP.UTF-8"
    if value == "Asia/Seoul":
        return "ko_KR.UTF-8"
    if value == "Europe/Berlin":
        return "de_DE.UTF-8"
    if value == "Europe/Paris":
        return "fr_FR.UTF-8"
    if value == "Europe/London":
        return "en_GB.UTF-8"
    return "en_US.UTF-8"


def derive_v3_fingerprint(timezone: str | None = None) -> dict[str, object]:
    """
    生成首次随机且可持久化的 v3 账号画像。

    :param timezone: 账号显式 IANA 时区；空值使用 UTC
    :return: profile v2 指纹字段
    """
    mac = bytearray(secrets.token_bytes(6))
    # Docker 账号 MAC 使用本地管理单播地址；各字段独立取随机值，不共享 seed。
    mac[0] = (mac[0] | 0x02) & 0xFE
    return {
        "profile_version": 2,
        "hostname": secrets.token_hex(6),
        "machine_id": secrets.token_hex(16),
        "mac": ":".join(f"{value:02x}" for value in mac),
        "tz": timezone or "UTC",
        "lang": locale_for_timezone(timezone),
    }


def atomic_json(path: Path, value: dict, mode: int = 0o600) -> None:
    """原子保存受限 JSON。

    :param path: 目标路径
    :param value: JSON object
    :param mode: 文件权限
    :return: None
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as output:
            os.chmod(temporary, mode)
            json.dump(value, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class RuntimeBusy(ValueError):
    """低优先级作业遇到正式工作时顺延，不能记为认证或任务失败。"""


class AccountRuntime:
    """每账号仅一个固定容器；执行结束不销毁 HOME 或网络。

    :param client: Docker SDK 客户端
    :param data: 调度器本地数据根
    :param host_data: Docker daemon 视角的数据根
    :param database: 返回 SQLite connection 的函数
    :param fingerprint: 首次创建时读取现有环境参数的函数
    :param gateway: 受信任 cc2api 客户端
    """

    def __init__(self, client, data: Path, host_data: Path, database: Callable,
                 fingerprint: Callable, gateway, quota_identity: Callable | None = None) -> None:
        self.client, self.data, self.host_data = client, data, host_data
        self.database, self.fingerprint, self.gateway = database, fingerprint, gateway
        self.quota_identity = quota_identity
        self.deployment = os.environ["V3_DEPLOYMENT_ID"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", self.deployment):
            raise ValueError("V3_DEPLOYMENT_ID 格式不合法")
        self.image = os.environ["V3_ACCOUNT_IMAGE"]
        self.network = os.environ["V3_NETWORK"]
        self.release_id = os.environ.get("V3_RELEASE", "")
        self.limit = int(os.environ.get("V3_MAX_ACTIVE_ACCOUNTS", "1"))
        if self.limit < 1:
            raise ValueError("v3 活跃环境预算必须大于零")
        self.lock = threading.RLock()
        self.environment_locks: dict[str, threading.RLock] = {}
        self.capacity_lock = threading.RLock()
        self.heartbeat_pool = ThreadPoolExecutor(max_workers=self.limit + 1, thread_name_prefix="v3-lease")
        self.jobs: dict[str, dict] = {}
        self.stopping = threading.Event()
        self.heartbeat = threading.Thread(target=self._heartbeat, daemon=True)
        connection = database()
        try:
            with connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS account_environments (
                    environment_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                    account_id INTEGER UNIQUE, fingerprint_json TEXT NOT NULL,
                    generation INTEGER NOT NULL DEFAULT 0, container_id TEXT,
                    state TEXT NOT NULL DEFAULT 'stopped')""")
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(runs)")}
                if columns:
                    for column, kind in (("environment_id", "TEXT"), ("environment_generation", "INTEGER"),
                            ("execution_source", "TEXT"), ("runtime_release", "TEXT")):
                        if column not in columns:
                            connection.execute(f"ALTER TABLE runs ADD COLUMN {column} {kind}")
        finally:
            connection.close()

    def environment_lock(self, environment_id: str):
        """取得账号级生命周期锁，全局登记锁只用于读取锁映射。

        :param environment_id: 不可变环境 ID
        :return: 可重入的账号锁
        """
        with self.lock:
            return self.environment_locks.setdefault(environment_id, threading.RLock())

    def _account_lock(self, account: dict):
        with self.lock:
            row = self._row(account["name"], account.get("id"), account.get("timezone"))
            draft_path = self.data / "login-drafts" / (row["environment_id"] + ".json")
            if draft_path.exists() and json.loads(draft_path.read_text()).get("phase") == "deleting":
                raise ValueError("登录草稿正在清理，禁止唤醒或重建")
        return self.environment_lock(row["environment_id"])

    @staticmethod
    def execution_token(container_id: str, source: str) -> str:
        """生成绑定执行来源的句柄，固定容器 ID 不能单独用于清理。

        :param container_id: 固定容器 ID
        :param source: 不可复用的执行来源
        :return: 绑定来源摘要的执行 token
        """
        return container_id + ":" + hashlib.sha256(source.encode()).hexdigest()[:20]

    def _sync_proxy(self, account: dict, configuration: dict) -> None:
        """仅从 cc2api 同步绑定账号代理；保留身份和运行目录。"""
        proxy = configuration["proxy_url"] or ""
        try:
            parsed = urlsplit(proxy)
            if proxy and (parsed.scheme not in ("http", "socks5", "socks5h") or not parsed.hostname
                    or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
                raise ValueError
            fields = {"upstream_proxy_scheme": parsed.scheme or "socks5",
                "upstream_socks5_host": parsed.hostname or "", "upstream_socks5_port": parsed.port or (80 if parsed.scheme == "http" else 1080),
                "upstream_socks5_user": unquote(parsed.username) if parsed.username else "",
                "upstream_socks5_pass": unquote(parsed.password) if parsed.password else ""}
        except ValueError:
            raise ValueError("cc2api 代理配置不支持当前账号网络环境") from None
        if all(account.get(key) == value for key, value in fields.items()):
            return
        connection = self.database()
        try:
            with connection:
                cursor = connection.execute("UPDATE accounts SET " + ",".join(f"{key}=?" for key in fields)
                    + " WHERE id=? AND cc2api_account_id=?", (*fields.values(), account["id"], account["cc2api_account_id"]))
                if cursor.rowcount != 1:
                    raise ValueError("账号绑定已改变，拒绝发布代理配置")
            account.update(fields)
        finally:
            connection.close()

    def _row(self, name: str, account_id=None, timezone: str | None = None) -> dict:
        """
        读取或首次登记固定账号环境。

        :param name: 账号名
        :param account_id: 可选正式账号 ID
        :param timezone: 新环境首次固化的显式时区
        :return: 环境数据库行
        """
        connection = self.database()
        try:
            row = connection.execute("SELECT * FROM account_environments WHERE account_id=? OR name=?",
                                     (account_id, name)).fetchone()
            if row:
                if account_id is not None and row["account_id"] not in (None, account_id):
                    raise ValueError("环境已绑定其它账号")
                if account_id is not None and row["account_id"] is None:
                    with connection:
                        connection.execute("UPDATE account_environments SET account_id=? WHERE environment_id=?",
                                           (account_id, row["environment_id"]))
                result = dict(row)
                if account_id is not None:
                    result["account_id"] = account_id
                    if result["name"] != name:
                        with connection:
                            connection.execute("UPDATE account_environments SET name=? WHERE environment_id=?", (name, row["environment_id"]))
                        result["name"] = name
                return result
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
                raise ValueError("账号名称不合法")
            environment_id = uuid.uuid4().hex
            fingerprint = self.fingerprint(timezone)
            fingerprint["mem"] = os.environ.get("V3_ACCOUNT_MEMORY", "4g")
            fingerprint["swap"] = os.environ.get("V3_ACCOUNT_SWAP", "0")
            account_limits(fingerprint["mem"], fingerprint["swap"])
            with connection:
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json) VALUES(?,?,?,?)",
                                   (environment_id, name, account_id, json.dumps(fingerprint)))
            return {"environment_id": environment_id, "name": name, "account_id": account_id,
                    "fingerprint_json": json.dumps(fingerprint), "generation": 0,
                    "container_id": None, "state": "stopped"}
        finally:
            connection.close()

    def _update(self, row: dict, **fields) -> None:
        connection = self.database()
        try:
            with connection:
                connection.execute("UPDATE account_environments SET " + ",".join(f"{key}=?" for key in fields)
                                   + " WHERE environment_id=?", (*fields.values(), row["environment_id"]))
            row.update(fields)
        finally:
            connection.close()

    def _root(self, row: dict) -> Path:
        return self.data / "environments" / row["environment_id"]

    def _labels(self, row: dict) -> dict:
        return {"vibebench.product": "v3", "vibebench.deployment": self.deployment,
                "vibebench.environment": row["environment_id"], "vibebench.role": "account"}

    def _container(self, row: dict):
        container = self.client.containers.get(row["container_id"])
        if any(container.labels.get(key) != value for key, value in self._labels(row).items()):
            raise ValueError("容器部署归属不匹配，拒绝操作")
        return container

    def ensure(self, account: dict, version: str | None = None, allow_inactive_login: bool = False,
               allow_login_recovery: bool = False) -> tuple[dict, object]:
        """创建或唤醒固定环境，沿用首次固化参数。

        :param account: bench 账号或登录草稿
        :param version: 可选目标 CLI 版本；发送器准备无需 CLI
        :param allow_inactive_login: 仅显式重授权允许读取非 active OAuth 配置
        :param allow_login_recovery: 仅恢复原登录提交可进入本地保存门禁
        :return: 环境记录与 Docker container
        """
        with self._account_lock(account):
            row = self._row(account["name"], account.get("id"), account.get("timezone"))
            # 历史画像门禁没有凭据失效证据；只迁移生命周期，不旋转画像或 HOME。
            if row["state"] in ("profile_reauth", "profile_reauth_reconcile"):
                self._update(row, state="reconcile" if row["state"] == "profile_reauth_reconcile" else "stopped")
            image = self.client.images.get(self.image)
            image_labels = image.attrs["Config"].get("Labels") or {}
            if not self.release_id or image_labels.get("vibebench.product") != "v3" or image_labels.get("vibebench.role") != "account" or image_labels.get("vibebench.release") != self.release_id:
                raise ValueError("账号镜像角色或构建批次不匹配")
            if account.get("cc2api_account_id") is not None:
                configuration = self.gateway._request("GET", f"/admin/runtime/accounts/{account['cc2api_account_id']}/config")
                if configuration["auth_type"] != "oauth" or (configuration["status"] != "active" and not allow_inactive_login):
                    raise ValueError("绑定账号认证类型或状态不可用")
                self._sync_proxy(account, configuration)
            draft_path = self.data / "login-drafts" / (row["environment_id"] + ".json")
            if draft_path.exists() and json.loads(draft_path.read_text()).get("phase") == "submitting" and not allow_login_recovery:
                raise ValueError("原登录保存尚未完成，请先继续登录提交")
            if int(row["generation"]) == 0 and account.get("timezone"):
                fingerprint = json.loads(row["fingerprint_json"])
                if fingerprint.get("profile_version") == 2:
                    fingerprint["tz"] = account["timezone"]
                    fingerprint["lang"] = locale_for_timezone(account["timezone"])
                    self._update(row, fingerprint_json=json.dumps(fingerprint))
            root = self._root(row)
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            for name in ("home", "projects", "workspaces", "flows", "controls", "ca", "cli", "runtime"):
                (root / name).mkdir(exist_ok=True, mode=0o700)
            for name in ("home", "projects"):
                os.chown(root / name, 1000, 1000)
            if row["state"] == "reconcile":
                raise ValueError("账号环境需要先对账，拒绝自动放行")
            with self.capacity_lock:
                try:
                    container = self._container(row) if row["container_id"] else None
                except NotFound:
                    container = None
                if container:
                    if container.labels.get("vibebench.release") != self.release_id:
                        raise ValueError("账号容器属于旧 v3 批次，请空闲重建后使用")
                    container.reload()
                    configuration_path = root / "runtime" / "sender.json"
                    configuration = json.loads(configuration_path.read_text())
                    if configuration.get("proxy_source", configuration["proxy_url"]) != self._proxy(account):
                        if container.status == "running" or row["environment_id"] in self.jobs:
                            raise ValueError("代理已改变，请先空闲维护账号环境")
                        # 配置事务已经停止旧发送器；只替换停止实例，HOME 和身份保持原值。
                        container.remove()
                        self._update(row, container_id=None, state="stopped")
                        container = None
                if container:
                    if container.status != "running":
                        self._make_room(row)
                        configuration_path = root / "runtime" / "sender.json"
                        configuration = json.loads(configuration_path.read_text())
                        generation = int(row["generation"]) + 1
                        configuration["binding"].update(generation=generation, secret=secrets.token_hex(32))
                        atomic_json(configuration_path, configuration)
                        (root / "runtime" / "ready").unlink(missing_ok=True)
                        container.start()
                        self._update(row, state="starting", generation=generation)
                else:
                    self._make_room(row)
                    fingerprint = json.loads(row["fingerprint_json"])
                    generation = int(row["generation"]) + 1
                    # DNS 单标签上限为 63 字符；完整部署归属保存在 labels 中。
                    deployment_key = hashlib.sha256(self.deployment.encode()).hexdigest()[:12]
                    name = f"v3-{deployment_key}-account-{row['environment_id']}"
                    binding = {"account_id": int(account.get("cc2api_account_id") or 0),
                        "environment_id": row["environment_id"], "generation": generation,
                        "endpoint": f"http://{name}:8091", "secret": secrets.token_hex(32), "release_id": self.release_id}
                    proxy = self._proxy(account)
                    atomic_json(root / "runtime" / "sender.json", {"binding": binding,
                        "proxy_url": proxy, "allowed_origin": "https://api.anthropic.com",
                        "evidence_file": "/flows/api/observations.jsonl", "quota_identity": ""})
                    environment = {"V3_MACHINE_ID": fingerprint["machine_id"], "HOME": "/home/node",
                        "TZ": fingerprint["tz"], "LANG": fingerprint["lang"],
                        "LC_ALL": fingerprint["lang"], "V3_SENDER_CONFIG": "/run/v3/sender.json",
                        "DNS_READY_HOST": os.environ.get("DNS_READY_HOST", "example.com"),
                        "UPSTREAM_PROXY_SCHEME": account.get("upstream_proxy_scheme") or "socks5",
                        "UPSTREAM_SOCKS5_HOST": account.get("upstream_socks5_host") or "",
                        "UPSTREAM_SOCKS5_PORT": str(account.get("upstream_socks5_port") or 1080),
                        "UPSTREAM_SOCKS5_USER": account.get("upstream_socks5_user") or "",
                        "UPSTREAM_SOCKS5_PASS": account.get("upstream_socks5_pass") or ""}
                    host_root = self.host_data / root.relative_to(self.data)
                    mounts = {str(host_root / source): {"bind": target, "mode": "rw"} for source, target in (
                        ("home", "/home/node"), ("projects", "/home/node/projects"), ("flows", "/flows"),
                        ("controls", "/controls"), ("ca", "/ca"), ("cli", "/cli"), ("runtime", "/run/v3"))}
                    quota = self.data / "quota"
                    quota.mkdir(parents=True, exist_ok=True, mode=0o700)
                    mounts[str(self.host_data / "quota")] = {"bind": "/quota-accounts", "mode": "ro"}
                    # swap 跟随首次预算固化；旧环境缺字段时保持禁用，不能随全局配置放大。
                    memory, memory_swap = account_limits(fingerprint["mem"], fingerprint.get("swap", "0"))
                    container = self.client.containers.run(self.image, name=name, detach=True,
                        auto_remove=False, labels={**self._labels(row), "vibebench.release": self.release_id}, network=self.network,
                        hostname=fingerprint["hostname"], mac_address=fingerprint["mac"],
                        mem_limit=memory, memswap_limit=memory_swap,
                        nano_cpus=int(float(os.environ.get("V3_ACCOUNT_CPUS", "2")) * 1_000_000_000),
                        cap_add=["NET_ADMIN"], devices=["/dev/net/tun:/dev/net/tun"],
                        security_opt=["no-new-privileges:true"], volumes=mounts, environment=environment,
                        log_config={"type": "json-file", "config": {"max-size": "10m", "max-file": "3"}})
                    self._update(row, container_id=container.id, generation=generation,
                        state="starting")
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                result = container.exec_run(["test", "-f", "/run/v3/ready"])
                if result.exit_code == 0:
                    try:
                        self._sender_active(row)
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.25)
                        continue
                    if row["state"] != "cli_reconcile":
                        self._update(row, state="ready")
                    break
                container.reload()
                if container.status != "running":
                    raise ValueError("账号环境启动失败")
                time.sleep(0.25)
            else:
                raise ValueError("账号环境未在截止时间内就绪")
        # 版本缓存准备不持有环境生命周期锁，API 不等待 CLI 安装。
        if version is not None:
            self._ensure_version(container, version)
        return row, container

    def _ensure_version(self, container, version: str) -> None:
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?", version):
            raise ValueError("CLI 版本格式不合法")
        result = container.exec_run(["timeout", "--kill-after=5", "180", "/usr/local/bin/v3-cli-version", version])
        if result.exit_code != 0:
            raise ValueError("固定环境 CLI 版本准备失败")

    @staticmethod
    def _proxy(account: dict) -> str:
        host = account.get("upstream_socks5_host") or ""
        if not host:
            return ""
        scheme = account.get("upstream_proxy_scheme") or "socks5"
        if scheme not in ("http", "socks5", "socks5h"):
            raise ValueError("不支持该上游代理协议")
        user, password = account.get("upstream_socks5_user"), account.get("upstream_socks5_pass")
        credentials = f"{quote(user, safe='')}:{quote(password or '', safe='')}@" if user else ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"{scheme}://{credentials}{host}:{int(account.get('upstream_socks5_port') or 1080)}"

    def sync_credentials(self, row: dict, account: dict) -> None:
        """发布 AT-only 运行凭据，完整 RT 副本留在管理目录。

        :param row: 固定环境
        :param account: bench 账号
        :return: None
        """
        profile = self.data / "profiles" / account["name"]
        path = profile / ".credentials.json"
        if not path.exists():
            return
        credentials = json.loads(path.read_text())
        home = self._root(row) / "home"
        destination = home / ".claude" / ".credentials.json"
        if account.get("cc2api_account_id") is None and destination.exists():
            # 未绑定时固定 HOME 是唯一运行所有者，不能用旧 profile 覆盖轮换后的 RT。
            credentials = json.loads(destination.read_text())
        if account.get("cc2api_account_id") is not None:
            credentials.get("claudeAiOauth", {}).pop("refreshToken", None)
        atomic_json(destination, credentials)
        os.chown(destination.parent, 1000, 1000)
        os.chown(destination, 1000, 1000)
        access = self._root(row) / "runtime" / "access" / ".credentials.json"
        atomic_json(access, credentials)
        if not (home / ".claude.json").exists() and (profile / ".claude.json").exists():
            shutil.copy2(profile / ".claude.json", home / ".claude.json")
            os.chown(home / ".claude.json", 1000, 1000)

    def transport(self, account: dict, version: str) -> dict:
        """返回只用于服务间调用的当前传输绑定。

        :param account: 绑定的 bench 账号
        :param version: 兼容旧调用方的 CLI 版本，不参与 API 环境准备
        :return: 当前账号传输绑定，含受限服务秘密
        """
        row, _ = self.ensure(account)
        config_path = self._root(row) / "runtime" / "sender.json"
        config = json.loads(config_path.read_text())
        binding = config["binding"]
        if config.get("proxy_source", config["proxy_url"]) != self._proxy(account):
            raise ValueError("代理配置已改变，请空闲重建环境后再使用")
        identity = self.quota_identity(account) if self.quota_identity else ""
        if binding["account_id"] != account["cc2api_account_id"] or config.get("quota_identity") != identity:
            binding["account_id"] = int(account["cc2api_account_id"])
            config["quota_identity"] = identity
            atomic_json(config_path, config)
        return binding

    def _sender_active(self, row: dict) -> int:
        binding = json.loads((self._root(row) / "runtime" / "sender.json").read_text())["binding"]
        request = urllib.request.Request(binding["endpoint"] + "/internal/status",
            headers={"Authorization": "Bearer " + binding["secret"]})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            value = json.load(response)
        if value["environment_id"] != row["environment_id"] or value["generation"] != row["generation"]:
            raise ValueError("发送器代次不一致")
        if value.get("evidence_ok") is False:
            raise ValueError("API 证据写入异常，账号环境需要维护")
        return int(value["active"])

    def _running_sender_active(self, row: dict) -> int:
        if not row.get("container_id"):
            return 0
        try:
            container = self._container(row)
        except NotFound:
            return 0
        container.reload()
        return self._sender_active(row) if container.status == "running" else 0

    @contextmanager
    def owner_transition(self, account: dict, target_id: int | None):
        """在绑定切换整个事务期间关闭两端门禁并撤销旧发送实例。

        :param account: 切换前的 bench 账号
        :param target_id: 新 cc2api 绑定，None 表示解绑或删除
        :return: 持有环境锁与远端门禁的上下文
        """
        with self._account_lock(account):
            row = self._row(account["name"], account["id"])
            if row["environment_id"] in self.jobs:
                raise ValueError("账号环境正在执行工作，不能切换绑定")
            leases = []
            try:
                for account_id in sorted({int(value) for value in (account.get("cc2api_account_id"), target_id) if value is not None}):
                    path = f"/admin/runtime/accounts/{account_id}/lease"
                    snapshot = self.gateway._request("GET", path)
                    if snapshot["active"] or snapshot.get("waiting") or snapshot["lease"]:
                        raise ValueError("绑定账号有活动或等待请求，不能切换绑定")
                    snapshot = self.gateway._request("POST", path, {"operation": "prepare", "owner": f"binding:{uuid.uuid4().hex}"})
                    leases.append((path, snapshot["lease"]))
                    if snapshot["active"] or self._running_sender_active(row):
                        raise ValueError("账号发送连接尚未收口，不能切换绑定")
                if self._running_sender_active(row):
                    raise ValueError("账号发送连接尚未收口，不能切换绑定")
                if row.get("container_id"):
                    try:
                        self._container(row).stop(timeout=5)
                    except NotFound:
                        pass
                # 已解析的旧 API 请求只能遇到停止的实例；下一唤醒轮换秘密和代次。
                self._update(row, state="stopped")
                yield
                connection = self.database()
                try:
                    current = connection.execute("SELECT * FROM accounts WHERE id=?", (account["id"],)).fetchone()
                finally:
                    connection.close()
                if current:
                    self.sync_credentials(row, dict(current))
            finally:
                for path, lease in reversed(leases):
                    try:
                        self.gateway._request("POST", path, {"operation": "release", "owner": lease["owner"], "generation": lease["generation"]})
                    except Exception:
                        self._update(row, state="reconcile")
                        raise

    def claim(self, row: dict, account: dict, source: str, idle_only: bool = False,
              exclusive: bool = False) -> dict:
        """串行认领 CLI；只有环境维护需要排空独立 API。

        :param row: 环境记录
        :param account: 当前账号
        :param source: 不可复用的执行来源
        :param idle_only: 低优先级工作遇到正式 CLI 或维护时立即顺延
        :param exclusive: 是否修改共享环境并需要排空 API
        :return: 本代执行句柄
        """
        with self.environment_lock(row["environment_id"]):
            if not exclusive and (self._root(row) / "runtime" / "cli-unhealthy").exists():
                self._update(row, state="cli_reconcile")
            if row["state"] in ("reconcile", "cli_reconcile"):
                raise ValueError("账号 CLI 需要先对账，拒绝开始下一作业")
            with self.lock:
                pending = self._root(row) / "runtime" / "login-commit.json"
                if pending.exists() and source != f"login:{json.loads(pending.read_text())['sid']}":
                    raise ValueError("重授权提交尚未收口，请先对账")
                if row["environment_id"] in self.jobs:
                    if idle_only:
                        raise RuntimeBusy("账号环境正在执行其它工作，低优先级工作顺延")
                    raise ValueError("账号环境正在执行其它工作")
                job = {"row": row, "account": dict(account), "source": source, "lease": None, "exec": None,
                    "claimed": False, "exclusive": exclusive, "last_used": time.monotonic()}
                job["lease_lock"] = threading.RLock()
                job["token"] = self.execution_token(row.get("container_id") or row["environment_id"], source)
                self.jobs[row["environment_id"]] = job
            account_id = account.get("cc2api_account_id")
            try:
                if account_id is not None:
                    path = f"/admin/runtime/accounts/{account_id}/lease"
                    if idle_only:
                        snapshot = self.gateway._request("GET", path)
                        if snapshot["lease"] or (exclusive and (snapshot["active"] or snapshot.get("waiting"))):
                            raise RuntimeBusy("账号有正式请求，低优先级工作顺延")
                    result = self.gateway._request("POST", path,
                        {"operation": "prepare" if exclusive else "prepare-cli", "owner": source})
                    job["lease"] = result["lease"]
                    if exclusive and idle_only and (result["active"] or self._running_sender_active(row)):
                        raise RuntimeBusy("账号已有请求，低优先级工作顺延")
                    deadline = time.monotonic() + 120
                    while exclusive and (result["active"] or self._running_sender_active(row)):
                        if time.monotonic() > deadline:
                            raise ValueError("账号既有请求未完成，执行未启动")
                        self._lease(job, "heartbeat")
                        time.sleep(0.5)
                        result = self.gateway._request("GET", path)
                    self._lease(job, "claim")
                elif exclusive and self._running_sender_active(row):
                    raise ValueError("未绑定环境仍有发送连接，需先对账")
                if job.get("heartbeat_failed"):
                    raise ValueError("执行门禁心跳失败，执行未启动")
                job["claimed"] = True
                self._save_execution(job)
                return job
            except Exception:
                # 排空未完成时尚未启动 CLI，可撤销本次排空门禁，保留已接受的 API 流。
                try:
                    self._lease(job, "release")
                except Exception:
                    self._save_execution(job)
                    self._isolate_job(job)
                    raise
                finally:
                    with self.lock:
                        self.jobs.pop(row["environment_id"], None)
                raise

    def _lease(self, job: dict, operation: str) -> dict:
        with job.setdefault("lease_lock", threading.RLock()):
            lease = job.get("lease")
            if not lease:
                return {}
            result = self.gateway._request("POST", f"/admin/runtime/accounts/{job['account']['cc2api_account_id']}/lease",
                {"operation": operation, "owner": lease["owner"], "generation": lease["generation"]})
            job["lease"] = None if operation == "release" else result["lease"]
            return result

    def _save_execution(self, job: dict) -> None:
        execution = {"source": job["source"], "lease": job["lease"],
            "account_id": job["account"].get("cc2api_account_id"), "phase": "claimed",
            "exclusive": job.get("exclusive", True), "container_id": job["row"].get("container_id"),
            "generation": job["row"]["generation"]}
        for key in ("exec", "handle", "tmux", "tmux_socket", "hooks_before"):
            if key in job:
                execution[key] = job[key]
        atomic_json(self._root(job["row"]) / "runtime" / "execution.json", execution)

    def _isolate_job(self, job: dict) -> None:
        # 普通 CLI 收口失败只禁止下一 CLI，独立发送器继续处理已接受的 API。
        if job.get("exclusive", True):
            try:
                if job.get("claimed", True):
                    self._container(job["row"]).stop(timeout=5)
            finally:
                self._update(job["row"], state="reconcile")
        else:
            self._update(job["row"], state="cli_reconcile")

    def release(self, job: dict) -> None:
        """确认本作业收口后释放租约；共享 CLI 不等待独立 API。

        :param job: 领取的执行句柄
        :return: None
        """
        row = job["row"]
        with self.environment_lock(row["environment_id"]):
            with self.lock:
                if self.jobs.get(row["environment_id"]) is not job:
                    return
            try:
                if job.get("exec") and self.client.api.exec_inspect(job["exec"]).get("Running"):
                    raise ValueError("执行尚未停止")
                if job.get("exclusive", True) and self._running_sender_active(row):
                    raise ValueError("账号发送连接尚未收口")
                if job["account"].get("cc2api_account_id") is None:
                    credentials = self._root(row) / "home" / ".claude" / ".credentials.json"
                    if credentials.exists():
                        atomic_json(self.data / "profiles" / row["name"] / ".credentials.json", json.loads(credentials.read_text()))
                self._lease(job, "release")
                (self._root(row) / "runtime" / "execution.json").unlink(missing_ok=True)
                if row["state"] == "cli_reconcile":
                    self._update(row, state="ready")
            except Exception:
                self._isolate_job(job)
                raise
            finally:
                with self.lock:
                    self.jobs.pop(row["environment_id"], None)

    def _heartbeat(self) -> None:
        while not self.stopping.wait(5):
            with self.lock:
                jobs = list(self.jobs.values())
            # 每个账号独立续期，单个慢服务请求不能耗尽其它账号的 30 秒租约。
            for job in jobs:
                future = job.get("heartbeat_future")
                if not future or future.done():
                    job["heartbeat_future"] = self.heartbeat_pool.submit(self._renew_job, job)

    def _renew_job(self, job: dict) -> None:
        failed = False
        with job.setdefault("lease_lock", threading.RLock()):
            with self.lock:
                if self.stopping.is_set() or self.jobs.get(job["row"]["environment_id"]) is not job:
                    return
            try:
                self._lease(job, "heartbeat")
            except Exception:
                job["heartbeat_failed"] = True
                failed = True
        if failed:
            # 不能带租约锁等待环境锁，cleanup 的锁顺序相反；旧 token 也不能清理新代。
            with self.environment_lock(job["row"]["environment_id"]):
                with self.lock:
                    if self.jobs.get(job["row"]["environment_id"]) is not job:
                        return
                if job["claimed"]:
                    try:
                        self.cleanup(job["token"])
                    except Exception:
                        pass

    @contextmanager
    def _cli_setup(self, account: dict, source: str, version: str,
                   idle_only: bool = False, exclusive: bool = False, allow_inactive_login: bool = False):
        row, container = self.ensure(account, allow_inactive_login=allow_inactive_login,
            allow_login_recovery=source.startswith("login:"))
        job = self.claim(row, account, source, idle_only, exclusive)
        try:
            self._ensure_version(container, version)
            with self.environment_lock(row["environment_id"]):
                with self.lock:
                    if self.jobs.get(row["environment_id"]) is not job or job.get("heartbeat_failed"):
                        raise ValueError("CLI 准备期间租约失效，执行未启动")
                yield row, container, job
        except Exception:
            self.cleanup(job["token"])
            raise

    def start_run(self, account: dict, task: dict, run_id: str, worker_env: dict, quota_env: dict) -> tuple[str, str]:
        """在固定容器内创建独立工作目录并启动一次 driver exec。

        :param account: 当前账号
        :param task: 已冻结的 run 配置
        :param run_id: 原 run ID
        :param worker_env: 既有 driver 环境变量
        :param quota_env: 当前额度上下文
        :return: 相同的执行 token，供旧 DTO 的两个字段兼容使用
        """
        source = worker_env.get("QUOTA_SOURCE") or f"run:{run_id}:{task.get('quota_attempt', 0)}"
        with self._cli_setup(account, source, worker_env["CLAUDE_CODE_VERSION"], bool(task.get("warmup"))) as (row, container, job):
            try:
                self.sync_credentials(row, account)
                root = self._root(row)
                settings = root / "home" / ".claude" / "settings.json"
                job["hooks_before"] = json.loads(settings.read_text()).get("hooks") if settings.exists() else None
                cwd = self._project_view(row, run_id)
                workspace = root / "projects" / Path(cwd).name
                legacy = self.data / "workspaces" / run_id
                legacy.parent.mkdir(parents=True, exist_ok=True)
                if not legacy.exists():
                    legacy.symlink_to(os.path.relpath(workspace, legacy.parent), target_is_directory=True)
                elif legacy.resolve() != workspace.resolve():
                    # 只允许迁入独立 v3 的历史工作目录；不可让旧文件留在第二个运行位置。
                    if any(legacy.iterdir()):
                        shutil.copytree(legacy, workspace, dirs_exist_ok=True)
                    shutil.rmtree(legacy)
                    legacy.symlink_to(os.path.relpath(workspace, legacy.parent), target_is_directory=True)
                handle = hashlib.sha256(source.encode()).hexdigest()[:20]
                self._session_view(row, run_id, cwd)
                controls = root / "controls" / handle
                controls.mkdir(parents=True, exist_ok=True, mode=0o700)
                (root / "controls").chmod(0o750)
                os.chown(root / "controls", 0, 1000)
                controls.chmod(0o750)
                os.chown(controls, 0, 1000)
                runtime_run = root / "runtime" / "runs" / run_id
                runtime_job = root / "runtime" / "jobs" / handle
                for directory in (runtime_run, runtime_job):
                    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                    os.chown(directory, 1000, 1000)
                control_files = {
                    ".bench-status.json": runtime_run / "status.json",
                    ".bench-transcript.log": runtime_run / "transcript.log",
                    ".bench-session-baseline.json": runtime_run / "session-baseline.json",
                }
                for name, destination in control_files.items():
                    legacy_control = workspace / name
                    if legacy_control.is_file():
                        if not destination.exists():
                            shutil.copy2(legacy_control, destination)
                        legacy_control.unlink()
                for name in (".cc2api-oauth-refresh-request.json", ".cc2api-oauth-refresh-result.json"):
                    (workspace / name).unlink(missing_ok=True)
                    (runtime_run / name.removeprefix(".cc2api-")).unlink(missing_ok=True)
                local_settings = workspace / ".claude" / "settings.local.json"
                if local_settings.is_file() and "claude-stop-seen" in local_settings.read_text(errors="ignore"):
                    local_settings.unlink()
                    try:
                        local_settings.parent.rmdir()
                    except OSError:
                        pass
                source_script = Path(os.environ.get("V3_WORKER_SCRIPT", "/opt/v3/worker.sh")).read_text()
                # v3 的私有控制树不向 CLI 开放写入；完成判定已有主会话 JSONL，无需另注入 Stop hook。
                source_script = source_script.replace(
                    "  Stop: [{matcher: '', hooks: [{type: 'command', command: 'date +%s >> /tmp/claude-stop-seen'}]}],\n", "")
                # v3 控制文件不放进 Claude 可见项目树；兼容 driver 仍由单一脚本生成。
                control_paths = {
                    "/workspace/.bench-status.json": f"/run/v3/runs/{run_id}/status.json",
                    "/workspace/.bench-transcript.log": f"/run/v3/runs/{run_id}/transcript.log",
                    "/workspace/.bench-session-baseline.json": f"/run/v3/runs/{run_id}/session-baseline.json",
                    "/workspace/.cc2api-oauth-refresh-request.json": f"/run/v3/runs/{run_id}/oauth-refresh-request.json",
                    "/workspace/.cc2api-oauth-refresh-result.json": f"/run/v3/runs/{run_id}/oauth-refresh-result.json",
                }
                script = source_script
                for old, new in control_paths.items():
                    script = script.replace(old, new)
                encoded_project = cwd.replace("/", "-")
                script = script.replace("-workspace", encoded_project)
                script = script.replace("/workspace", cwd).replace("/tmp/", f"/run/v3/jobs/{handle}/")
                script = script.replace("/mnt/profile", "/run/v3/access")
                # tmux 的登录 shell 会改写 PATH，显式传入本代已选定的 CLI 缓存。
                script = script.replace("runuser -u '$CLAUDE_USER' -- env", "setpriv --reuid=1000 --regid=1000 --init-groups --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs env PATH='$PATH'")
                script_path = root / "runtime" / f"job-{handle}.sh"
                script_path.write_text(script)
                script_path.chmod(0o700)
                original_flows = self.data / "flows" / account["name"] / str(task["id"]) / run_id
                flow_directory = self.execution_flows(account, source, original_flows)
                flow_path = "/flows/" + str(flow_directory.relative_to(root / "flows"))
                context = dict(quota_env)
                inspection_mode = "capture" if task.get("capture_full_http") else "passthrough"
                context.update(STATS_FILE=f"{flow_path}/stats.jsonl",
                    CAPTURE_FILE=f"{flow_path}/http_capture.jsonl", CAPTURE_INDEX_FILE=f"{flow_path}/capture_index.json",
                    CAPTURE_FULL_HTTP="1" if task.get("capture_full_http") else "0",
                    SAVE_FULL_FLOWS="1" if task.get("capture_full_http") else "0",
                    NETWORK_INSPECTION_MODE=inspection_mode)
                original_controls = self.data / "quota-controls" / run_id / handle
                self._link_directory(original_controls, controls)
                for key in ("QUOTA_STATE_FILE", "QUOTA_SIGNAL_FILE", "QUOTA_OBSERVATIONS_FILE"):
                    if key in context:
                        local = Path(context[key])
                        # 旧 sidecar 路径不能沿用；只发布本账号网络进程可读写的位置。
                        if key == "QUOTA_SIGNAL_FILE":
                            context[key] = f"/controls/{handle}/pause.json"
                        elif key == "QUOTA_OBSERVATIONS_FILE":
                            context[key] = f"{flow_path}/passive-quota.jsonl"
                        elif local.name == "state.json":
                            context[key] = f"/quota-accounts/{account['id']}/state.json"
                context["QUOTA_CREDENTIALS_FILE"] = "/home/node/.claude/.credentials.json"
                atomic_json(root / "runtime" / "context.json", context)
                self._configure_network_context(container, context)
                (root / "runtime" / f"tmux-{handle}").mkdir(exist_ok=True, mode=0o700)
                environment = dict(worker_env)
                environment.update(V3_PERSISTENT_HOME="1", USE_SIDECAR_DNS="1", HOME="/home/node",
                    PATH=f"/cli/{worker_env['CLAUDE_CODE_VERSION']}/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    QUOTA_SIGNAL_FILE=context.get("QUOTA_SIGNAL_FILE", ""), TMUX_TMPDIR=f"/run/v3/tmux-{handle}",
                    QUOTA_WARMUP="1" if inspection_mode == "quota" else "0",
                    NETWORK_INSPECTION_MODE=inspection_mode)
                ex = self.client.api.exec_create(container.id,
                    # setsid 默认可能先返回，必须让 exec 生命周期跟随真实 driver。
                    ["setsid", "--wait", "bash", "-c", f"echo $$ > /run/v3/job-{handle}.pid; exec bash /run/v3/job-{handle}.sh"],
                    environment=environment, workdir=cwd)
                job.update(exec=ex["Id"], run_id=run_id, context=context, handle=handle, cwd=cwd,
                    network_inspection_mode=inspection_mode, tmux=f"claude-{run_id}",
                    tmux_socket=f"/run/v3/tmux-{handle}/tmux-0/default")
                self._save_execution(job)
                connection = self.database()
                try:
                    with connection:
                        connection.execute("UPDATE runs SET environment_id=?,environment_generation=?,execution_source=?,runtime_release=? WHERE id=?",
                            (row["environment_id"], row["generation"], source, self.release_id, run_id))
                finally:
                    connection.close()
                self.client.api.exec_start(ex["Id"], detach=True)
                return job["token"], job["token"]
            except Exception:
                self.cleanup(job["token"])
                raise

    def _configure_network_context(self, container, context: dict) -> None:
        """
        切换 CLI 网络监听并核对当前执行的模式与来源。

        :param container: 固定账号容器
        :param context: 当前执行的私有网络上下文
        :return: None
        """
        mode = str(context.get("NETWORK_INSPECTION_MODE") or "passthrough")
        if mode not in NETWORK_INSPECTION_MODES:
            raise ValueError("网络检查模式不合法")
        result = container.exec_run(["/usr/local/bin/v3-network-context"])
        if result.exit_code != 0:
            output = result.output.decode("utf-8", errors="replace") if isinstance(result.output, bytes) else str(result.output or "")
            detail = output.strip().splitlines()
            suffix = f"：{detail[-1][:240]}" if detail else ""
            raise ValueError("网络上下文切换失败，执行未启动" + suffix)
        acknowledgement = container.exec_run(["cat", "/run/v3/context-ack.json"])
        if acknowledgement.exit_code != 0:
            raise ValueError("网络上下文确认不匹配")
        payload = json.loads(acknowledgement.output)
        if (payload.get("QUOTA_SOURCE") != context.get("QUOTA_SOURCE", "")
                or payload.get("NETWORK_INSPECTION_MODE") != mode
                or payload.get("process") != ("passthrough" if mode == "passthrough" else "recorder")):
            raise ValueError("网络上下文确认不匹配")

    def wait_worker(self, container_id: str) -> int:
        """等待本次 exec，而非等待固定容器退出。

        :param container_id: 固定账号容器 ID
        :return: 本次 driver 的退出码
        """
        job = self.job_for_container(container_id)
        while True:
            state = self.client.api.exec_inspect(job["exec"])
            if not state.get("Running"):
                return int(state.get("ExitCode") if state.get("ExitCode") is not None else -1)
            time.sleep(0.5)

    def register_exec(self, token: str, exec_id: str) -> None:
        """将交互执行句柄写入当前代次，支持重启后仅清理 CLI。

        :param token: 绑定执行来源的 token
        :param exec_id: Docker exec 标识
        :return: None
        """
        job = self.job_for_container(token)
        with self.environment_lock(job["row"]["environment_id"]):
            with self.lock:
                if self.jobs.get(job["row"]["environment_id"]) is not job:
                    raise ValueError("执行代次已改变")
            job["exec"] = exec_id
            self._save_execution(job)

    def cleanup(self, container_id: str) -> None:
        """停止本代 driver/子进程并撤销诊断，保留固定容器。

        :param container_id: 带执行来源的完整 token；原始容器 ID 不触发清理
        :return: None
        """
        with self.lock:
            job = next((job for job in self.jobs.values() if job["token"] == container_id), None)
        if not job:
            return
        with self.environment_lock(job["row"]["environment_id"]):
            with self.lock:
                if self.jobs.get(job["row"]["environment_id"]) is not job:
                    return
            commit_path = self._root(job["row"]) / "runtime" / "login-commit.json"
            if commit_path.exists() and json.loads(commit_path.read_text()).get("phase") != "mirrored":
                raise ValueError("重授权提交结果尚未确认，必须先对账")
            container = self._container(job["row"])
            try:
                if job.get("tmux"):
                    container.exec_run(["tmux", "-S", job["tmux_socket"], "kill-server"])
                    processes = container.exec_run(["pgrep", "-f", job["tmux_socket"]])
                    if processes.exit_code == 0:
                        raise ValueError("登录进程尚未收口")
                if job.get("exec"):
                    inspected = self.client.api.exec_inspect(job["exec"])
                    if inspected.get("Running"):
                        pid_path = self._root(job["row"]) / "runtime" / f"job-{job['handle']}.pid"
                        pid = int(pid_path.read_text().strip())
                        if pid > 1:
                            container.exec_run(["kill", "-TERM", "--", f"-{pid}"])
                        else:
                            raise ValueError("执行进程组不合法，拒绝清理其它进程")
                        deadline = time.monotonic() + 10
                        while self.client.api.exec_inspect(job["exec"]).get("Running") and time.monotonic() < deadline:
                            time.sleep(0.1)
                        if self.client.api.exec_inspect(job["exec"]).get("Running"):
                            container.exec_run(["kill", "-KILL", "--", f"-{pid}"])
                            deadline = time.monotonic() + 3
                            while self.client.api.exec_inspect(job["exec"]).get("Running") and time.monotonic() < deadline:
                                time.sleep(0.1)
                            if self.client.api.exec_inspect(job["exec"]).get("Running"):
                                raise ValueError("执行未完成收口，禁止下一 CLI 作业")
                # 一个账号只有一个 CLI 执行，收口该 UID 的全部子进程，防止项目服务器遗留。
                container.exec_run(["pkill", "-TERM", "-u", "1000"])
                deadline = time.monotonic() + 3
                while container.exec_run(["pgrep", "-u", "1000"]).exit_code == 0 and time.monotonic() < deadline:
                    time.sleep(0.1)
                container.exec_run(["pkill", "-KILL", "-u", "1000"])
                if container.exec_run(["pgrep", "-u", "1000"]).exit_code == 0:
                    raise ValueError("账号子进程尚未完成收口，禁止下一 CLI 作业")
                idle_context = {"NETWORK_INSPECTION_MODE": "passthrough", "QUOTA_SOURCE": ""}
                atomic_json(self._root(job["row"]) / "runtime" / "context.json", idle_context)
                self._configure_network_context(container, idle_context)
                if "hooks_before" in job:
                    settings = self._root(job["row"]) / "home" / ".claude" / "settings.json"
                    value = json.loads(settings.read_text()) if settings.exists() else {}
                    if job["hooks_before"] is None:
                        value.pop("hooks", None)
                    else:
                        value["hooks"] = job["hooks_before"]
                    atomic_json(settings, value)
                    os.chown(settings, 1000, 1000)
                if job.get("tmux") and job.get("home", "/home/node") != "/home/node" and job["account"].get("cc2api_account_id") is not None:
                    # RT 必须在释放排他门禁前销毁，避免普通 CLI 形成第二条刷新链。
                    shutil.rmtree(self._root(job["row"]) / "home" / ".v3-login" / job["tmux"], ignore_errors=False)
                self.release(job)
            except Exception:
                try:
                    self._isolate_job(job)
                finally:
                    with self.lock:
                        self.jobs.pop(job["row"]["environment_id"], None)
                raise

    def execution_flows(self, account: dict, source: str, flows: Path) -> Path:
        """取得固定证据组内的分代目录，额度恢复不改写兼容入口。

        :param account: 当前账号
        :param source: 当前 run/续聊执行来源
        :param flows: 账号下原 run/续聊的兼容目录
        :return: Recorder 与额度游标共同使用的本代本地目录
        """
        relative = flows.relative_to(self.data / "flows" / account["name"])
        if ".." in relative.parts or not relative.parts:
            raise ValueError("证据目录不属于当前账号")
        row = self._row(account["name"], account["id"])
        with self.environment_lock(row["environment_id"]):
            group = self._root(row) / "flows" / ("group-" + hashlib.sha256(str(relative).encode()).hexdigest()[:20])
            group.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._link_directory(flows, group)
            # 保留每代原生 flow，不能用复制或共享文件让新 Recorder 覆盖旧证据。
            execution = group / "executions" / hashlib.sha256(source.encode()).hexdigest()[:20]
            execution.mkdir(parents=True, exist_ok=True, mode=0o700)
            return execution

    @staticmethod
    def _link_directory(path: Path, destination: Path) -> None:
        """将 v3 兼容入口固定到唯一数据目录，禁止改写指向其它目录的链接。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            if path.resolve() != destination.resolve():
                raise ValueError("数据目录绑定冲突")
            return
        if path.exists():
            shutil.copytree(path, destination, dirs_exist_ok=True)
            shutil.rmtree(path)
        path.symlink_to(os.path.relpath(destination, path.parent), target_is_directory=True)

    def _project_view(self, row: dict, run_id: str) -> str:
        """
        为 run 创建不暴露内部 ID 的固定容器项目别名。

        :param row: 固定环境行
        :param run_id: 内部运行 ID
        :return: 容器内项目 cwd
        """
        alias = "project-" + hashlib.sha256(f"{row['environment_id']}:{run_id}".encode()).hexdigest()[:12]
        root = self._root(row)
        projects = root / "projects"
        compatibility_root = root / "workspaces"
        projects.mkdir(parents=True, exist_ok=True)
        compatibility_root.mkdir(parents=True, exist_ok=True)
        os.chown(projects, 1000, 1000)
        view = projects / alias
        compatibility = compatibility_root / run_id
        if compatibility.is_symlink():
            if compatibility.resolve() != view.resolve():
                raise ValueError("项目兼容入口绑定冲突")
        elif view.exists():
            if compatibility.exists() and any(compatibility.iterdir()):
                raise ValueError("项目别名与旧工作目录同时存在")
            if compatibility.exists():
                compatibility.rmdir()
            compatibility.symlink_to(os.path.relpath(view, compatibility.parent), target_is_directory=True)
        elif compatibility.exists():
            # 实际 cwd 必须位于匿名目录；保留 run ID 路径只供宿主兼容读取。
            compatibility.rename(view)
            compatibility.symlink_to(os.path.relpath(view, compatibility.parent), target_is_directory=True)
        else:
            view.mkdir(mode=0o755)
            os.chown(view, 1000, 1000)
            compatibility.symlink_to(os.path.relpath(view, compatibility.parent), target_is_directory=True)
        cwd = f"/home/node/projects/{alias}"
        configuration = self._root(row) / "home" / ".claude.json"
        if configuration.is_file():
            value = json.loads(configuration.read_text())
            projects = value.get("projects") if isinstance(value.get("projects"), dict) else {}
            project = projects.get(cwd) if isinstance(projects.get(cwd), dict) else {}
            # 这里只信任本系统为当前任务创建的专属目录，避免首屏确认吞掉原题。
            value["projects"] = {**projects, cwd: {**project, "hasTrustDialogAccepted": True}}
            atomic_json(configuration, value)
            os.chown(configuration, 1000, 1000)
        return cwd

    def _session_view(self, row: dict, run_id: str, cwd: str | None = None) -> None:
        """
        把持久 HOME 的 Claude session 映射到历史 workspace 兼容视图。

        :param row: 固定环境行
        :param run_id: 内部运行 ID
        :param cwd: 当前容器项目目录
        :return: None
        """
        home = self._root(row) / "home"
        project_key = (cwd or f"/workspaces/{run_id}").replace("/", "-")
        project = home / ".claude" / "projects" / project_key
        project.mkdir(parents=True, exist_ok=True)
        os.chown(project, 1000, 1000)
        for parent in (project.parent, project.parent.parent):
            os.chown(parent, 1000, 1000)

        # 旧兼容层曾把 .claude-home 写进项目树；只移除本系统创建且仍指向当前 session 的链接。
        legacy_home = self._root(row) / "workspaces" / run_id / ".claude-home"
        legacy_view = legacy_home / "projects" / "-workspace"
        if legacy_view.is_symlink() and legacy_view.resolve() == project.resolve():
            legacy_view.unlink()
            for directory in (legacy_view.parent, legacy_home):
                try:
                    directory.rmdir()
                except OSError:
                    break

    def run_session_path(self, run_id: str) -> Path:
        """
        解析 v3 run 的持久 Claude 主 session 目录。

        :param run_id: runs.id
        :return: 固定 HOME 下不进入项目树的 session 目录
        """
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
            raise ValueError("运行 ID 不合法")
        connection = self.database()
        try:
            record = connection.execute("SELECT environment_id FROM runs WHERE id=?", (run_id,)).fetchone()
            row = connection.execute(
                "SELECT * FROM account_environments WHERE environment_id=?",
                (record["environment_id"],),
            ).fetchone() if record and record["environment_id"] else None
        finally:
            connection.close()
        if not row:
            return self.data / "missing-run-session" / run_id
        row = dict(row)
        alias = "project-" + hashlib.sha256(f"{row['environment_id']}:{run_id}".encode()).hexdigest()[:12]
        project_key = f"/home/node/projects/{alias}".replace("/", "-")
        return self._root(row) / "home" / ".claude" / "projects" / project_key

    def run_artifact_path(self, run_id: str, name: str) -> Path:
        """
        解析 v3 run 的受限状态或 transcript 文件。

        :param run_id: runs.id
        :param name: `status.json`、`transcript.log` 或 `session-baseline.json`
        :return: 环境 runtime 下的文件路径
        """
        if name not in {"status.json", "transcript.log", "session-baseline.json",
                "oauth-refresh-request.json", "oauth-refresh-result.json"}:
            raise ValueError("运行产物名称不合法")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
            raise ValueError("运行 ID 不合法")
        connection = self.database()
        try:
            row = connection.execute("SELECT environment_id FROM runs WHERE id=?", (run_id,)).fetchone()
        finally:
            connection.close()
        if not row or not row["environment_id"]:
            return self.data / "missing-run-artifact" / run_id / name
        return self.data / "environments" / row["environment_id"] / "runtime" / "runs" / run_id / name

    def _make_room(self, requested: dict) -> None:
        running = self.client.containers.list(filters={"label": ["vibebench.product=v3",
            f"vibebench.deployment={self.deployment}", "vibebench.role=account"]})
        if len(running) < self.limit:
            return
        connection = self.database()
        try:
            rows = [dict(row) for row in connection.execute("SELECT * FROM account_environments")]
            for row in rows:
                if row["environment_id"] == requested["environment_id"]:
                    continue
                guard = self.environment_lock(row["environment_id"])
                # 不等待另一个正在准备的账号锁，避免两个环境相互等待资源预算。
                if not guard.acquire(blocking=False):
                    continue
                try:
                    with self.lock:
                        busy = row["environment_id"] in self.jobs
                    if busy or row["container_id"] not in {container.id for container in running}:
                        continue
                    account = connection.execute("SELECT * FROM accounts WHERE id=?", (row["account_id"],)).fetchone()
                    account = dict(account) if account else {"name": row["name"]}
                    try:
                        job = self.claim(row, account, f"idle:{uuid.uuid4().hex}", idle_only=True, exclusive=True)
                    except (ValueError, RuntimeError):
                        continue
                    self._container(row).stop(timeout=5)
                    self._update(row, state="stopped")
                    (self._root(row) / "runtime" / "execution.json").unlink(missing_ok=True)
                    self._lease(job, "release")
                    with self.lock:
                        self.jobs.pop(row["environment_id"], None)
                    return
                finally:
                    guard.release()
        finally:
            connection.close()
        raise ValueError("已达到 v3 活跃环境预算且没有可停止的空闲账号")

    def begin_login(self, sid: str, account: dict, version: str, force: bool) -> tuple[dict, object, Path, str]:
        """在固定环境创建 tmux 登录；重授权使用同环境内的暂存 HOME。

        :param sid: 登录会话 ID
        :param account: 账号草稿或已存在账号
        :param version: 精确 CLI 版本
        :param force: 是否保护旧凭据
        :return: 环境、容器、登录 profile、本次 HOME
        """
        with self._cli_setup(account, f"login:{sid}", version, exclusive=True,
            allow_inactive_login=force and account.get("cc2api_account_id") is not None) as (row, container, job):
            idle_context = {"NETWORK_INSPECTION_MODE": "passthrough", "QUOTA_SOURCE": f"login:{sid}"}
            atomic_json(self._root(row) / "runtime" / "context.json", idle_context)
            self._configure_network_context(container, idle_context)
            home = self._root(row) / "home"
            cli_home = "/home/node"
            if force:
                staged = home / ".v3-login" / sid
                staged.mkdir(parents=True, exist_ok=True)
                for source in (home / ".claude.json", home / ".claude" / "settings.json"):
                    if source.exists():
                        target = staged / (".claude.json" if source.name == ".claude.json" else ".claude/settings.json")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                top = staged / ".claude.json"
                if top.exists():
                    configuration = json.loads(top.read_text())
                    # 只保留设备与本地设置；新身份必须由本次 CLI 登录重新写出。
                    configuration.pop("oauthAccount", None)
                    atomic_json(top, configuration)
                home = staged
                cli_home = f"/home/node/.v3-login/{sid}"
            profile = home / ".claude"
            profile.mkdir(exist_ok=True)
            for current, dirs, files in os.walk(home if force else profile):
                os.chown(current, 1000, 1000)
                for name in files:
                    os.chown(Path(current) / name, 1000, 1000)
            if force:
                os.chown(home.parent, 1000, 1000)
            socket_path = f"/tmp/v3-login-{sid}.sock"
            command = ["setpriv", "--reuid=1000", "--regid=1000", "--init-groups", "--bounding-set=-all",
                "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs", "env", f"HOME={cli_home}",
                f"PATH=/cli/{version}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin",
                "claude", "auth", "login"]
            try:
                job.update(tmux=sid, tmux_socket=socket_path, home=cli_home, version=version)
                self._save_execution(job)
                result = container.exec_run(["tmux", "-S", socket_path, "new-session", "-d", "-s", sid,
                    "-x", "120", "-y", "36", shlex.join(command) + "; sleep 86400"])
                if result.exit_code:
                    raise ValueError("tmux 登录启动失败")
                return row, container, profile, cli_home
            except Exception:
                self.release(job)
                raise

    @staticmethod
    def cli_command(command: list[str]) -> list[str]:
        """生成去掉所有能力的非 root CLI 命令。

        :param command: 实际 argv
        :return: 不经过字符串拼接的 setpriv argv
        """
        return ["setpriv", "--reuid=1000", "--regid=1000", "--init-groups", "--bounding-set=-all",
            "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs", "--", *command]

    def exec_cli(self, container_id: str, command: list[str], home: str, version: str):
        """在 passthrough 网络中执行短期 CLI 子命令。

        :param container_id: 本部署固定容器
        :param command: CLI argv
        :param home: 当前执行 HOME
        :param version: 精确版本
        :return: Docker ExecResult
        """
        job = self.job_for_container(container_id)
        return self._container(job["row"]).exec_run(self.cli_command(command),
            environment={"HOME": home, "PATH": f"/cli/{version}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin"},
            workdir=home)

    def job_for_container(self, container_id: str) -> dict:
        """按容器或执行 token 找当前执行；异步回调必须传入带来源的 token。

        :param container_id: 固定容器 ID
        :return: 当前执行句柄
        """
        with self.lock:
            job = next((job for job in self.jobs.values() if job["token"] == container_id
                or (":" not in container_id and job["row"]["container_id"] == container_id)), None)
        if not job:
            raise ValueError("账号执行已过期")
        return job

    def commit_login(self, session, account_id: int) -> None:
        """提交暂存登录配置，并把环境绑定到不可变账号 ID。

        :param session: 已通过登录校验的 LoginSession
        :param account_id: bench 账号 ID
        :return: None
        """
        job = self.job_for_container(self.execution_token(session.worker_id, f"login:{session.sid}"))
        row = self._row(session.name, account_id)
        destination = self._root(row) / "home"
        for relative in (".claude.json", ".claude/.credentials.json", ".claude/settings.json"):
            source = session.profile_dir.parent / relative
            target = destination / relative
            if source.exists() and source.resolve() != target.resolve():
                atomic_json(target, json.loads(source.read_text()))
                os.chown(target, 1000, 1000)
        if row["state"] == "profile_reauth":
            self._update(row, state="ready")
        job["row"] = row

    def login_commit_context(self, session) -> dict:
        """取得本次登录的固定环境和受控提交记录位置。

        :param session: 当前登录会话
        :return: 环境、租约与 root 私有记录路径
        """
        job = self.job_for_container(self.execution_token(session.worker_id, f"login:{session.sid}"))
        return {"environment_id": job["row"]["environment_id"], "generation": job["row"]["generation"],
            "lease": dict(job["lease"] or {}), "path": self._root(job["row"]) / "runtime" / "login-commit.json"}

    def capture_login_pane(self, session) -> str:
        """读取原 tmux 的有界输出，浏览器断线不会丢失授权链接。

        :param session: 当前登录会话
        :return: 仅供链接提取的屏幕文本，不记录终端全文
        """
        job = self.job_for_container(self.execution_token(session.worker_id, f"login:{session.sid}"))
        result = self._container(job["row"]).exec_run(["tmux", "-S", job["tmux_socket"],
            "capture-pane", "-p", "-J", "-S", "-200"])
        if result.exit_code:
            raise ValueError("登录终端已结束")
        return result.output[-65536:].decode("utf-8", errors="replace")

    def login_terminal_alive(self, session) -> bool:
        """区分仍等待授权的 CLI 与用于保留屏幕的 sleep。

        :param session: 当前登录会话
        :return: CLI/tmux 尚未结束时为 True
        """
        job = self.job_for_container(self.execution_token(session.worker_id, f"login:{session.sid}"))
        result = self._container(job["row"]).exec_run(["tmux", "-S", job["tmux_socket"],
            "display-message", "-p", "-t", session.sid, "#{pane_current_command}"])
        return result.exit_code == 0 and result.output.strip() != b"sleep"

    def send_login_code(self, session, request_id: str, code: str) -> None:
        """经 stdin 向原登录 tmux 投递一次授权码；调用方持有 owner 锁。

        :param session: 当前登录会话
        :param request_id: 已校验的无秘密请求标识
        :param code: 已校验的完整授权码，仅用于 stdin
        :return: None；投递前拒绝为 ValueError，投递结果未知为 RuntimeError
        """
        token = self.execution_token(session.worker_id, f"login:{session.sid}")
        job = self.job_for_container(token)
        with self.environment_lock(job["row"]["environment_id"]):
            if self.job_for_container(token) is not job or job.get("heartbeat_failed"):
                raise ValueError("原登录执行已失效，请刷新状态")
            row = job["row"]
            connection = self.database()
            try:
                current = connection.execute("SELECT * FROM account_environments WHERE environment_id=?", (row["environment_id"],)).fetchone()
            finally:
                connection.close()
            proof = json.loads((self._root(row) / "runtime" / "execution.json").read_text())
            if (not current or current["generation"] != row["generation"] or current["container_id"] != session.worker_id
                or current["state"] in ("reconcile", "cli_reconcile") or proof.get("source") != f"login:{session.sid}"
                or proof.get("generation") != row["generation"] or proof.get("container_id") != session.worker_id
                or proof.get("tmux") != session.sid or proof.get("tmux_socket") != job.get("tmux_socket")
                or job.get("tmux") != session.sid or session.phase != "authorizing" or not self.login_terminal_alive(session)):
                raise ValueError("原登录终端或环境已改变，请重新检查登录状态")
            container = self._container(row)
            command = ["tmux", "-S", job["tmux_socket"]]
            stream = None
            try:
                # code 不进入 argv 或文件；半关闭 stdin 让 load-buffer 确认 EOF 后再 paste。
                execution = self.client.api.exec_create(container.id,
                    command + ["load-buffer", "-b", request_id, "-"], stdin=True, tty=False, user="root")
                stream = self.client.api.exec_start(execution["Id"], socket=True, tty=False)
                raw = getattr(stream, "_sock", None) or stream
                raw.settimeout(5)
                raw.sendall(code.encode("utf-8"))
                raw.shutdown(SHUT_WR)
                while raw.recv(4096):
                    pass
                inspected = self.client.api.exec_inspect(execution["Id"])
                if inspected.get("Running") or inspected.get("ExitCode") != 0:
                    raise RuntimeError("输入缓冲结果未确认")
                result = container.exec_run(command + ["paste-buffer", "-b", request_id, "-t", session.sid])
                if result.exit_code:
                    raise RuntimeError("终端投递结果未确认")
                result = container.exec_run(command + ["send-keys", "-t", session.sid, "Enter"])
                if result.exit_code:
                    raise RuntimeError("终端确认结果未确认")
            except Exception:
                # paste/Enter 可能已发生，任何错误均不能驱动自动重放。
                raise RuntimeError("发送结果未知，请查询回执和 CLI 状态，勿重复发送") from None
            finally:
                try:
                    try:
                        if stream is not None:
                            stream.close()
                    finally:
                        result = container.exec_run(command + ["delete-buffer", "-b", request_id])
                        if result.exit_code:
                            raise RuntimeError("临时输入清理未确认")
                except Exception:
                    # 清理也发生在可能投递之后，不能被外层误判为“尚未发送”。
                    raise RuntimeError("临时输入清理未确认，请检查环境，勿重复发送") from None

    def recover_login(self, sid: str, account: dict, version: str, home: str) -> tuple[dict, object]:
        """认领重启后保留的产物，只检查认证，不伪造旧 tmux。

        :param sid: 新的维护会话 ID
        :param account: 原草稿配置
        :param version: 原 CLI 版本
        :param home: 已校验的原容器 HOME
        :return: 原环境与容器
        """
        with self._cli_setup(account, f"login:{sid}", version, exclusive=True) as (row, container, job):
            idle_context = {"NETWORK_INSPECTION_MODE": "passthrough", "QUOTA_SOURCE": f"login:{sid}"}
            atomic_json(self._root(row) / "runtime" / "context.json", idle_context)
            self._configure_network_context(container, idle_context)
            job.update(home=home, version=version)
            self._save_execution(job)
            return row, container

    def finish_bound_login(self, record: dict, snapshot: dict) -> None:
        """镜像已确认的权威凭据，主 HOME 永远不发布 RT。

        :param record: root 私有的已验证提交记录
        :param snapshot: cc2api 同一账号当前凭据
        :return: None；任何不完整写入保留记录供重试
        """
        connection = self.database()
        try:
            existing = connection.execute("SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL", (record["account_id"],)).fetchone()
        finally:
            connection.close()
        if not existing or existing["name"] != record["name"] or existing["cc2api_account_id"] != record["cc2api_account_id"]:
            raise ValueError("重授权的原关联账号已改变")
        account = dict(existing)
        row = self._row(account["name"], account["id"])
        if row["environment_id"] != record["environment_id"] or snapshot.get("account_id") != account["cc2api_account_id"]:
            raise ValueError("重授权环境或凭据归属不匹配")
        profile = self.data / "profiles" / account["name"]
        credentials_path = profile / ".credentials.json"
        credentials = json.loads(credentials_path.read_text())
        oauth = credentials.get("claudeAiOauth")
        if not isinstance(oauth, dict) or any(not isinstance(snapshot.get(key), str) or not snapshot[key]
            for key in ("access_token", "refresh_token")) or type(snapshot.get("expires_at")) is not int:
            raise ValueError("权威凭据不完整，重授权尚未完成")
        oauth.update(accessToken=snapshot["access_token"], refreshToken=snapshot["refresh_token"], expiresAt=snapshot["expires_at"])
        atomic_json(credentials_path, credentials)
        os.chown(credentials_path, 1000, 1000)
        home = self._root(row) / "home"
        identity = record["identity"]
        for top in (profile / ".claude.json", home / ".claude.json"):
            value = json.loads(top.read_text()) if top.exists() else {}
            oauth_account = value.setdefault("oauthAccount", {})
            # 只更新经验证的登录身份，保留 userID 等原设备字段与本地配置。
            for source, target in (("email", "emailAddress"), ("account_uuid", "accountUuid"), ("organization_uuid", "organizationUuid")):
                if identity.get(source):
                    oauth_account[target] = identity[source]
            atomic_json(top, value)
            os.chown(top, 1000, 1000)
        self.sync_credentials(row, account)
        record["phase"] = "mirrored"
        atomic_json(self._root(row) / "runtime" / "login-commit.json", record)

    def begin_continue(self, account: dict, run: dict, sid: str, context: dict, flows: Path) -> tuple[str, str]:
        """在原工作目录领取续聊，不复制整个账号 HOME。

        :param account: 当前账号
        :param run: 原 run 快照
        :param sid: 续聊会话
        :param context: 被动额度上下文
        :param flows: 当前续聊证据目录
        :return: 当前执行 token 的兼容二元组
        """
        version = run.get("claude_code_version") or os.environ.get("CLAUDE_CODE_VERSION", "2.1.280")
        with self._cli_setup(account, context["QUOTA_SOURCE"], version) as (row, container, job):
            try:
                self.sync_credentials(row, account)
                cwd = self._project_view(row, run["id"])
                self._session_view(row, run["id"], cwd)
                handle = hashlib.sha256(context["QUOTA_SOURCE"].encode()).hexdigest()[:20]
                root = self._root(row)
                flow_directory = self.execution_flows(account, context["QUOTA_SOURCE"], flows)
                flow_path = "/flows/" + str(flow_directory.relative_to(root / "flows"))
                control = root / "controls" / handle
                control.mkdir(parents=True, exist_ok=True, mode=0o750)
                self._link_directory(self.data / "quota-controls" / run["id"] / handle, control)
                context = dict(context, STATS_FILE=f"{flow_path}/stats.jsonl",
                    QUOTA_SIGNAL_FILE=f"/controls/{handle}/pause.json",
                    QUOTA_STATE_FILE=f"/quota-accounts/{account['id']}/state.json",
                    QUOTA_OBSERVATIONS_FILE=f"{flow_path}/passive-quota.jsonl",
                    QUOTA_CREDENTIALS_FILE="/home/node/.claude/.credentials.json",
                    NETWORK_INSPECTION_MODE="capture" if run.get("capture_full_http") else "passthrough")
                if run.get("capture_full_http"):
                    context.update(CAPTURE_FULL_HTTP="1", SAVE_FULL_FLOWS="1",
                        CAPTURE_FILE=f"{flow_path}/http_capture.jsonl", CAPTURE_INDEX_FILE=f"{flow_path}/capture_index.json")
                atomic_json(root / "runtime" / "context.json", context)
                self._configure_network_context(container, context)
                job.update(run_id=run["id"], handle=handle, version=version, cwd=cwd,
                    network_inspection_mode=context["NETWORK_INSPECTION_MODE"])
                self._save_execution(job)
                return job["token"], job["token"]
            except Exception:
                self.cleanup(job["token"])
                raise

    def reprofile_blocker(self, row: dict) -> str | None:
        """
        判断 legacy 环境是否可以安全旋转到 profile v2。

        :param row: account_environments 行
        :return: 可校正时为 None，否则返回稳定阻塞原因
        """
        if row.get("account_id") is None:
            return "未提交登录草稿不能校正正式账号画像"
        fingerprint = json.loads(row["fingerprint_json"])
        if int(fingerprint.get("profile_version") or 1) >= 2:
            return "账号已经使用固定 profile v2，禁止再次旋转设备画像"
        with self.lock:
            if row["environment_id"] in self.jobs:
                return "环境仍有活动 CLI 作业"
        connection = self.database()
        try:
            account = connection.execute("SELECT * FROM accounts WHERE id=?", (row["account_id"],)).fetchone()
            if not account:
                return "环境没有可用正式账号"
            if account["cc2api_account_id"] is not None:
                return "账号已绑定 cc2api，请先解除绑定"
            tables = {item["name"] for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("tasks", "runs"):
                if table in tables and connection.execute(
                    f"SELECT 1 FROM {table} WHERE account_id=? LIMIT 1", (row["account_id"],)
                ).fetchone():
                    return "账号已有任务或运行历史，禁止旋转设备画像"
        finally:
            connection.close()
        root = self._root(row)
        if (root / "runtime" / "identity.json").exists():
            return "环境已经观测设备身份，禁止旋转"
        if any((root / "runtime" / name).exists() for name in ("login-commit.json", "execution.json")):
            return "环境仍有登录提交或执行记录"
        if (self.data / "login-drafts" / f"{row['environment_id']}.json").exists():
            return "环境仍有登录草稿"
        if row.get("container_id"):
            try:
                container = self._container(row)
                container.reload()
                if container.status == "running":
                    return "账号容器仍在运行，请先停止"
            except NotFound:
                pass
        return None

    def maintenance(self, environment_id: str, operation: str) -> None:
        """空闲维护本部署环境，保留 HOME 和已确认身份。

        :param environment_id: 不可变环境 ID
        :param operation: stop、rebuild、reprofile 或 reconcile
        :return: None；活动作业和 API 请求拒绝维护
        """
        if operation not in ("stop", "rebuild", "reprofile", "reconcile"):
            raise ValueError("维护操作不合法")
        with self.environment_lock(environment_id):
            connection = self.database()
            try:
                record = connection.execute("SELECT * FROM account_environments WHERE environment_id=?", (environment_id,)).fetchone()
                if not record:
                    raise ValueError("环境不存在")
                row = dict(record)
                account = connection.execute("SELECT * FROM accounts WHERE id=?", (row["account_id"],)).fetchone()
            finally:
                connection.close()
            account = dict(account) if account else {"name": row["name"]}
            if operation == "reprofile":
                blocker = self.reprofile_blocker(row)
                if blocker:
                    raise ValueError(blocker)
                try:
                    container = self._container(row) if row.get("container_id") else None
                except NotFound:
                    container = None
                if container:
                    container.remove()
                fingerprint = self.fingerprint(account.get("timezone"))
                previous = json.loads(row["fingerprint_json"])
                fingerprint["mem"] = previous.get("mem", os.environ.get("V3_ACCOUNT_MEMORY", "4g"))
                fingerprint["swap"] = previous.get("swap", "0")
                account_limits(str(fingerprint["mem"]), str(fingerprint["swap"]))
                root = self._root(row)
                shutil.rmtree(root / "ca", ignore_errors=True)
                (root / "ca").mkdir(parents=True, exist_ok=True, mode=0o700)
                for name in ("sender.json", "context.json", "context-ack.json", "network.pid", "mitm.pid",
                        "ready", "cli-unhealthy", "proxy-ip"):
                    (root / "runtime" / name).unlink(missing_ok=True)
                self._update(row, fingerprint_json=json.dumps(fingerprint), container_id=None, state="stopped")
                return
            if operation == "reconcile" and (self._root(row) / "runtime" / "login-commit.json").exists():
                self.reconcile(environment_id)
                if (self._root(row) / "runtime" / "login-commit.json").exists():
                    raise ValueError("重授权提交结果仍需对账，暂存和门禁已保留")
                return
            if environment_id in self.jobs:
                raise ValueError("环境正在执行工作")
            if operation == "reconcile" and row["state"] == "cli_reconcile":
                self.reconcile(environment_id)
                if self._row(row["name"], row["account_id"])["state"] == "cli_reconcile":
                    raise ValueError("CLI 对账未完成，独立 API 环境保持运行")
                return
            if operation == "reconcile" and row["state"] == "profile_reauth_reconcile":
                self.reconcile(environment_id)
                if self._row(row["name"], row["account_id"])["state"] in ("profile_reauth_reconcile", "reconcile", "cli_reconcile"):
                    raise ValueError("遗留执行对账未完成")
                return
            job = None
            if operation != "reconcile":
                job = self.claim(row, account, f"maintenance:{uuid.uuid4().hex}", idle_only=True, exclusive=True)
            else:
                account_id = account.get("cc2api_account_id")
                if account_id is not None:
                    snapshot = self.gateway._request("GET", f"/admin/runtime/accounts/{account_id}/lease")
                    if snapshot["active"]:
                        raise ValueError("API 仍有活动请求，拒绝对账")
            try:
                container = self._container(row) if row.get("container_id") else None
            except NotFound:
                container = None
            if container:
                container.stop(timeout=5)
                if operation == "rebuild":
                    container.remove()
            if job:
                self._lease(job, "release")
                with self.lock:
                    self.jobs.pop(environment_id, None)
            elif account.get("cc2api_account_id") is not None and snapshot["lease"]:
                lease = snapshot["lease"]
                self.gateway._request("POST", f"/admin/runtime/accounts/{account['cc2api_account_id']}/lease",
                    {"operation": "release", "owner": lease["owner"], "generation": lease["generation"]})
            (self._root(row) / "runtime" / "execution.json").unlink(missing_ok=True)
            self._update(row, state="stopped", **({"container_id": None} if operation == "rebuild" else {}))

    def identity_import(self, account: dict, version: str) -> dict:
        """导出实际 CLI 请求确认的设备字段及可测量的基础环境。

        :param account: 新导入的 bench 账号
        :param version: 当前 CLI 基础版本
        :return: 无凭据的身份载荷；缺少证据时阻止导入
        """
        row, container = self.ensure(account, version)
        identity_file = self._root(row) / "runtime" / "identity.json"
        if not identity_file.exists():
            raise ValueError("设备身份尚未确认：请先在该固定环境完成一次 CLI 任务，再同步账号")
        identity = json.loads(identity_file.read_text())
        if identity.get("conflict") or not re.fullmatch(r"[a-f0-9]{64}", identity.get("device_id", "")):
            raise ValueError("客户端设备身份存在冲突，已阻止同步")
        top = self._root(row) / "home" / ".claude.json"
        oauth_account = json.loads(top.read_text()).get("oauthAccount", {}) if top.exists() else {}
        if not identity.get("account_uuid") or identity["account_uuid"] != oauth_account.get("accountUuid"):
            raise ValueError("观测设备身份与当前登录账号归属不一致，已阻止同步")
        probe = '''const os=require('os');const fs=require('fs');const distro=Object.fromEntries(fs.readFileSync('/etc/os-release','utf8').split('\\n').filter(x=>x.includes('=')).map(x=>{const i=x.indexOf('=');return[x.slice(0,i),x.slice(i+1).replace(/^"|"$/g,'')]}));console.log(JSON.stringify({platform_raw:process.platform,arch:process.arch,node_version:process.version,linux_distro_id:distro.ID||'',linux_distro_version:distro.VERSION_ID||'',linux_kernel:os.release()}));'''
        result = container.exec_run(self.cli_command(["node", "-e", probe]))
        if result.exit_code:
            raise ValueError("实际基础环境读取失败")
        environment = json.loads(result.output)
        environment.update(platform="Linux", terminal="tmux", package_managers="npm", runtimes="node",
            version=version, version_base=version, build_time="", deployment_environment="", vcs="git")
        return {"device_id": identity["device_id"], "environment_id": row["environment_id"],
            "source": identity["source"], "canonical_env": environment,
            "canonical_prompt": {"platform": "linux", "shell": "bash", "os_version": environment["linux_kernel"],
                "working_dir": "/home/node"}}

    def reconcile(self, environment_id: str | None = None) -> None:
        """启动时按持久模式收口遗留执行，共享 CLI 保留独立 API。

        :param environment_id: 可选的单环境对账范围
        :return: None；未知门禁保持隔离
        """
        connection = self.database()
        try:
            rows = [dict(row) for row in connection.execute("SELECT * FROM account_environments")]
        finally:
            connection.close()
        for row in rows:
            if environment_id is not None and row["environment_id"] != environment_id:
                continue
            record = self._root(row) / "runtime" / "execution.json"
            shared = row["state"] == "cli_reconcile"
            # 历史画像校正状态按正常对账收口，失败仍保留真实执行和提交门禁。
            settled_state = None
            try:
                container = self._container(row) if row["container_id"] else None
            except NotFound:
                container = None
            try:
                commit_path = self._root(row) / "runtime" / "login-commit.json"
                if commit_path.exists():
                    self._reconcile_login_import(row, container, commit_path)
                    continue
                if record.exists():
                    execution = json.loads(record.read_text())
                    shared = execution.get("exclusive") is False
                    if shared:
                        if execution.get("container_id") != row["container_id"] or execution.get("generation") != row["generation"]:
                            raise ValueError("遗留 CLI 记录与当前容器代次不一致")
                        lease = execution.get("lease")
                        if lease:
                            path = f"/admin/runtime/accounts/{execution['account_id']}/lease"
                            current = self.gateway._request("GET", path)["lease"]
                            if current and (current["owner"] != lease["owner"] or current["generation"] != lease["generation"] or current.get("exclusive", True)):
                                raise ValueError("遗留 CLI 记录与当前租约不一致")
                            lease = current
                        job = {"row": row, "account": {"cc2api_account_id": execution.get("account_id")},
                            "source": execution["source"], "lease": lease, "exclusive": False, "claimed": True,
                            "token": self.execution_token(row["container_id"] or row["environment_id"], execution["source"])}
                        for key in ("exec", "handle", "tmux", "tmux_socket", "hooks_before"):
                            if key in execution:
                                job[key] = execution[key]
                        with self.environment_lock(row["environment_id"]):
                            with self.lock:
                                if row["environment_id"] in self.jobs:
                                    continue
                                self.jobs[row["environment_id"]] = job
                            if container:
                                container.reload()
                            if container and container.status == "running":
                                self.cleanup(job["token"])
                                self._update(row, state=settled_state or "ready")
                            else:
                                job["exec"] = None
                                self.release(job)
                                self._update(row, state=settled_state or "stopped")
                        continue
                    if container:
                        container.stop(timeout=5)
                    if execution.get("lease"):
                        lease = execution["lease"]
                        path = f"/admin/runtime/accounts/{execution['account_id']}/lease"
                        current = self.gateway._request("GET", path)
                        if current["lease"]:
                            self.gateway._request("POST", path, {"operation": "release", "owner": lease["owner"], "generation": lease["generation"]})
                    record.unlink()
                    self._update(row, state=settled_state or "stopped")
                else:
                    # 管理服务重启不应截断账号内已接受的 API/SSE；只有遗留 CLI 执行才收口容器。
                    connection = self.database()
                    try:
                        account = connection.execute("SELECT * FROM accounts WHERE id=?", (row["account_id"],)).fetchone()
                    finally:
                        connection.close()
                    if account and account["cc2api_account_id"] is not None:
                        current = self.gateway._request("GET", f"/admin/runtime/accounts/{account['cc2api_account_id']}/lease")
                        if current["lease"]:
                            shared = current["lease"].get("exclusive") is False
                            raise ValueError("存在没有本地执行记录的门禁，需人工对账")
                    if container:
                        container.reload()
                        if shared and container.status == "running" and (self._root(row) / "runtime" / "cli-unhealthy").exists():
                            idle_context = {"NETWORK_INSPECTION_MODE": "passthrough", "QUOTA_SOURCE": ""}
                            atomic_json(self._root(row) / "runtime" / "context.json", idle_context)
                            self._configure_network_context(container, idle_context)
                    self._update(row, state=settled_state or (
                        "ready" if container and container.status == "running" else "stopped"))
            except Exception:
                state = "cli_reconcile" if shared else "reconcile"
                self._update(row, state=state)

    def _reconcile_login_import(self, row: dict, container, path: Path) -> None:
        """撤销迟到提交权限后对账；结果未知时保持门禁和暂存。

        :param row: 固定环境
        :param container: 该环境原容器
        :param path: root 私有提交记录
        :return: None；不能确认时抛出异常并由调用方保留 reconcile
        """
        with self.environment_lock(row["environment_id"]):
            record = json.loads(path.read_text())
            if record.get("environment_id") != row["environment_id"] or not re.fullmatch(r"[a-f0-9]{12}", record.get("sid", "")):
                raise ValueError("重授权提交记录归属不合法")
            with self.lock:
                job = self.jobs.pop(row["environment_id"], None)
            if job:
                # 等待已经在途的心跳退出；移除作业后不会再启动新的续租。
                with job["lease_lock"]:
                    pass
            lease_path = f"/admin/runtime/accounts/{record['cc2api_account_id']}/lease"
            current = self.gateway._request("GET", lease_path)
            lease = current.get("lease")
            if lease:
                if lease["owner"] != record["lease"]["owner"] or lease["generation"] != record["lease"]["generation"]:
                    raise ValueError("重授权门禁已由其他代次接管")
            else:
                lease = self.gateway._request("POST", lease_path, {"operation": "prepare", "owner": f"login:{record['sid']}"})["lease"]
                record["lease"] = lease
                atomic_json(path, record)
            self.gateway._request("POST", lease_path, {"operation": "fence", "owner": lease["owner"], "generation": lease["generation"]})
            current = self.gateway._request("GET", lease_path)
            if current.get("active") or self._running_sender_active(row):
                raise ValueError("重授权对账等待现有 API 收口")
            if container:
                container.stop(timeout=5)
            snapshot = self.gateway.import_status(record["cc2api_account_id"], record["operation_id"])
            if snapshot is not None:
                self.finish_bound_login(record, snapshot)
            staged = self._root(row) / "home" / ".v3-login" / record["sid"]
            if staged.exists():
                shutil.rmtree(staged)
            self.gateway._request("POST", lease_path, {"operation": "release", "owner": lease["owner"], "generation": lease["generation"]})
            (self._root(row) / "runtime" / "execution.json").unlink(missing_ok=True)
            path.unlink()
            self._update(row, state="stopped")

    def start(self) -> None:
        """启动执行租约心跳。

        :return: None
        """
        self.heartbeat.start()

    def stop(self) -> None:
        """停止调度时收口 CLI，保留独立 API 与持久环境。

        :return: None
        """
        self.stopping.set()
        if self.heartbeat.is_alive():
            self.heartbeat.join(timeout=6)
        self.heartbeat_pool.shutdown(wait=False, cancel_futures=True)
        with self.lock:
            jobs = list(self.jobs.values())
        for job in jobs:
            try:
                self.cleanup(job["token"])
            except Exception:
                # cleanup 已保存隔离状态；不能因单账号失联阻止其它 CLI 收口。
                pass
