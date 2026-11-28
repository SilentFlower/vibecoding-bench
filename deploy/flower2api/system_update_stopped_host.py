"""由固定宿主在原更新门禁中核对历史停止环境，结果仅限本次挑战。"""

from contextlib import closing
from hashlib import sha256
import json
import os
import re
import sqlite3

from runtime_files import directory_fd
from system_update_contract import BUILD_RE, SHA_RE, safe_read, strict_json, validate_release, verify_signed
from system_update_gate import read_gate
from system_update_host import docker

_ROUTE = "/internal/v3/system-updates/stopped-activity"
_COLUMNS = {"cli": "container_id", "network": "network_container_id", "sender": "sender_container_id"}
_SCOPE_KEYS = {
    "deployment",
    "operation_id",
    "epoch",
    "challenge",
    "environment_id",
    "account_id",
    "generation",
    "profile_name",
    "role_ids",
    "draft",
    "nodes",
}


def _same(left, right):
    # 避免 Python 的 True == 1 混淆数据库整数身份。
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _frozen(engine, scope):
    host = engine.backend
    gate = read_gate(host.gate, host.policy["deployment"])
    if (
        gate["phase"] != "blocked"
        or any(scope.get(k) != gate[k] for k in ("deployment", "operation_id", "epoch"))
        or engine.state.get("active_operation") != gate["operation_id"]
    ):
        raise ValueError("原平台维护门禁不再持有本次操作")
    op = engine._operation(gate["operation_id"])
    if (
        op.get("operation_id") != gate["operation_id"]
        or op.get("epoch") != gate["epoch"]
        or op.get("target_release") != gate["target_release"]
        or op.get("revision") != gate["revision"]
        or op.get("cancel_requested")
        or op.get("release_started")
        or op.get("phase")
        not in ("draining", "switching", "snapshotting", "migrating", "verifying", "restoring", "reconcile")
    ):
        raise ValueError("原维护操作或发行身份已变化")
    return gate


def _db(path):
    # 只读打开原账本，不为缺失的部署创建数据库。
    if path.resolve() != path:
        raise ValueError("维护数据库路径含有链接")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
    db.row_factory = sqlite3.Row
    return db


def _registration(host, scope):
    with closing(_db(host.data / "bench/db.sqlite")) as db:
        db.execute("BEGIN")
        env, account = scope["environment_id"], scope["account_id"]
        row = db.execute("SELECT * FROM account_environments WHERE environment_id=?", (env,)).fetchone()
        if (
            row is None
            or row["state"] != "stopped"
            or row["name"] != scope["profile_name"]
            or row["generation"] != scope["generation"]
            or row["account_id"] != account
            or not _same(scope["role_ids"], {role: row[column] for role, column in _COLUMNS.items()})
            or db.execute(
                "SELECT 1 FROM accounts WHERE id=? OR name=? COLLATE NOCASE OR profile_path=?",
                (account, row["name"], "profiles/" + row["name"]),
            ).fetchone()
            or db.execute("SELECT 1 FROM account_node_assignments WHERE account_id=?", (account,)).fetchone()
        ):
            raise ValueError("历史账号、环境或角色登记不符")
        draft = db.execute(
            "SELECT node_id,operation_id,phase,revision,saved_account_id FROM node_login_drafts "
            "WHERE environment_id=?",
            (env,),
        ).fetchone()
        nodes = [
            dict(item)
            for item in db.execute(
                "SELECT id,node_key,kind,revision FROM cluster_nodes WHERE deleted_at IS NULL ORDER BY id"
            )
        ]
        if (
            not _same(scope["nodes"], nodes)
            or not _same(scope["draft"], dict(draft) if draft else None)
            or [n["node_key"] for n in nodes if n["kind"] == "local"] != ["local"]
            or any(n["kind"] not in ("local", "ssh") for n in nodes)
            or draft
            and (
                draft["phase"] != "closed"
                or draft["saved_account_id"] not in (None, account)
                or not any(n["kind"] == "ssh" and n["id"] == draft["node_id"] for n in nodes)
            )
        ):
            raise ValueError("冻结节点或历史草稿与本部署不符")
        return db.execute(
            "SELECT COUNT(*) FROM node_executions WHERE environment_id=? OR account_id=?", (env, account)
        ).fetchone()[0]


