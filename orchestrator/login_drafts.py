"""v3 未提交登录环境的私有记录、归属证明和完整清理。"""
import json
import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from docker.errors import NotFound
from account_runtime import atomic_json


class LoginDraftStore:
    """管理固定环境草稿；修改操作由调用方持有 owner/profile 锁。

    :param runtime: 固定账号运行环境
    :param database: SQLite 连接工厂
    :param db_lock: 数据库写入锁
    """

    def __init__(self, runtime, database, db_lock) -> None:
        """连接固定环境及既有数据库写锁。

        :param runtime: 固定账号运行环境
        :param database: SQLite 连接工厂
        :param db_lock: 数据库写入锁
        :return: None
        """
        self.runtime, self.database, self.db_lock = runtime, database, db_lock
        self.directory = runtime.data / "login-drafts"

    def _path(self, environment_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", environment_id):
            raise ValueError("草稿环境 ID 无效")
        path = self.directory / (environment_id + ".json")
        if self.directory.is_symlink() or path.is_symlink():
            raise ValueError("草稿记录归属异常")
        return path

    def record(self, row: dict) -> dict:
        """读取私有元数据，旧环境使用稳定的兼容代次。

        :param row: 环境行
        :return: 不含授权秘密的内部记录
        """
        path = self._path(row["environment_id"])
        if path.exists():
            value = json.loads(path.read_text())
            if not isinstance(value, dict) or value.get("environment_id") != row["environment_id"] or value.get("name") != row["name"]:
                raise ValueError("草稿记录与环境归属不一致")
            if not isinstance(value.get("generation"), str) or not value["generation"] or value.get("phase") not in (
                "preparing", "authorizing", "ready_to_submit", "committed", "cancelled", "ended", "interrupted", "reconcile", "deleting", "submitting"):
                raise ValueError("草稿记录结构无效")
            self.profile(row, value)
            return value
        return {"environment_id": row["environment_id"], "name": row["name"],
            "generation": "legacy-" + str(row["generation"]), "phase": "interrupted"}

    def save(self, row: dict, **fields) -> dict:
        """原子保存当前阶段，不保存授权链接、代码或令牌。

        :param row: 环境行
        :param fields: sid、generation、phase、version、home 等恢复字段
        :return: 保存后的记录
        """
        value = self.record(row)
        value.update(fields)
        atomic_json(self._path(row["environment_id"]), value)
        return value

    def rows(self) -> list[dict]:
        """列出未关联环境和清理中遗留标记。

        :return: 环境行；正式账号环境不混入
        """
        connection = self.database()
        try:
            rows = {row["environment_id"]: dict(row) for row in connection.execute(
                "SELECT * FROM account_environments WHERE account_id IS NULL")}
        finally:
            connection.close()
        if self.directory.is_symlink():
            raise ValueError("草稿目录归属异常")
        for path in self.directory.glob("*.json"):
            if path.stem not in rows:
                if not re.fullmatch(r"[a-f0-9]{32}", path.stem):
                    continue
                try:
                    value = json.loads(self._path(path.stem).read_text())
                    if not isinstance(value, dict) or not isinstance(value.get("name"), str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value["name"]):
                        raise ValueError("遗留草稿记录结构无效")
                except (ValueError, OSError):
                    # 已清目录后仍可能留下损坏标记；保留可见条目，不能靠猜名称删资源。
                    rows[path.stem] = {"environment_id": path.stem, "name": "未识别-" + path.stem[:8],
                        "account_id": None, "generation": 0, "container_id": None, "state": "reconcile"}
                    continue
                if value.get("phase") in ("deleting", "submitting"):
                    connection = self.database()
                    try:
                        existing = connection.execute("SELECT * FROM account_environments WHERE environment_id=?", (path.stem,)).fetchone()
                    finally:
                        connection.close()
                    rows[path.stem] = dict(existing) if existing else {"environment_id": path.stem, "name": value["name"],
                        "account_id": None, "generation": 0, "container_id": None, "state": "stopped"}
        return list(rows.values())

    def row(self, environment_id: str) -> dict | None:
        """只读查找指定环境，包括数据库已删除的清理标记。

        :param environment_id: 不可变环境 ID
        :return: 环境行或 None
        """
        self._path(environment_id)
        connection = self.database()
        try:
            row = connection.execute("SELECT * FROM account_environments WHERE environment_id=?", (environment_id,)).fetchone()
        finally:
            connection.close()
        return dict(row) if row else next((row for row in self.rows() if row["environment_id"] == environment_id), None)

    def guard(self, row: dict, generation: str | None = None, allow_submitting: bool = False,
              allow_reconcile: bool = False) -> dict:
        """证明环境尚未成为正式账号，也没有历史或待确认提交。

        :param row: 当前环境行
        :param generation: 可选的页面草稿代次
        :param allow_submitting: 仅继续原本地提交允许读取已保存的同名账号
        :param allow_reconcile: 仅受控恢复检查允许读取隔离状态，不跳过归属和提交保护
        :return: 通过校验的元数据；冲突时抛 ValueError
        """
        record = self.record(row)
        pending = allow_submitting and record["phase"] == "submitting" and re.fullmatch(r"[a-f0-9]{12}", record.get("sid", ""))
        if (row["account_id"] is not None and not pending) or not re.fullmatch(r"[A-Za-z0-9_-]+", row["name"]):
            raise ValueError("已保存账号不能作为登录草稿处理")
        if generation is not None and generation != record["generation"]:
            raise ValueError("草稿已换代，请刷新账号列表")
        connection = self.database()
        try:
            formal = connection.execute("SELECT * FROM accounts WHERE name=? OR profile_path=?",
                (row["name"], "profiles/" + row["name"])).fetchone()
            prefix = str(self.runtime.data / "flows" / row["name"]) + "/"
            history = connection.execute("SELECT id FROM runs WHERE environment_id=? OR substr(flows_dir,1,?)=? LIMIT 1",
                (row["environment_id"], len(prefix), prefix)).fetchone()
        finally:
            connection.close()
        root = self.runtime._root(row)
        if formal and pending and (formal["name"] != row["name"] or formal["profile_path"] != "profiles/" + row["name"]
            or formal["cc2api_account_id"] is not None or formal["deleted_at"] is not None
            or row["account_id"] not in (None, formal["id"]) or record.get("saved_account_id", formal["id"]) != formal["id"]):
            raise ValueError("保存中的账号归属已改变，不能继续提交")
        if (formal and not pending) or history:
            raise ValueError("账号或历史仍引用此环境，请在环境页检查")
        if ((record["phase"] == "submitting" and not pending) or (root / "runtime" / "login-commit.json").exists()
            or (not allow_reconcile and row["state"] in ("reconcile", "cli_reconcile"))):
            raise ValueError("环境仍需对账，不能删除或重新登录")
        return record

    def recovery_record(self, row: dict, generation: str | None = None) -> dict:
        """只允许原归属明确、无活动工作的草稿恢复检查。

        :param row: 当前草稿环境
        :param generation: 页面代次，列表可省略
        :return: 可受控对账的原草稿记录
        """
        record = self.guard(row, generation, allow_reconcile=True)
        root = self.runtime._root(row)
        if (record["phase"] in ("preparing", "deleting", "submitting")
            or not re.fullmatch(r"[a-f0-9]{12}", record.get("sid", ""))
            or row["environment_id"] in self.runtime.jobs or root.is_symlink() or root.parent.is_symlink()
            or (root / "runtime").is_symlink()):
            raise ValueError("草稿正在操作或归属无法核对，请查看环境")
        path = root / "runtime" / "execution.json"
        if path.is_symlink():
            raise ValueError("遗留执行不是本环境的私有记录，请查看环境")
        if path.exists():
            proof = json.loads(path.read_text())
            if (not isinstance(proof, dict) or proof.get("source") != "login:" + record["sid"]
                or proof.get("container_id") != row["container_id"] or proof.get("generation") != row["generation"]
                or proof.get("account_id") is not None):
                raise ValueError("遗留执行归属无法核对，请查看环境")
        elif row["state"] not in ("reconcile", "cli_reconcile"):
            raise ValueError("草稿无需恢复检查，请刷新账号列表")
        if self.runtime._running_sender_active(row):
            raise ValueError("环境仍有活动发送请求，不能恢复检查")
        return record

    def proxy_summary(self, row: dict) -> dict:
        """读取原代理的公开摘要，不返回认证信息。

        :param row: 已核对私有记录归属的环境
        :return: 协议/主机/端口或明确的未知、未配置状态
        """
        try:
            account = self.account(row)
            host = account["upstream_socks5_host"]
            if ":" in host:
                host = "[" + host + "]"
            summary = (f"{account['upstream_proxy_scheme']}://{host}:{account['upstream_socks5_port']}" if host else None)
            return {"proxy_known": True, "proxy_summary": summary}
        except (ValueError, KeyError, TypeError, OSError):
            return {"proxy_known": False, "proxy_summary": None}

    def account(self, row: dict) -> dict:
        """从原私有配置恢复代理和首次固化时区，不公开发送器秘密。

        :param row: 已验证的未关联环境
        :return: 仅供恢复 CLI 的账号配置
        """
        path = self.runtime._root(row) / "runtime" / "sender.json"
        if not path.exists():
            raise ValueError("登录准备未完成，请删除草稿后重新配置")
        configuration = json.loads(path.read_text())
        if not isinstance(configuration, dict) or ("proxy_source" not in configuration and "proxy_url" not in configuration):
            raise ValueError("原代理配置缺失")
        source = configuration["proxy_source"] if "proxy_source" in configuration else configuration["proxy_url"]
        if not isinstance(source, str):
            raise ValueError("原代理配置无效")
        parsed = urlsplit(source)
        if source and (parsed.scheme not in ("http", "socks5", "socks5h") or not parsed.hostname
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("原代理配置无法恢复")
        return {"name": row["name"], "timezone": json.loads(row["fingerprint_json"])["tz"],
            "upstream_proxy_scheme": parsed.scheme or "socks5", "upstream_socks5_host": parsed.hostname or "",
            "upstream_socks5_port": parsed.port or (80 if parsed.scheme == "http" else 1080),
            "upstream_socks5_user": unquote(parsed.username or ""), "upstream_socks5_pass": unquote(parsed.password or "")}

    def profile(self, row: dict, record: dict) -> tuple[Path, str]:
        """恢复登录 HOME，禁止记录引入任意目录。

        :param row: 原环境
        :param record: 私有登录元数据
        :return: 本地 profile 和容器内 HOME
        """
        home = record.get("home", "/home/node")
        if not isinstance(home, str) or (home != "/home/node" and not re.fullmatch(r"/home/node/\.v3-login/[a-f0-9]{12}", home)):
            raise ValueError("登录 HOME 归属无效")
        relative = home.removeprefix("/home/node").lstrip("/")
        return self.runtime._root(row) / "home" / relative / ".claude", home

    def _safe_tree(self, path: Path, parent: Path) -> None:
        if parent.is_symlink() or path.is_symlink() or path.resolve().parent != parent.resolve():
            raise ValueError("草稿目录不是专属目录，拒绝清理")
        # npm 缓存会有指向本树的可执行链接；跨专属目录的链接必须拒绝，rmtree 不跟随链接。
        for current, directories, files in os.walk(path, followlinks=False):
            for name in directories + files:
                child = Path(current) / name
                if child.is_symlink() and not child.resolve().is_relative_to(path.resolve()):
                    raise ValueError("草稿目录含跨目录符号链接，请先检查归属")

    def delete(self, row: dict, generation: str, manager) -> None:
        """完整清理未提交草稿，失败保留环境外的 deleting 记录。

        :param row: 外层 owner/profile 锁内读取的环境
        :param generation: 页面看到的草稿代次
        :param manager: 登录管理器，用于收口同名会话
        :return: None；仅完整完成时返回
        """
        with self.runtime.environment_lock(row["environment_id"]):
            row = self.row(row["environment_id"])
            if row is None:
                return
            record = self.guard(row, generation)
            root = self.runtime._root(row)
            profile = self.runtime.data / "profiles" / row["name"]
            self._safe_tree(root, self.runtime.data / "environments")
            self._safe_tree(profile, self.runtime.data / "profiles")
            container = None
            if row["container_id"]:
                try:
                    container = self.runtime._container(row)
                except NotFound:
                    pass
            with manager._lock:
                sessions = [session for session in manager.sessions.values() if session.name == row["name"]]
            job = self.runtime.jobs.get(row["environment_id"])
            if job and (not sessions or job["source"] not in {"login:" + session.sid for session in sessions}):
                raise ValueError("环境有其他活动工作，不能清理")
            if self.runtime._running_sender_active(row):
                raise ValueError("账号发送连接尚未收口")
            if not job and (root / "runtime" / "execution.json").exists():
                raise ValueError("遗留执行尚未对账，不能清理")
            self.save(row, phase="deleting", deleting_at=time.time())
            for session in sessions:
                manager.cleanup(session.sid)
            if row["environment_id"] in self.runtime.jobs:
                raise ValueError("登录执行尚未收口")
            if container:
                container.stop(timeout=5)
                container.remove()
            for path in (root, profile):
                if path.exists():
                    shutil.rmtree(path)
            # 先完成外部资源清理，最后写 DB；标记在目录外，部分失败仍能发现。
            with self.db_lock:
                connection = self.database()
                try:
                    with connection:
                        cursor = connection.execute("DELETE FROM account_environments WHERE environment_id=? AND account_id IS NULL AND name=?",
                            (row["environment_id"], row["name"]))
                        if cursor.rowcount == 0 and connection.execute("SELECT 1 FROM account_environments WHERE environment_id=?", (row["environment_id"],)).fetchone():
                            raise ValueError("环境已提交，拒绝删除正式账号")
                finally:
                    connection.close()
            self._path(row["environment_id"]).unlink(missing_ok=True)
