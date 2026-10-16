"""v3 单账号固定容器、执行句柄和服务间传输登记。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from socket import SHUT_WR
from stat import S_ISREG
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlsplit

from docker.errors import DockerException, NotFound
from account_isolation import ISOLATION_VERSION, ROLE_COLUMNS, ROLE_LABELS, create_environment, role_container
from process_metrics import PROCESS_SOURCE, merge_process_metrics, validate_process_metrics
from resource_budget import account_limits, isolated_account_limits
from system_profile import (MAX_CPUINFO_BYTES, generate_system_profile, render_system_profile,
    validate_system_profile, verify_system_profile)


NETWORK_INSPECTION_MODES = {"passthrough", "quota", "capture"}
V3_DEFAULT_TIMEZONE = "America/Los_Angeles"
CLI_CONFIG_IDENTITY_SOURCES = {"2.1.293": "cli:2.1.293:config.userID"}
CLI_REQUEST_IDENTITY_SOURCE = "cli:/v1/messages:metadata.user_id.device_id"


def locale_for_timezone(timezone: str | None) -> str:
    """
    为显式时区选择同地区的可用 locale。

    :param timezone: IANA 时区名；空值使用英语回退
    :return: 账号镜像已生成的 UTF-8 locale
    """
    value = timezone or V3_DEFAULT_TIMEZONE
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

    :param timezone: 账号显式 IANA 时区；空值使用洛杉矶时区
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
        "tz": timezone or V3_DEFAULT_TIMEZONE,
        "lang": locale_for_timezone(timezone),
    }


def _directory_fd(path: Path, create: bool = False) -> int:
    absolute = path.absolute()
    if '..' in absolute.parts:
        raise ValueError('账号文件路径不能包含上级目录')
    directory = os.open(absolute.anchor, os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            if create:
                try:
                    os.mkdir(part, dir_fd=directory)
                except FileExistsError:
                    pass
            following = os.open(part, os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = following
        return directory
    except Exception:
        os.close(directory)
        raise


def _read_json(path: Path):
    directory = _directory_fd(path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, 'rb') as source:
            metadata = os.fstat(source.fileno())
            if not S_ISREG(metadata.st_mode) or metadata.st_size > 16 * 1024 ** 2:
                raise ValueError('账号配置必须为大小受限的普通 JSON 文件')
            raw = source.read(16 * 1024 ** 2 + 1)
            if len(raw) > 16 * 1024 ** 2:
                raise ValueError('账号配置超过 JSON 大小上限')
            return json.loads(raw)
    finally:
        os.close(directory)


def atomic_json(path: Path, value: dict, mode: int = 0o600) -> None:
    """原子保存受限 JSON。

    :param path: 目标路径
    :param value: JSON object
    :param mode: 文件权限
    :return: None
    """
    atomic_text(path, json.dumps(value, ensure_ascii=False), mode)


def atomic_text(path: Path, value: str, mode: int = 0o600) -> None:
    """通过受控目录 fd 原子保存文本，供 JSON 和只读画像共同使用。

    :param path: 目标文件。
    :param value: 完整 UTF-8 文本。
    :param mode: 文件权限。
    :return: None。
    """
    directory = _directory_fd(path.parent, create=True)
    temporary = path.name + "." + uuid.uuid4().hex
    try:
        # 目录逐级以 fd 固定；不能先检查链接、随后再沿可被业务进程替换的路径写入。
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode, dir_fd=directory)
        with os.fdopen(descriptor, "w") as output:
            os.fchmod(output.fileno(), mode)
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        finally:
            os.close(directory)


class RuntimeBusy(ValueError):
    """低优先级作业遇到正式工作时顺延，不能记为认证或任务失败。"""


class AccountRuntime:
    """管理每账号的固定逻辑环境和隔离角色；执行结束保留 HOME 与网络。

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
                environment_columns = {row["name"] for row in connection.execute("PRAGMA table_info(account_environments)")}
                for column, kind in (("network_container_id", "TEXT"), ("sender_container_id", "TEXT"),
                        ("isolation_version", "INTEGER NOT NULL DEFAULT 0")):
                    if column not in environment_columns:
                        connection.execute(f"ALTER TABLE account_environments ADD COLUMN {column} {kind}")
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
            if draft_path.exists() and _read_json(draft_path).get("phase") == "deleting":
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
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json,isolation_version) VALUES(?,?,?,?,?)",
                                   (environment_id, name, account_id, json.dumps(fingerprint), 0))
            return {"environment_id": environment_id, "name": name, "account_id": account_id,
                    "fingerprint_json": json.dumps(fingerprint), "generation": 0,
                    "container_id": None, "network_container_id": None, "sender_container_id": None,
                    "isolation_version": 0, "state": "stopped"}
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

    def prepare_system_profile(self, row: dict, network) -> None:
        """在受控创建窗口保存一次画像，并发布 CLI 专属只读文件。

        :param row: 已持有生命周期锁且尚未创建 CLI 的环境。
        :param network: 同账号实际 Docker 网络角色，用于读取真实 CPU。
        :return: None；坏画像保留，不重新随机。
        """
        if row["environment_id"] in self.jobs:
            raise ValueError("活动执行中不能生成或应用系统画像")
        if row.get("container_id"):
            raise ValueError("已有 CLI 实例不能切换系统画像，请先空闲重建")
        result = network.exec_run(["cat", "/proc/cpuinfo"])
        if result.exit_code or not isinstance(result.output, bytes) or len(result.output) > MAX_CPUINFO_BYTES:
            raise ValueError("无法读取实际 Docker CPU 信息，系统画像未启用")
        try:
            cpuinfo = result.output.decode("utf-8")
            fingerprint = json.loads(row["fingerprint_json"])
        except (UnicodeError, ValueError):
            raise ValueError("系统画像来源或保存记录损坏") from None
        if not isinstance(fingerprint, dict):
            raise ValueError("系统画像保存记录格式无效")
        if "system_profile" not in fingerprint:
            fingerprint["system_profile"] = generate_system_profile(cpuinfo)
            self._update(row, fingerprint_json=json.dumps(fingerprint))
        profile = validate_system_profile(fingerprint["system_profile"], cpuinfo)
        directory = self._root(row) / "runtime/system-profile"
        descriptor = _directory_fd(directory, create=True)
        try:
            os.fchown(descriptor, 0, 0)
            os.fchmod(descriptor, 0o755)
        finally:
            os.close(descriptor)
        for name, content in render_system_profile(profile, cpuinfo).items():
            atomic_text(directory / name, content, 0o444)

    def check_system_profile(self, row: dict, container) -> None:
        """只读确认 CLI 已应用固定画像，不迁移或改写运行配置。

        :param row: 当前环境行。
        :param container: 当前 CLI 角色。
        :return: None；旧容器提示空闲重建，API 角色不受影响。
        """
        try:
            fingerprint = json.loads(row["fingerprint_json"])
            if not isinstance(fingerprint, dict) or "system_profile" not in fingerprint:
                raise ValueError("CLI 尚无固定系统画像，请空闲重建账号环境")
            verify_system_profile(container, fingerprint["system_profile"])
        except ValueError:
            # 只关闭 CLI 门禁，不能为本地画像问题中断健康的独立 API。
            self._update(row, state="cli_reconcile")
            raise

    def _labels(self, row: dict) -> dict:
        return {"vibebench.product": "v3", "vibebench.deployment": self.deployment,
                "vibebench.environment": row["environment_id"], "vibebench.role": "account"}

    def _container(self, row: dict):
        if row.get("isolation_version") == ISOLATION_VERSION:
            return role_container(self, row, "cli")
        container = self.client.containers.get(row["container_id"])
        if any(container.labels.get(key) != value for key, value in self._labels(row).items()):
            raise ValueError("容器部署归属不匹配，拒绝操作")
        return container

    def _network_runtime(self, row: dict) -> Path:
        return self._root(row) / "runtime" / "network" if row.get("isolation_version") == ISOLATION_VERSION else self._root(row) / "runtime"

    def _adopt_sender_evidence(self, row: dict) -> None:
        # 旧布局由 root 追加证据；转换后必须移交现有文件，不能只修改父目录属主。
        directory = _directory_fd(self._root(row) / "flows/api", create=True)
        try:
            os.fchown(directory, 1001, 1001)
            os.fchmod(directory, 0o700)
            for name in ("observations.jsonl", "observations.jsonl.previous"):
                try:
                    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                except FileNotFoundError:
                    continue
                try:
                    metadata = os.fstat(descriptor)
                    if not S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                        raise ValueError("API 证据必须为无硬链接的普通文件")
                    os.fchown(descriptor, 1001, 1001)
                    os.fchmod(descriptor, 0o600)
                finally:
                    os.close(descriptor)
        finally:
            os.close(directory)

    def _cli_runtime(self, row: dict) -> Path:
        return self._root(row) / "runtime" / "cli" if row.get("isolation_version") == ISOLATION_VERSION else self._root(row) / "runtime"

    def _sender_config(self, row: dict) -> Path:
        parent = self._root(row) / "runtime"
        return (parent / "sender" if row.get("isolation_version") == ISOLATION_VERSION else parent) / "sender.json"

    def _write_sender_config(self, row: dict, configuration: dict) -> None:
        path = self._sender_config(row)
        atomic_json(path, configuration, 0o640 if row.get("isolation_version") == ISOLATION_VERSION else 0o600)
        if row.get("isolation_version") == ISOLATION_VERSION:
            os.chown(path, 0, 1001, follow_symlinks=False)

    def _wait_network(self, row: dict) -> None:
        network = self._network_container(row)
        deadline = time.monotonic() + 120
        while network.exec_run(["test", "-f", "/run/v3/ready"]).exit_code:
            network.reload()
            if network.status != "running" or time.monotonic() >= deadline:
                raise ValueError("账号隔离网络未就绪，业务请求未启动")
            time.sleep(0.25)

    def _network_container(self, row: dict):
        return role_container(self, row, "network") if row.get("isolation_version") == ISOLATION_VERSION else self._container(row)

    def role_status(self, row: dict) -> dict:
        """只读核对环境角色状态，不唤醒容器或改变生命周期。

        :param row: 持久环境行。
        :return: 各角色的有限状态；不返回配置或服务秘密。
        """
        result = {}
        roles = ROLE_COLUMNS if row.get("isolation_version") == ISOLATION_VERSION else ("cli",)
        for role in roles:
            try:
                if not row.get(ROLE_COLUMNS[role]):
                    result[role] = "未创建"
                    continue
                container = role_container(self, row, role) if row.get("isolation_version") == ISOLATION_VERSION else self._container(row)
                container.reload()
                result[role] = str(container.status)
            except NotFound:
                result[role] = "缺失"
            except ValueError:
                result[role] = "归属或批次不匹配"
            except DockerException:
                result[role] = "状态未知"
        return result

    def _stop_environment(self, row: dict, remove: bool = False) -> None:
        """按角色归属停止完整环境，保留持久数据；停止失败不假报成功。

        :param row: 已确认的环境记录。
        :param remove: 是否在停止后移除运行实例。
        :return: None。
        """
        containers = []
        for role in ("cli", "sender", "network") if row.get("isolation_version") == ISOLATION_VERSION else ("cli",):
            if not row.get(ROLE_COLUMNS[role]):
                continue
            try:
                containers.append(role_container(self, row, role, allow_old_release=True)
                    if row.get("isolation_version") == ISOLATION_VERSION else self._container(row))
            except NotFound:
                continue
        if row.get("isolation_version") == ISOLATION_VERSION:
            # Docker 创建成功与 DB 登记之间可能中断；精确标签补收孤儿，不能靠名字猜归属。
            expected = self._labels(row)
            expected.pop("vibebench.role")
            instances = self.client.containers.list(all=True, filters={"label": [
                key + "=" + value for key, value in expected.items()]})
            known = {container.id for container in containers}
            for container in instances:
                if (any(container.labels.get(key) != value for key, value in expected.items())
                        or container.labels.get("vibebench.role") not in ROLE_LABELS.values()
                        or container.labels.get("vibebench.isolation-version") != str(ISOLATION_VERSION)):
                    raise ValueError("孤立角色归属不匹配，拒绝操作")
                if container.id not in known:
                    containers.append(container)
                    known.add(container.id)
        if row.get("isolation_version") == ISOLATION_VERSION:
            order = {ROLE_LABELS[role]: index for index, role in enumerate(("cli", "sender", "network"))}
            containers.sort(key=lambda current: order[current.labels["vibebench.role"]])
        for container in containers:
            container.stop(timeout=5)
        if remove:
            for container in containers:
                container.remove()
            self._update(row, container_id=None, sender_container_id=None, network_container_id=None)

    def ensure(self, account: dict, version: str | None = None, allow_inactive_login: bool = False,
               allow_login_recovery: bool = False, preserve_proxy: bool = False) -> tuple[dict, object]:
        """创建或唤醒固定环境，沿用首次固化参数。

        :param account: bench 账号或登录草稿
        :param version: 可选目标 CLI 版本；发送器准备无需 CLI
        :param allow_inactive_login: 仅显式重授权允许读取非 active OAuth 配置
        :param allow_login_recovery: 仅恢复原登录提交可进入本地保存门禁
        :param preserve_proxy: 指标读取只核对权威代理，不回写账号代理字段
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
                if preserve_proxy:
                    if self._proxy(account) != configuration["proxy_url"]:
                        raise ValueError("代理配置不一致，请先完成账号配置维护")
                else:
                    self._sync_proxy(account, configuration)
            draft_path = self.data / "login-drafts" / (row["environment_id"] + ".json")
            if draft_path.exists() and _read_json(draft_path).get("phase") == "submitting" and not allow_login_recovery:
                raise ValueError("原登录保存尚未完成，请先继续登录提交")
            root = self._root(row)
            if (root / "runtime/credential-handoff.json").exists():
                raise ValueError("解绑凭据交接尚未完成，请再次解绑完成交接")
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            for name in ("home", "projects", "workspaces", "flows", "controls", "ca", "cli", "runtime"):
                (root / name).mkdir(exist_ok=True, mode=0o700)
            for name in ("home", "projects"):
                os.chown(root / name, 1000, 1000, follow_symlinks=False)
            if row["state"] == "reconcile":
                raise ValueError("账号环境需要先对账，拒绝自动放行")
            if row.get("isolation_version") != ISOLATION_VERSION:
                if row["generation"] or row.get("container_id"):
                    raise ValueError("旧账号环境需要先空闲重建以升级 Docker 隔离，身份和 HOME 保留")
                self._update(row, isolation_version=ISOLATION_VERSION)
            if image_labels.get("vibebench.isolation-version") != str(ISOLATION_VERSION):
                raise ValueError("账号镜像不支持当前隔离布局，请使用同批新镜像")
            with self.capacity_lock:
                present = [bool(row.get(column)) for column in ROLE_COLUMNS.values()]
                if any(present) and not all(present):
                    self._update(row, state="reconcile")
                    raise ValueError("账号隔离角色登记不完整，需要先对账")
                if all(present):
                    try:
                        containers = {role: role_container(self, row, role) for role in ROLE_COLUMNS}
                        for current in containers.values():
                            current.reload()
                    except NotFound:
                        self._update(row, state="reconcile")
                        raise ValueError("账号隔离角色缺失，需要先对账") from None
                    configuration = _read_json(self._sender_config(row))
                    if configuration.get("proxy_source", configuration["proxy_url"]) != self._proxy(account):
                        if any(current.status == "running" for current in containers.values()) or row["environment_id"] in self.jobs:
                            raise ValueError("代理已改变，请先空闲维护账号环境")
                        self._stop_environment(row, remove=True)
                        present = [False]
                    elif not any(current.status == "running" for current in containers.values()):
                        self._make_room(row)
                        generation = int(row["generation"]) + 1
                        configuration["binding"].update(generation=generation, secret=secrets.token_hex(32))
                        self._write_sender_config(row, configuration)
                        (self._network_runtime(row) / "ready").unlink(missing_ok=True)
                        self._update(row, generation=generation, state="starting")
                        try:
                            containers["network"].start()
                            self._wait_network(row)
                            containers["cli"].start()
                            containers["sender"].start()
                        except Exception:
                            self._update(row, state="reconcile")
                            self._stop_environment(row)
                            raise
                    elif containers["network"].status != "running" or containers["sender"].status != "running":
                        self._update(row, state="reconcile")
                        raise ValueError("账号公共网络或发送器退出，需要先对账")
                    elif containers["cli"].status != "running":
                        self._update(row, state="cli_reconcile")
                if not any(present):
                    self._make_room(row)
                    deployment_key = hashlib.sha256(self.deployment.encode()).hexdigest()[:12]
                    name = f"v3-{deployment_key}-account-{row['environment_id']}"
                    create_environment(self, row, account, name, atomic_json)
                self._wait_network(row)
                container = self._container(row)
                deadline = time.monotonic() + 30
                while True:
                    try:
                        self._sender_active(row)
                        break
                    except (OSError, urllib.error.URLError):
                        sender = role_container(self, row, "sender")
                        sender.reload()
                        if sender.status != "running" or time.monotonic() >= deadline:
                            self._update(row, state="reconcile")
                            raise ValueError("账号发送器尚未就绪") from None
                        time.sleep(0.1)
                if row["state"] != "cli_reconcile":
                    self._update(row, state="ready")
        # 版本缓存准备不持有环境生命周期锁，API 不等待 CLI 安装。
        if version is not None:
            self.check_system_profile(row, container)
            self._ensure_version(container, version)
        return row, container

    def _ensure_version(self, container, version: str) -> None:
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?", version):
            raise ValueError("CLI 版本格式不合法")
        network = (self._network_container(self._row_for_container(container))
            if container.labels.get("vibebench.isolation-version") == str(ISOLATION_VERSION) else container)
        result = network.exec_run(["timeout", "--kill-after=5", "180", "/usr/local/bin/v3-cli-version", version])
        if result.exit_code != 0:
            raise ValueError("固定环境 CLI 版本准备失败")

    def _row_for_container(self, container) -> dict:
        connection = self.database()
        try:
            row = connection.execute("SELECT * FROM account_environments WHERE container_id=?", (container.id,)).fetchone()
        finally:
            connection.close()
        if not row:
            raise ValueError("CLI 容器没有当前环境登记")
        return dict(row)

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

    @staticmethod
    def _local_oauth(credentials: dict) -> dict:
        """校验本地刷新所有者的完整凭据，错误不包含秘密。"""
        oauth = credentials.get("claudeAiOauth") if isinstance(credentials, dict) else None
        if (not isinstance(oauth, dict)
                or any(not isinstance(oauth.get(key), str) or not oauth[key].strip()
                    for key in ("accessToken", "refreshToken"))
                or type(oauth.get("expiresAt")) not in (int, float)
                or not 0 < oauth["expiresAt"] < 2 ** 53):
            raise ValueError("本地 OAuth 凭据不完整，请恢复同账号完整凭据或重新授权")
        return oauth

    def _local_credentials(self, row: dict, account: dict, take_ownership: bool = False) -> dict | None:
        """选择本地权威凭据，仅在已证明来源一致时补齐 AT-only HOME。"""
        profile = self.data / "profiles" / account["name"]
        path = profile / ".credentials.json"
        if not path.exists():
            return None
        home = self._root(row) / "home"
        destination = home / ".claude/.credentials.json"
        try:
            credentials = _read_json(path)
            if not destination.exists():
                self._local_oauth(credentials)
                return credentials
            current = _read_json(destination)
            oauth = current.get("claudeAiOauth") if isinstance(current, dict) else None
            if not isinstance(oauth, dict):
                raise ValueError("本地 HOME 凭据损坏，请恢复同账号完整凭据或重新授权")
            if oauth.get("refreshToken"):
                self._local_oauth(current)
                # 独立运行后的 HOME 持有轮换结果，旧管理副本不能回滚它。
                if not take_ownership:
                    return current
            source = self._local_oauth(credentials)
            identities = [_read_json(folder / ".claude.json") for folder in (profile, home)]
            expected = identities[0]
            if (not isinstance(expected, dict) or not isinstance(identities[1], dict)
                    or not isinstance(expected.get("userID"), str) or not expected["userID"]
                    or not isinstance(expected.get("oauthAccount"), dict)
                    or not isinstance(expected["oauthAccount"].get("accountUuid"), str)
                    or not expected["oauthAccount"]["accountUuid"]
                    or identities[1].get("userID") != expected["userID"]
                    or not isinstance(identities[1].get("oauthAccount"), dict)
                    or identities[1]["oauthAccount"].get("accountUuid") != expected["oauthAccount"]["accountUuid"]):
                raise ValueError("本地 HOME 与管理凭据账号身份不一致，请先核对或重新授权")
            if oauth.get("refreshToken"):
                if (any(not secrets.compare_digest(oauth[key], source[key])
                        for key in ("accessToken", "refreshToken")) or oauth["expiresAt"] != source["expiresAt"]):
                    raise ValueError("解绑前 HOME 存在独立凭据，请先核对凭据所有权")
                return current
            if not take_ownership and (not isinstance(oauth.get("accessToken"), str)
                    or not secrets.compare_digest(oauth["accessToken"], source["accessToken"])
                    or oauth.get("expiresAt") != source["expiresAt"]):
                raise ValueError("本地 HOME 凭据来源不能确认，请恢复同账号完整凭据或重新授权")
            # 显式解绑可交接原管理所有者的最新快照；普通修复只补同一 AT 的 RT。
            return {**current, **credentials, "claudeAiOauth": {**oauth, **source}}
        except (OSError, ValueError) as error:
            if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError):
                raise
            raise ValueError("本地凭据或账号身份文件无法读取，请检查后重新授权") from None

    def sync_credentials(self, row: dict, account: dict, *, take_ownership: bool = False) -> None:
        """绑定时发布 AT-only；未绑定时保留完整的本地刷新所有者。

        :param row: 固定环境
        :param account: bench 账号
        :param take_ownership: 显式从原 cc2api 绑定接管本地刷新权
        :return: None
        """
        profile = self.data / "profiles" / account["name"]
        path = profile / ".credentials.json"
        if not path.exists():
            return
        credentials = (self._local_credentials(row, account, take_ownership)
            if account.get("cc2api_account_id") is None else _read_json(path))
        home = self._root(row) / "home"
        destination = home / ".claude" / ".credentials.json"
        if account.get("cc2api_account_id") is not None:
            credentials.get("claudeAiOauth", {}).pop("refreshToken", None)
        atomic_json(destination, credentials)
        os.chown(destination.parent, 1000, 1000, follow_symlinks=False)
        os.chown(destination, 1000, 1000, follow_symlinks=False)
        access = self._root(row) / "runtime" / "access" / ".credentials.json"
        atomic_json(access, credentials)
        if row.get("isolation_version") == ISOLATION_VERSION:
            access.parent.chmod(0o750)
            os.chown(access.parent, 0, 1000, follow_symlinks=False)
            os.chown(access, 1000, 1000, follow_symlinks=False)
            network_access = self._network_runtime(row) / "access" / ".credentials.json"
            snapshot = json.loads(json.dumps(credentials))
            snapshot.get("claudeAiOauth", {}).pop("refreshToken", None)
            atomic_json(network_access, snapshot)
        if not (home / ".claude.json").exists() and (profile / ".claude.json").exists():
            shutil.copy2(profile / ".claude.json", home / ".claude.json")
            os.chown(home / ".claude.json", 1000, 1000, follow_symlinks=False)

    def transport(self, account: dict, version: str) -> dict:
        """返回只用于服务间调用的当前传输绑定。

        :param account: 绑定的 bench 账号
        :param version: 兼容旧调用方的 CLI 版本，不参与 API 环境准备
        :return: 当前账号传输绑定，含受限服务秘密
        """
        row, _ = self.ensure(account)
        config_path = self._sender_config(row)
        config = _read_json(config_path)
        binding = config["binding"]
        if config.get("proxy_source", config["proxy_url"]) != self._proxy(account):
            raise ValueError("代理配置已改变，请空闲重建环境后再使用")
        identity = self.quota_identity(account) if self.quota_identity else ""
        if binding["account_id"] != account["cc2api_account_id"] or config.get("quota_identity") != identity:
            binding["account_id"] = int(account["cc2api_account_id"])
            config["quota_identity"] = identity
            self._write_sender_config(row, config)
        return binding

    def _sender_active(self, row: dict) -> int:
        binding = _read_json(self._sender_config(row))["binding"]
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
        if not row.get("sender_container_id" if row.get("isolation_version") == ISOLATION_VERSION else "container_id"):
            return 0
        try:
            container = role_container(self, row, "sender", allow_old_release=True) if row.get("isolation_version") == ISOLATION_VERSION else self._container(row)
        except NotFound:
            return 0
        container.reload()
        return self._sender_active(row) if container.status == "running" else 0

    @contextmanager
    def owner_transition(self, account: dict, target_id: int | None, *, handoff_credentials: bool = True):
        """在绑定切换整个事务期间关闭两端门禁并撤销旧发送实例。

        :param account: 切换前的 bench 账号
        :param target_id: 新 cc2api 绑定，None 表示解绑或删除
        :param handoff_credentials: 本地账号删除无需交接凭据，其余切换保留发布
        :return: 持有环境锁与远端门禁的上下文
        """
        with self._account_lock(account):
            row = self._row(account["name"], account["id"])
            if row["environment_id"] in self.jobs:
                raise ValueError("账号环境正在执行工作，不能切换绑定")
            handoff = self._root(row) / "runtime/credential-handoff.json"
            profile = self.data / "profiles" / account["name"] / ".credentials.json"
            take_ownership = handoff_credentials and account.get("cc2api_account_id") is not None and target_id is None
            if handoff_credentials and handoff.exists():
                try:
                    pending = _read_json(handoff)
                    valid = (isinstance(pending, dict) and pending.get("schema") == 1
                        and pending.get("account_id") == account["id"]
                        and pending.get("environment_id") == row["environment_id"]
                        and account.get("cc2api_account_id") in (None, pending.get("previous_binding"))
                        and pending.get("profile_sha256") == hashlib.sha256(profile.read_bytes()).hexdigest())
                except (OSError, ValueError):
                    valid = False
                if target_id is not None or not valid:
                    raise ValueError("解绑凭据交接记录或来源已变化，请先核对同账号凭据")
                take_ownership = True
            leases = []
            try:
                for account_id in sorted({int(value) for value in (account.get("cc2api_account_id"), target_id) if value is not None}):
                    path = f"/admin/runtime/accounts/{account_id}/lease"
                    try:
                        snapshot = self.gateway._request("GET", path)
                        if snapshot["active"] or snapshot.get("waiting") or snapshot["lease"]:
                            raise ValueError("绑定账号有活动或等待请求，不能切换绑定")
                        snapshot = self.gateway._request("POST", path, {"operation": "prepare", "owner": f"binding:{uuid.uuid4().hex}"})
                    except ValueError as error:
                        cause = error.__cause__
                        if (target_id is not None or account_id != account.get("cc2api_account_id")
                                or not isinstance(cause, HTTPError) or cause.code != 404):
                            raise
                        # 仅原绑定的明确删除允许本地收口；路由 404、坏分页和网络故障保持拒绝。
                        if any(item["id"] == account_id for item in self.gateway.list_accounts(require_complete=True)):
                            raise
                        continue
                    leases.append((path, snapshot["lease"]))
                    if snapshot["active"] or self._running_sender_active(row):
                        raise ValueError("账号发送连接尚未收口，不能切换绑定")
                if self._running_sender_active(row):
                    raise ValueError("账号发送连接尚未收口，不能切换绑定")
                local_credentials = None
                if take_ownership:
                    # 交接所需资料先校验，身份/完整性冲突不能先清空本地绑定。
                    local_credentials = self._local_credentials(row, account, True)
                self._stop_environment(row)
                # 已解析的旧 API 请求只能遇到停止的实例；下一唤醒轮换秘密和代次。
                self._update(row, state="stopped")
                if local_credentials is not None and not handoff.exists():
                    # 先持久化无令牌意图，再提交 DB；跨文件失败可由重复解绑接着完成。
                    atomic_json(handoff, {"schema": 1, "account_id": account["id"],
                        "environment_id": row["environment_id"], "previous_binding": account["cc2api_account_id"],
                        "profile_sha256": hashlib.sha256(profile.read_bytes()).hexdigest()})
                yield
                connection = self.database()
                try:
                    current = connection.execute("SELECT * FROM accounts WHERE id=?", (account["id"],)).fetchone()
                finally:
                    connection.close()
                if current and handoff_credentials:
                    try:
                        self.sync_credentials(row, dict(current), take_ownership=take_ownership)
                    except Exception:
                        # DB 已提交而文件未收口时保留隔离，重复解绑可重新完成发布。
                        self._update(row, state="reconcile")
                        raise
                handoff.unlink(missing_ok=True)
            except Exception:
                if handoff.exists():
                    self._update(row, state="reconcile")
                raise
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
            if not exclusive and (self._network_runtime(row) / "cli-unhealthy").exists():
                self._update(row, state="cli_reconcile")
            maintenance = (row["state"] == "cli_reconcile" and exclusive and idle_only
                and source.startswith("maintenance:"))
            if row["state"] in ("reconcile", "cli_reconcile") and not maintenance:
                raise ValueError("账号 CLI 需要先对账，拒绝开始下一作业")
            with self.lock:
                pending = self._root(row) / "runtime" / "login-commit.json"
                if pending.exists() and source != f"login:{_read_json(pending)['sid']}":
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
        for key in ("exec", "handle", "tmux", "tmux_socket", "hooks_before", "statusline_before", "statusline_command", "version"):
            if key in job:
                execution[key] = job[key]
        atomic_json(self._root(job["row"]) / "runtime" / "execution.json", execution)

    def _isolate_job(self, job: dict) -> None:
        # 普通 CLI 收口失败只禁止下一 CLI，独立发送器继续处理已接受的 API。
        if job.get("exclusive", True):
            try:
                if job.get("claimed", True):
                    self._stop_environment(job["row"])
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
                self._restore_cli_quota(job)
                if row.get("account_id") is not None and job["account"].get("cc2api_account_id") is None:
                    credentials = self._root(row) / "home" / ".claude" / ".credentials.json"
                    if credentials.exists():
                        current = _read_json(credentials)
                        self._local_oauth(current)
                        atomic_json(self.data / "profiles" / row["name"] / ".credentials.json", current)
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
        elif job["row"].get("isolation_version") == ISOLATION_VERSION and job.get("version"):
            try:
                with self.environment_lock(job["row"]["environment_id"]):
                    with self.lock:
                        if self.jobs.get(job["row"]["environment_id"]) is not job:
                            return
                    self._sample_cli_metrics(job["row"], self._container(job["row"]))
            except (OSError, ValueError, RuntimeError, DockerException):
                # 指标缺失不改变认证/执行状态；独立导入会准确返回采样错误。
                pass

    @staticmethod
    def execution_environment(row: dict) -> dict[str, str]:
        """从已固化画像提取实际 CLI 环境，避免上层旧派生值覆盖。

        :param row: 含 fingerprint_json 的持久环境行
        :return: TZ、LANG 和 LC_ALL 环境变量
        """
        fingerprint = json.loads(row["fingerprint_json"])
        return {"TZ": fingerprint["tz"], "LANG": fingerprint["lang"], "LC_ALL": fingerprint["lang"]}

    @contextmanager
    def _cli_setup(self, account: dict, source: str, version: str,
                   idle_only: bool = False, exclusive: bool = False, allow_inactive_login: bool = False):
        row, container = self.ensure(account, allow_inactive_login=allow_inactive_login,
            allow_login_recovery=source.startswith("login:"))
        self.check_system_profile(row, container)
        job = self.claim(row, account, source, idle_only, exclusive)
        try:
            self._ensure_version(container, version)
            with self.environment_lock(row["environment_id"]):
                with self.lock:
                    if self.jobs.get(row["environment_id"]) is not job or job.get("heartbeat_failed"):
                        raise ValueError("CLI 准备期间租约失效，执行未启动")
                # CLI 版本由管理端固定，禁止账号 CLI 自行写入 root 管理的版本缓存。
                settings = self._root(row) / "home/.claude/settings.json"
                value = _read_json(settings) if settings.is_file() else {}
                environment = value.get("env") if isinstance(value.get("env"), dict) else {}
                value["env"] = {**environment, "DISABLE_AUTOUPDATER": "1", **self.execution_environment(row)}
                atomic_json(settings, value)
                os.chown(settings, 1000, 1000, follow_symlinks=False)
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
                job["hooks_before"] = _read_json(settings).get("hooks") if settings.exists() else None
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
                os.chown(root / "controls", 0, 1000, follow_symlinks=False)
                controls.chmod(0o750)
                os.chown(controls, 0, 1000, follow_symlinks=False)
                runtime_run = root / "runtime" / "runs" / run_id
                runtime_job = root / "runtime" / "jobs" / handle
                for directory in (runtime_run, runtime_job):
                    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                    os.chown(directory, 1000, 1000, follow_symlinks=False)
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
                if quota_env.get("QUOTA_IDENTITY") and not task.get("capture_full_http"):
                    # 正式任务也调用默认设置函数；本代临时采集必须保留到 CLI 读取设置后。
                    source_script = source_script.replace(
                        "(.[0] | del(.hooks, .statusLine)) * .[1]", "(.[0] | del(.hooks)) * .[1]")
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
                script = script.replace("runuser -u '$CLAUDE_USER' -- env", "env PATH='$PATH'")
                script_path = root / "runtime" / "drivers" / f"job-{handle}.sh"
                script_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
                os.chown(script_path.parent, 0, 1000, follow_symlinks=False)
                script_path.write_text(script)
                os.chown(script_path, 0, 1000, follow_symlinks=False)
                script_path.chmod(0o750)
                original_flows = self.data / "flows" / account["name"] / str(task["id"]) / run_id
                flow_directory = self.execution_flows(account, source, original_flows)
                if not task.get("capture_full_http"):
                    self._install_cli_quota(job, cwd, flow_directory, quota_env.get("QUOTA_IDENTITY"))
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
                context["QUOTA_CREDENTIALS_FILE"] = "/run/v3/access/.credentials.json"
                atomic_json(self._network_runtime(row) / "context.json", context)
                self._configure_network_context(container, context)
                environment = dict(worker_env)
                environment.update(self.execution_environment(row))
                environment.update(V3_PERSISTENT_HOME="1", USE_SIDECAR_DNS="1", HOME="/home/node",
                    PATH=f"/cli/{worker_env['CLAUDE_CODE_VERSION']}/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    QUOTA_SIGNAL_FILE=context.get("QUOTA_SIGNAL_FILE", ""), TMUX_TMPDIR=f"/run/v3/jobs/{handle}",
                    QUOTA_WARMUP="1" if inspection_mode == "quota" else "0",
                    NETWORK_INSPECTION_MODE=inspection_mode)
                ex = self.client.api.exec_create(container.id,
                    # setsid 默认可能先返回，必须让 exec 生命周期跟随真实 driver。
                    ["setsid", "--wait", "bash", "-c", f"echo $$ > /run/v3/jobs/{handle}/group.pid; exec bash /run/v3/drivers/job-{handle}.sh"],
                    environment=environment, workdir=cwd)
                job.update(exec=ex["Id"], run_id=run_id, context=context, handle=handle, cwd=cwd,
                    network_inspection_mode=inspection_mode, tmux=f"claude-{run_id}",
                    tmux_socket=f"/run/v3/jobs/{handle}/tmux-1000/default", version=worker_env["CLAUDE_CODE_VERSION"])
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

    def _install_cli_quota(self, job: dict, cwd: str, flows: Path, identity: str | None) -> None:
        """为正式执行安装本地状态栏采集，先保存可跨重启恢复的原设置。

        :param job: 已领取的本代 CLI 执行
        :param cwd: 当前专属项目目录
        :param flows: 本代证据目录
        :param identity: 已登记额度游标的账号身份；未启用采集时为空
        :return: None
        """
        if not identity:
            return
        root = self._root(job["row"])
        relative = flows.relative_to(root / "flows")
        # 只赋予穿过本次路径的权限；UID1000 不获得父目录列表或私有 runtime 写权限。
        current = root / "flows"
        for part in (None, *relative.parts):
            if part is not None:
                current /= part
            if current.is_symlink():
                raise ValueError("额度采集目录不能是链接")
            current.chmod(0o710)
            os.chown(current, 0, 1000, follow_symlinks=False)
        directory = flows / "cli"
        if directory.is_symlink():
            raise ValueError("额度采集目录不能是链接")
        directory.mkdir(exist_ok=True, mode=0o700)
        os.chown(directory, 1000, 1000, follow_symlinks=False)
        settings = root / "home/.claude/settings.json"
        value = _read_json(settings) if settings.is_file() else {}
        original = value.get("statusLine")
        configuration = directory / "config.json"
        container_directory = "/flows/" + str(directory.relative_to(root / "flows"))
        command = "/usr/local/bin/v3-cli-quota --config " + shlex.quote(container_directory + "/config.json")
        job["statusline_before"] = {"present": "statusLine" in value, "value": original}
        job["statusline_command"] = command
        self._save_execution(job)
        atomic_json(configuration, {"source": "cli:" + job["source"], "identity": identity, "cwd": cwd,
            "session_dir": "/home/node/.claude/projects/" + cwd.replace("/", "-"),
            "output": container_directory + "/cli-quota.jsonl", "started_at": time.time(),
            "previous_command": original.get("command") if isinstance(original, dict) else None})
        os.chown(configuration, 1000, 1000, follow_symlinks=False)
        value["statusLine"] = {**(original if isinstance(original, dict) else {}), "type": "command", "command": command}
        atomic_json(settings, value)
        os.chown(settings, 1000, 1000, follow_symlinks=False)

    def _restore_cli_quota(self, job: dict) -> None:
        """在进程收口后恢复本代状态栏设置，保留执行期间用户明确改写的配置。

        :param job: 本代执行或重启后恢复的执行记录
        :return: None
        """
        snapshot = job.get("statusline_before")
        if not snapshot:
            return
        settings = self._root(job["row"]) / "home/.claude/settings.json"
        value = _read_json(settings) if settings.is_file() else {}
        current = value.get("statusLine")
        if not isinstance(current, dict) or current.get("command") != job.get("statusline_command"):
            return
        if snapshot["present"]:
            value["statusLine"] = snapshot["value"]
        else:
            value.pop("statusLine", None)
        atomic_json(settings, value)
        os.chown(settings, 1000, 1000, follow_symlinks=False)

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
        network = (self._network_container(self._row_for_container(container))
            if container.labels.get("vibebench.isolation-version") == str(ISOLATION_VERSION) else container)
        result = network.exec_run(["/usr/local/bin/v3-network-context"])
        if result.exit_code != 0:
            output = result.output.decode("utf-8", errors="replace") if isinstance(result.output, bytes) else str(result.output or "")
            detail = output.strip().splitlines()
            suffix = f"：{detail[-1][:240]}" if detail else ""
            raise ValueError("网络上下文切换失败，执行未启动" + suffix)
        acknowledgement = network.exec_run(["cat", "/run/v3/context-ack.json"])
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
            if commit_path.exists() and _read_json(commit_path).get("phase") != "mirrored":
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
                        pid_path = (self._root(job["row"]) / "runtime/jobs" / job['handle'] / "group.pid"
                            if job["row"].get("isolation_version") == ISOLATION_VERSION
                            else self._cli_runtime(job["row"]) / f"job-{job['handle']}.pid")
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
                if job["row"].get("isolation_version") == ISOLATION_VERSION:
                    result = container.exec_run(["python3", "-I", "/usr/local/bin/v3-cli-control", "stop"])
                    if result.exit_code:
                        raise ValueError("账号子进程尚未完成收口，禁止下一 CLI 作业")
                else:
                    container.exec_run(["pkill", "-TERM", "-u", "1000"])
                    deadline = time.monotonic() + 3
                    while container.exec_run(["pgrep", "-u", "1000"]).exit_code == 0 and time.monotonic() < deadline:
                        time.sleep(0.1)
                    container.exec_run(["pkill", "-KILL", "-u", "1000"])
                    if container.exec_run(["pgrep", "-u", "1000"]).exit_code == 0:
                        raise ValueError("账号子进程尚未完成收口，禁止下一 CLI 作业")
                idle_context = {"NETWORK_INSPECTION_MODE": "passthrough", "QUOTA_SOURCE": ""}
                atomic_json(self._network_runtime(job["row"]) / "context.json", idle_context)
                self._configure_network_context(container, idle_context)
                if "hooks_before" in job:
                    settings = self._root(job["row"]) / "home" / ".claude" / "settings.json"
                    value = _read_json(settings) if settings.exists() else {}
                    if job["hooks_before"] is None:
                        value.pop("hooks", None)
                    else:
                        value["hooks"] = job["hooks_before"]
                    atomic_json(settings, value)
                    os.chown(settings, 1000, 1000, follow_symlinks=False)
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
        os.chown(projects, 1000, 1000, follow_symlinks=False)
        view = projects / alias
        if view.is_symlink():
            raise ValueError("项目物理目录不能是符号链接")
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
            os.chown(view, 1000, 1000, follow_symlinks=False)
            compatibility.symlink_to(os.path.relpath(view, compatibility.parent), target_is_directory=True)
        cwd = f"/home/node/projects/{alias}"
        configuration = self._root(row) / "home" / ".claude.json"
        if configuration.is_file():
            value = _read_json(configuration)
            projects = value.get("projects") if isinstance(value.get("projects"), dict) else {}
            project = projects.get(cwd) if isinstance(projects.get(cwd), dict) else {}
            # 这里只信任本系统为当前任务创建的专属目录，避免首屏确认吞掉原题。
            value["projects"] = {**projects, cwd: {**project, "hasTrustDialogAccepted": True}}
            atomic_json(configuration, value)
            os.chown(configuration, 1000, 1000, follow_symlinks=False)
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
        os.chown(project, 1000, 1000, follow_symlinks=False)
        for parent in (project.parent, project.parent.parent):
            os.chown(parent, 1000, 1000, follow_symlinks=False)

        # 旧兼容层曾把 .claude-home 写进项目树；只移除本系统创建且仍指向当前 session 的链接。
        legacy_home = self._root(row) / "workspaces" / run_id / ".claude-home"
        # 此目录仅为旧 Runner 遗留；只清空目录，不跟随用户链接或删除内容。
        if legacy_home.is_symlink() or (legacy_home / "projects").is_symlink():
            return
        legacy_view = legacy_home / "projects" / "-workspace"
        if legacy_view.is_symlink() and legacy_view.resolve() == project.resolve():
            legacy_view.unlink()
            for directory in (legacy_view.parent, legacy_home):
                try:
                    directory.rmdir()
                except OSError:
                    break
        try:
            legacy_home.rmdir()
        except OSError:
            pass

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
            f"vibebench.deployment={self.deployment}"]})
        running = [container for container in running if container.labels.get("vibebench.role")
            in ("account", "account-network", "account-sender")]
        active_environments = {container.labels.get("vibebench.environment") or container.id for container in running}
        if requested["environment_id"] in active_environments or len(active_environments) < self.limit:
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
                    if busy or row["environment_id"] not in active_environments:
                        continue
                    account = connection.execute("SELECT * FROM accounts WHERE id=?", (row["account_id"],)).fetchone()
                    account = dict(account) if account else {"name": row["name"]}
                    try:
                        job = self.claim(row, account, f"idle:{uuid.uuid4().hex}", idle_only=True, exclusive=True)
                    except (ValueError, RuntimeError):
                        continue
                    self._stop_environment(row)
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
            atomic_json(self._network_runtime(row) / "context.json", idle_context)
            self._configure_network_context(container, idle_context)
            home = self._root(row) / "home"
            cli_home = "/home/node"
            if force:
                staged = home / ".v3-login" / sid
                staged_descriptor = _directory_fd(staged, create=True)
                os.close(staged_descriptor)
                for source in (home / ".claude.json", home / ".claude" / "settings.json"):
                    if source.exists():
                        target = staged / (".claude.json" if source.name == ".claude.json" else ".claude/settings.json")
                        atomic_json(target, _read_json(source))
                top = staged / ".claude.json"
                if top.exists():
                    configuration = _read_json(top)
                    # 只保留设备与本地设置；新身份必须由本次 CLI 登录重新写出。
                    configuration.pop("oauthAccount", None)
                    atomic_json(top, configuration)
                home = staged
                cli_home = f"/home/node/.v3-login/{sid}"
            profile = home / ".claude"
            profile.mkdir(exist_ok=True)
            for current, dirs, files in os.walk(home if force else profile):
                os.chown(current, 1000, 1000, follow_symlinks=False)
                for name in files:
                    os.chown(Path(current) / name, 1000, 1000, follow_symlinks=False)
            if force:
                os.chown(home.parent, 1000, 1000, follow_symlinks=False)
            socket_path = f"/tmp/v3-login-{sid}.sock"
            command = ["env", f"HOME={cli_home}",
                f"PATH=/cli/{version}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin",
                *(f"{key}={value}" for key, value in self.execution_environment(row).items()),
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
        """保留实际 argv；普通用户与能力边界由整个 CLI 容器提供。

        :param command: 实际 argv
        :return: 不经过字符串拼接的命令副本
        """
        return list(command)

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
            environment={"HOME": home, "PATH": f"/cli/{version}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin",
                **self.execution_environment(job["row"])},
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
                atomic_json(target, _read_json(source))
                os.chown(target, 1000, 1000, follow_symlinks=False)
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
            proof = _read_json(self._root(row) / "runtime" / "execution.json")
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
                    command + ["load-buffer", "-b", request_id, "-"], stdin=True, tty=False)
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
            atomic_json(self._network_runtime(row) / "context.json", idle_context)
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
        credentials = _read_json(credentials_path)
        oauth = credentials.get("claudeAiOauth")
        if not isinstance(oauth, dict) or any(not isinstance(snapshot.get(key), str) or not snapshot[key]
            for key in ("access_token", "refresh_token")) or type(snapshot.get("expires_at")) is not int:
            raise ValueError("权威凭据不完整，重授权尚未完成")
        oauth.update(accessToken=snapshot["access_token"], refreshToken=snapshot["refresh_token"], expiresAt=snapshot["expires_at"])
        atomic_json(credentials_path, credentials)
        os.chown(credentials_path, 1000, 1000, follow_symlinks=False)
        home = self._root(row) / "home"
        identity = record["identity"]
        for top in (profile / ".claude.json", home / ".claude.json"):
            value = _read_json(top) if top.exists() else {}
            oauth_account = value.setdefault("oauthAccount", {})
            # 只更新经验证的登录身份，保留 userID 等原设备字段与本地配置。
            for source, target in (("email", "emailAddress"), ("account_uuid", "accountUuid"), ("organization_uuid", "organizationUuid")):
                if identity.get(source):
                    oauth_account[target] = identity[source]
            atomic_json(top, value)
            os.chown(top, 1000, 1000, follow_symlinks=False)
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
                runtime_job = root / 'runtime/jobs' / handle
                runtime_job.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chown(runtime_job, 1000, 1000, follow_symlinks=False)
                flow_directory = self.execution_flows(account, context["QUOTA_SOURCE"], flows)
                flow_path = "/flows/" + str(flow_directory.relative_to(root / "flows"))
                control = root / "controls" / handle
                control.mkdir(parents=True, exist_ok=True, mode=0o750)
                self._link_directory(self.data / "quota-controls" / run["id"] / handle, control)
                context = dict(context, STATS_FILE=f"{flow_path}/stats.jsonl",
                    QUOTA_SIGNAL_FILE=f"/controls/{handle}/pause.json",
                    QUOTA_STATE_FILE=f"/quota-accounts/{account['id']}/state.json",
                    QUOTA_OBSERVATIONS_FILE=f"{flow_path}/passive-quota.jsonl",
                    QUOTA_CREDENTIALS_FILE="/run/v3/access/.credentials.json",
                    NETWORK_INSPECTION_MODE="capture" if run.get("capture_full_http") else "passthrough")
                if not run.get("capture_full_http"):
                    self._install_cli_quota(job, cwd, flow_directory, context.get("QUOTA_IDENTITY"))
                if run.get("capture_full_http"):
                    context.update(CAPTURE_FULL_HTTP="1", SAVE_FULL_FLOWS="1",
                        CAPTURE_FILE=f"{flow_path}/http_capture.jsonl", CAPTURE_INDEX_FILE=f"{flow_path}/capture_index.json")
                atomic_json(self._network_runtime(row) / "context.json", context)
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
                self._stop_environment(row, remove=True)
                fingerprint = self.fingerprint(account.get("timezone"))
                previous = json.loads(row["fingerprint_json"])
                if "system_profile" in previous:
                    fingerprint["system_profile"] = validate_system_profile(previous["system_profile"])
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
                row = self._row(row["name"], row["account_id"])
                if row["state"] == "cli_reconcile" and row.get("isolation_version") == ISOLATION_VERSION:
                    self._recover_cli(row)
                if row["state"] == "cli_reconcile":
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
                    if snapshot["active"] or self._running_sender_active(row):
                        raise ValueError("API 仍有活动请求，拒绝对账")
            if operation == "rebuild" and row.get("isolation_version") != ISOLATION_VERSION:
                self._prepare_isolation_upgrade(row)
            self._stop_environment(row, remove=operation == "rebuild")
            if job:
                self._lease(job, "release")
                with self.lock:
                    self.jobs.pop(environment_id, None)
            elif account.get("cc2api_account_id") is not None and snapshot["lease"]:
                lease = snapshot["lease"]
                self.gateway._request("POST", f"/admin/runtime/accounts/{account['cc2api_account_id']}/lease",
                    {"operation": "release", "owner": lease["owner"], "generation": lease["generation"]})
            (self._root(row) / "runtime" / "execution.json").unlink(missing_ok=True)
            self._update(row, state="stopped", **({"isolation_version": ISOLATION_VERSION} if operation == "rebuild" else {}))

    def _prepare_isolation_upgrade(self, row: dict) -> None:
        # 迁移只由已排空的显式 rebuild 进入；恢复资料私有保存，绝不自动回写旧 RT。
        root = self._root(row)
        snapshot = root / "runtime" / "isolation-upgrade"
        if snapshot.is_symlink():
            raise ValueError("隔离迁移备份目录不能是链接")
        snapshot.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = snapshot / "record.json"
        if marker.exists():
            previous = _read_json(marker)
            if previous.get("environment_id") != row["environment_id"]:
                raise ValueError("隔离迁移记录归属不匹配")
            return
        connection = self.database()
        try:
            with sqlite3.connect(snapshot / "before.sqlite") as destination:
                connection.backup(destination)
            (snapshot / "before.sqlite").chmod(0o600)
        finally:
            connection.close()
        for source, name in ((root / "home/.claude.json", "identity.json"),
                (root / "runtime/sender.json", "sender.json")):
            if source.is_file():
                shutil.copy2(source, snapshot / name)
                (snapshot / name).chmod(0o600)
        atomic_json(marker, {"schema": 1, "environment_id": row["environment_id"],
            "previous": row, "target_isolation_version": ISOLATION_VERSION,
            "created_at": time.time(), "credential_restore": "禁止恢复历史凭据，沿用最新合法所有者"})

    def _recover_cli(self, row: dict) -> None:
        if row["environment_id"] in self.jobs or (self._root(row) / "runtime/execution.json").exists():
            raise ValueError("CLI 执行尚未确认收口")
        roles = {role: role_container(self, row, role) for role in ROLE_COLUMNS}
        for current in roles.values():
            current.reload()
        if any(roles[role].status != "running" for role in ("network", "sender")):
            raise ValueError("公共网络或发送器异常，需要重建完整环境")
        self._wait_network(row)
        if roles["cli"].status != "running":
            roles["cli"].start()
        self.check_system_profile(row, roles["cli"])
        result = roles["cli"].exec_run(["python3", "-I", "/usr/local/bin/v3-cli-control", "stop"])
        if result.exit_code:
            raise ValueError("CLI 子进程仍未收口，独立 API 保持运行")
        context = {"NETWORK_INSPECTION_MODE": "passthrough", "QUOTA_SOURCE": ""}
        atomic_json(self._network_runtime(row) / "context.json", context)
        self._configure_network_context(roles["cli"], context)
        self._update(row, state="ready")

    def read_cli_identity(self, row: dict, version: str) -> dict:
        """只读核验官方 CLI 的本地身份及已有请求观察，不创建环境。

        :param row: 已登记的固定环境；调用方按 owner、profile、environment 顺序保护读取
        :param version: 目标 CLI 的精确版本
        :return: 无凭据的设备、账号和来源；缺失或冲突时抛出 ValueError
        """
        root = self._root(row)
        identity_file = root / "runtime" / "identity.json"
        has_observation = identity_file.exists()
        try:
            top = _read_json(root / "home" / ".claude.json")
            profile = _read_json(self.data / "profiles" / row["name"] / ".claude.json")
            observed = _read_json(identity_file) if has_observation else None
        except (OSError, ValueError):
            raise ValueError("CLI 身份配置缺失或损坏，请检查固定环境的登录产物") from None
        if not isinstance(top, dict) or not isinstance(profile, dict):
            raise ValueError("CLI 身份配置格式无效，已阻止同步")
        oauth = top.get("oauthAccount")
        profile_oauth = profile.get("oauthAccount")
        account_uuid = oauth.get("accountUuid") if isinstance(oauth, dict) else None
        if not isinstance(account_uuid, str) or not account_uuid.strip() or not isinstance(profile_oauth, dict) \
                or account_uuid != profile_oauth.get("accountUuid"):
            raise ValueError("CLI 设备身份与当前登录账号归属不一致，已阻止同步")
        if has_observation:
            if not isinstance(observed, dict) or observed.get("conflict") \
                    or not isinstance(observed.get("device_id"), str) \
                    or not re.fullmatch(r"[a-f0-9]{64}", observed["device_id"]) \
                    or observed.get("source") != CLI_REQUEST_IDENTITY_SOURCE:
                raise ValueError("客户端设备身份观察损坏或存在冲突，已阻止同步")
            if observed.get("account_uuid") != account_uuid:
                raise ValueError("观测设备身份与当前登录账号归属不一致，已阻止同步")
        source = CLI_CONFIG_IDENTITY_SOURCES.get(version)
        if source:
            # 此映射已由指定官方版本的隔离请求验证；不能按字段名推定其它版本或 machineID。
            device_id = top.get("userID")
            if not isinstance(device_id, str) or not re.fullmatch(r"[a-f0-9]{64}", device_id):
                raise ValueError("CLI 登录产物缺少有效设备身份，请检查固定 HOME")
            if observed is not None and observed["device_id"] != device_id:
                raise ValueError("本地 CLI 设备身份与历史请求观察冲突，已阻止同步")
            return {"device_id": device_id, "account_uuid": account_uuid, "source": source}
        if observed is not None:
            return {key: observed[key] for key in ("device_id", "account_uuid", "source")}
        raise ValueError("当前 CLI 版本的设备身份来源尚未验证，暂不能同步到 cc2api")

    def identity_import(self, account: dict, version: str) -> dict:
        """导出已核验的 CLI 设备字段及可测量的基础环境。

        :param account: 新导入的 bench 账号
        :param version: 当前 CLI 基础版本
        :return: 无凭据的身份载荷；缺少证据时阻止导入
        """
        row, container = self.ensure(account, version)
        with self.environment_lock(row["environment_id"]):
            identity = self.read_cli_identity(row, version)
        probe = '''const os=require('os');const fs=require('fs');const distro=Object.fromEntries(fs.readFileSync('/etc/os-release','utf8').split('\\n').filter(x=>x.includes('=')).map(x=>{const i=x.indexOf('=');return[x.slice(0,i),x.slice(i+1).replace(/^"|"$/g,'')]}));console.log(JSON.stringify({platform_raw:process.platform,arch:process.arch,node_version:process.version,linux_distro_id:distro.ID||'',linux_distro_version:distro.VERSION_ID||'',linux_kernel:os.release()}));'''
        result = container.exec_run(self.cli_command(["node", "-e", probe]))
        if result.exit_code:
            raise ValueError("实际基础环境读取失败")
        environment = json.loads(result.output)
        environment.update(platform="Linux", terminal="tmux", package_managers="npm", runtimes="node",
            version=version, version_base=version, build_time="", deployment_environment="", vcs="git")
        return {"device_id": identity["device_id"], "environment_id": row["environment_id"],
            "source": identity["source"], "canonical_env": environment, "canonical_process": self.process_import(row, container, version),
            "canonical_prompt": {"platform": "linux", "shell": "bash", "os_version": environment["linux_kernel"],
                "working_dir": "/home/node"}}

    def process_import(self, row: dict, container, version: str) -> dict:
        """读取 root 管理的实测指标，不启动模型或执行额外登录。

        :param row: 已确认环境行。
        :param container: 当前环境的 Docker 容器。
        :param version: 当前 CLI 版本。
        :return: 可导入的进程指标；损坏或预算不符时拒绝。
        """
        if row.get("isolation_version") == ISOLATION_VERSION:
            observed = self._sample_cli_metrics(row, container)
            sample = observed["versions"].get(version, {"sampled_at": None, "sample_count": 0,
                "rss_bytes": None, "rss_min_bytes": None, "rss_max_bytes": None})
            payload = {"constrained_memory": observed["constrained_memory"], "observation": {
                "source": PROCESS_SOURCE, "environment_id": row["environment_id"], "cli_version": version,
                "observed_at": observed["observed_at"], **sample}}
        else:
            result = container.exec_run(["python3", "/usr/local/bin/v3-process-metrics", "read", version])
            if result.exit_code:
                raise ValueError("实际进程指标读取失败，请检查环境采样状态")
            payload = json.loads(result.output)
        try:
            value = validate_process_metrics(payload, row["environment_id"], version)
            fingerprint = json.loads(row["fingerprint_json"])
            expected, _ = (isolated_account_limits(fingerprint["mem"], fingerprint.get("swap", "0"))["cli"]
                if row.get("isolation_version") == ISOLATION_VERSION else account_limits(fingerprint["mem"], fingerprint.get("swap", "0")))
            if value["constrained_memory"] != expected:
                raise ValueError("实际容器内存限制与固化预算不一致")
            return value
        except (KeyError, TypeError, json.JSONDecodeError):
            raise ValueError("进程指标响应损坏") from None

    def _sample_cli_metrics(self, row: dict, container) -> dict:
        result = container.exec_run(["env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "python3", "-I",
            "/usr/local/bin/v3-cli-control", "sample"])
        if result.exit_code:
            raise ValueError("实际 CLI 内核采样失败")
        try:
            sample = json.loads(result.output)
            fingerprint = json.loads(row["fingerprint_json"])
            expected = isolated_account_limits(fingerprint["mem"], fingerprint.get("swap", "0"))["cli"][0]
            if sample["memory"] != expected:
                raise ValueError("实际 CLI 内存限制与角色预算不符")
            return merge_process_metrics(self._root(row) / "runtime", row["environment_id"], expected, sample["samples"])
        except (KeyError, TypeError, json.JSONDecodeError):
            raise ValueError("实际 CLI 内核采样响应无效") from None

    def process_identity_import(self, account: dict, version: str) -> dict:
        """导出原绑定的指标和非秘密身份，不读取或刷新 OAuth 凭据。

        :param account: 当前已绑定账号。
        :param version: 当前官方 CLI 版本。
        :return: 独立进程导入载荷。
        """
        row, container = self.ensure(account, preserve_proxy=True)
        with self.environment_lock(row["environment_id"]):
            identity = self.read_cli_identity(row, version)
            top = _read_json(self._root(row) / "home/.claude.json")
            email = top.get("oauthAccount", {}).get("emailAddress")
            if not isinstance(email, str) or not email.strip():
                raise ValueError("CLI 登录身份缺少邮箱，无法核对原关联账号")
            process = self.process_import(row, container, version)
        return {"device_id": identity["device_id"], "account_uuid": identity["account_uuid"],
            "email": email.strip(), "environment_id": row["environment_id"], "cli_version": version,
            "canonical_process": process}

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
            except (DockerException, ValueError):
                # 新批次启动时旧角色仍需显式收口；单环境异常不能使整个管理服务启动失败。
                self._update(row, state="cli_reconcile" if shared else "reconcile")
                continue
            try:
                if (self._root(row) / "runtime/credential-handoff.json").exists():
                    raise ValueError("解绑凭据交接未完成，需要再次显式解绑")
                commit_path = self._root(row) / "runtime" / "login-commit.json"
                if commit_path.exists():
                    self._reconcile_login_import(row, container, commit_path)
                    continue
                if record.exists():
                    execution = _read_json(record)
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
                        for key in ("exec", "handle", "tmux", "tmux_socket", "hooks_before", "statusline_before", "statusline_command"):
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
                    self._stop_environment(row)
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
                    isolated_state = None
                    if row.get("isolation_version") == ISOLATION_VERSION and any(row.get(column) for column in ROLE_COLUMNS.values()):
                        roles = {role: role_container(self, row, role) for role in ROLE_COLUMNS}
                        for current in roles.values():
                            current.reload()
                        if any(current.status == "running" for current in roles.values()):
                            if any(roles[role].status != "running" for role in ("network", "sender")):
                                raise ValueError("账号公共角色状态不完整，需显式收口或重建")
                            self._wait_network(row)
                            self._sender_active(row)
                            if roles["cli"].status != "running":
                                shared, isolated_state = True, "cli_reconcile"
                    if container:
                        container.reload()
                        if shared and container.status == "running" and (self._network_runtime(row) / "cli-unhealthy").exists():
                            idle_context = {"NETWORK_INSPECTION_MODE": "passthrough", "QUOTA_SOURCE": ""}
                            atomic_json(self._network_runtime(row) / "context.json", idle_context)
                            self._configure_network_context(container, idle_context)
                    self._update(row, state=isolated_state or settled_state or (
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
            record = _read_json(path)
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
            self._stop_environment(row)
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