def _entries(path, *, names=True):
    try:
        fd = directory_fd(path)
    except FileNotFoundError:
        return None
    try:
        return os.listdir(fd) if names else True
    finally:
        os.close(fd)


def _gateway(host, scope):
    gateway = host.request("gateway", "/admin/runtime/system-update/status")
    if (
        gateway.get("phase") != "blocked"
        or any(gateway.get(k) != scope[k] for k in ("deployment", "operation_id", "epoch"))
        or type(gateway.get("active")) is not int
        or gateway["active"] != 0
        or gateway.get("tui_tool_pending") is not False
    ):
        raise ValueError("网关同代活动或工具回执尚未收口")
    return gateway


def _leases(host):
    # 原账号映射已经删除，不能把 Bench 账号 ID 当作网关 ID。取实际队列并纳入已删除账号遗留的持久租约。
    controls = host.controls()
    configured = [v for v in controls["gateway"]["Config"]["Env"] if v.startswith("V3_LEASE_DIR=")]
    if configured != ["V3_LEASE_DIR=/data/leases"]:
        raise ValueError("网关实际租约目录待核对")
    with closing(_db(host.data / "gateway/gateway.sqlite")) as db:
        ids = [row[0] for row in db.execute("SELECT id FROM accounts ORDER BY id")]
    held = 0
    active_files = set()
    for account in ids:
        status = host.request("gateway", f"/admin/runtime/accounts/{int(account)}/lease")
        if (
            not isinstance(status.get("holders"), list)
            or "lease" not in status
            or any(type(status.get(k)) is not int or status[k] != 0 for k in ("active", "waiting", "importing"))
            or (status["lease"] is None) != (not status["holders"])
        ):
            raise ValueError("网关账号队列仍有在途活动或身份不完整")
        held += len(status["holders"])
        if status["holders"]:
            active_files.add(f"{account}.json")
    # 正常释放最后一项后网关会删除持久文件。跨快照出现的条目保守等待下一次观察。
    if set(_entries(host.data / "gateway/leases") or []) - active_files:
        raise ValueError("网关仍有未归属到实际账号的持久租约")
    return held


def _image(host, environment, runtime, binding):
    try:
        registered = strict_json(safe_read(runtime / "account-image.json", private=True))
    except FileNotFoundError:
        registered = None
    sources = {
        item
        for item in (binding.get("release_id"), registered.get("release") if registered else None)
        if item is not None
    }
    if len(sources) != 1:
        raise ValueError("历史 sender 或原镜像登记的发行缺失或不一致")
    (source,) = sources
    if not isinstance(source, str) or not BUILD_RE.fullmatch(source):
        raise ValueError("原 sender 缺少可核验的账号发行")
    folder = host.root / "releases" / ("system-" + source)
    raw = safe_read(folder / "system-release.json")
    release = validate_release(
        verify_signed(raw, safe_read(folder / "system-release.sig", 64), host.policy["public_key"])
    )
    entry = release["account"]
    if release["release"] != folder.name or entry["release"] != source:
        raise ValueError("原账号签发来源不符")
    # 先按签发引用检查引擎的镜像表示，再由编排器与三个冻结容器逐一核对。
    image = json.loads(docker("image", "inspect", entry["reference"], timeout=4))[0]
    labels = image["Config"]["Labels"]
    if (
        labels.get("vibebench.role") != "account"
        or labels.get("vibebench.product") != "v3"
        or labels.get("vibebench.release") != source
        or labels.get("vibebench.parent-revision") != entry["revision"]
        or image.get("Os") != "linux"
        or image.get("Architecture") != "amd64"
    ):
        raise ValueError("签发账号镜像的实际来源待核对")
    (field,) = [name for name in ("registry_digest", "config_digest") if image.get("Id") == entry[name]]
    if registered is not None and (
        not _same(registered.get("schema_version"), 1)
        or registered.get("environment_id") != environment
        or registered.get("release") != source
        or registered.get("reference") not in (entry["reference"], entry["reference"].rsplit("/", 1)[-1])
        or registered.get("image_id") != image["Id"]
        or not _same(registered.get("protocol"), 1)
    ):
        raise ValueError("原环境镜像登记和签发选择冲突")
    return {
        "system_release": release["release"],
        "manifest_sha256": sha256(raw).hexdigest(),
        "account_release": source,
        "registry_digest": entry["registry_digest"],
        "config_digest": entry["config_digest"],
        "engine_digest": field,
    }


def stopped_evidence(engine, scope):
    """读取同一冻结操作、登记、节点活动及签名来源，不持更新器锁等待编排或 SSH。

    :param engine: 已初始化的独立系统更新器。
    :param scope: 经本机 socket 认证的原编排挑战。
    :return: 仅限本次环境及挑战的脱敏读回；证据缺失时抛出异常。
    """
    if (
        set(scope) != _SCOPE_KEYS
        or not isinstance(scope["environment_id"], str)
        or not re.fullmatch("[a-f0-9]{32}", scope["environment_id"])
        or not isinstance(scope["challenge"], str)
        or not re.fullmatch("[a-f0-9]{32}", scope["challenge"])
        or type(scope["account_id"]) is not int
        or scope["account_id"] <= 0
        or type(scope["generation"]) is not int
        or scope["generation"] <= 0
        or not isinstance(scope["profile_name"], str)
        or scope["profile_name"] in ("", ".", "..")
        or "/" in scope["profile_name"]
        or "\x00" in scope["profile_name"]
        or not isinstance(scope["role_ids"], dict)
        or set(scope["role_ids"]) != set(_COLUMNS)
        or any(not isinstance(value, str) or not SHA_RE.fullmatch(value) for value in scope["role_ids"].values())
        or len(set(scope["role_ids"].values())) != len(_COLUMNS)
    ):
        raise ValueError("原环境维护读取范围无效")
    host = engine.backend
    first = _frozen(engine, scope)
    host.values()
    registered_executions = _registration(host, scope)
    executions = registered_executions
    gateway = _gateway(host, scope)
    leases = _leases(host)
    env = scope["environment_id"]
    root = host.data / "bench/environments" / env
    runtime = root / "runtime"
    dirs = [
        name
        for name, path in [
            ("home", root / "home"),
            ("runtime", runtime),
            ("profile", host.data / "bench/profiles" / scope["profile_name"]),
        ]
        if _entries(path, names=False) is not None
    ]
    identity, image = None, None
    if "runtime" in dirs:
        binding = strict_json(safe_read(runtime / "sender/sender.json")).get("binding")
        if (
            not isinstance(binding, dict)
            or binding.get("environment_id") != env
            or not _same(binding.get("generation"), scope["generation"])
        ):
            raise ValueError("原中央 sender 登记或代次不符")
        identity = [env, scope["generation"]]
        executions += len(_entries(runtime / "executions") or [])
        if (runtime / "execution.json").exists():
            executions += 1
        if scope["draft"] is None:
            image = _image(host, env, runtime, binding)
    activity_scope = {key: scope[key] for key in ("operation_id", "epoch", "environment_id", "challenge")}
    activity = host.request("orchestrator", _ROUTE, activity_scope)
    if activity.get("scope") != activity_scope or type(activity.get("jobs")) is not int or activity["jobs"] < 0:
        raise ValueError("编排活动身份待核对")
    local = {
        "engine_id": docker("info", "--format", "{{.ID}}", timeout=4).strip(),
        "phase": first["phase"],
        "operation_id": first["operation_id"],
        "epoch": first["epoch"],
        "directories": dirs,
        "binding": identity,
        "jobs": activity["jobs"],
        "executions": executions,
        "leases": leases,
        "pending_receipts": int(gateway["tui_tool_pending"]),
    }
    nodes = {"local": local}
    for node in scope["nodes"]:
        if node["kind"] == "ssh":
            from stopped_node_observation import observe_stopped_node

            nodes[node["node_key"]] = observe_stopped_node(host, scope, node)
    if local["leases"] == 0 and _leases(host) != 0:
        raise ValueError("读回期间出现新的网关租约")
    if _registration(host, scope) != registered_executions:
        raise ValueError("原登记或执行读回期间发生变化")
    _gateway(host, scope)
    if _frozen(engine, scope) != first:
        raise ValueError("读回期间原维护门禁已变化")
    return {"scope": scope, "nodes": nodes, "image": image}
