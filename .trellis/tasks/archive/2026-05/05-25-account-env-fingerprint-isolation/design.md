# 技术设计

## 1. 模块边界

```
┌─────────────────────────────────────────────────────────────────┐
│ orchestrator/main.py                                            │
│                                                                 │
│  ┌─────────────────────────┐                                    │
│  │ derive_fingerprint(name)│ ← 新增,纯函数,无 IO              │
│  └────────────┬────────────┘                                    │
│               │ 返回 dict: { hostname, mac, tz, lang,           │
│               │              machine_id }                       │
│               ▼                                                 │
│  ┌─────────────────────────┐   ┌────────────────────────────┐   │
│  │ Runner.start_run        │   │ LoginManager.start         │   │
│  │  (task 模式)            │   │  (login 模式)              │   │
│  └────────────┬────────────┘   └────────────┬───────────────┘   │
│               │ 注入到容器创建参数                                │
│               ▼                              ▼                  │
│  ┌─────────────────────────┐   ┌────────────────────────────┐   │
│  │ login_commit            │ ← 新增 in-flight run 校验 +      │
│  │  (existing)             │   profile 清理(telemetry+backups)│
│  └─────────────────────────┘                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ docker run --hostname=... --mac-address=...
                              │           -e ACC_NAME=... -e TZ=... -e LANG=...
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ images/worker/entrypoint.sh                                     │
│                                                                 │
│  ① CA 注入(unchanged)                                          │
│  ② [new] 若 ACC_NAME 非空 → 写 /etc/machine-id                  │
│  ③ profile cp 后 [new] rm -rf .../telemetry .../backups         │
│  ④ tmux + claude 启动(unchanged)                               │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 派生函数契约

```python
def derive_fingerprint(account_name: str) -> dict:
    """
    从账号名派生稳定的环境指纹。纯函数,同名输入必出同结果。

    返回字段:
      hostname:   str,形如 "vb-<8 hex>",11 字符,符合 Docker hostname
      mac:        str,形如 "02:xx:xx:xx:xx:xx",sidecar 的 mac_address
      tz:         str,IANA 时区名
      lang:       str,locale 字符串(en_US.UTF-8 等)
      machine_id: str,32 位小写 hex
      mem:        str,Docker mem_limit("4g"/"8g"/"16g"/"32g")

    候选池(锁定,排除与中文出口 IP 强相关的 zh_CN.UTF-8 / Asia/Shanghai):
      TZ_POOL  = ["Asia/Tokyo","Asia/Singapore","Asia/Seoul",
                  "Australia/Sydney","Europe/London","Europe/Berlin","Europe/Paris",
                  "America/Los_Angeles","America/New_York","America/Chicago"]   # 10
      LANG_POOL = ["en_US.UTF-8","ja_JP.UTF-8","ko_KR.UTF-8",
                   "de_DE.UTF-8","fr_FR.UTF-8"]                                  # 5
      MEM_POOL  = ["4g","8g","16g","32g"]                                        # 4
                  # 刻意避开 2g —— 防止 compile/test 重题 OOM 污染评测

    派生规则:
      seed = sha256(account_name.encode("utf-8")).digest()    # 32 字节
      hostname   = "vb-" + seed[0:4].hex()                    # 8 hex
      mac_bytes  = bytes([0x02]) + seed[1:6]                  # 6 字节
      mac        = ":".join(f"{b:02x}" for b in mac_bytes)
      tz         = TZ_POOL[seed[6] % len(TZ_POOL)]
      lang       = LANG_POOL[seed[7] % len(LANG_POOL)]
      machine_id = sha256(account_name.encode("utf-8")).hexdigest()[:32]
      mem        = MEM_POOL[seed[8] % len(MEM_POOL)]
    """
```

**字节切片决策**:
- hostname / MAC 用 `seed[0:4] / seed[1:6]` 故意有 1 字节重叠 — 这样 hostname 和 MAC 在视觉上有弱关联,但不会造成熵冲突;
- TZ / LANG / MEM 用单字节模运算(seed[6/7/8]),池子均小于 256,均匀分布;
- machine-id 用完整 sha256 前 32 hex,与 hostname 独立(不复用前 4 字节)。

**为什么用 Docker mem_limit 而非 NODE_OPTIONS=--max-old-space-size**:
- mem_limit 走 cgroup,Node 的 `process.constrainedMemory()` / `os.totalmem()` **都**会读到,影响面广
- NODE_OPTIONS 只影响 V8 heap 上限,不动 totalmem;Claude Code 上报的内存指标里 totalmem 是核心字段
- mem_limit 配合 memswap_limit 同值,可以禁止 Node 走 swap → 被 oom-killer 杀比走 swap 死撑更明确

## 3. 数据流

### 3.1 task 模式

```
orchestrator.run_task(task_id)
  → 查 task + account
  → scheduler.submit(run_id, account, task)
    → Runner.start_run(run_id, account, task)
      → fp = derive_fingerprint(account["name"])
      → docker.containers.run(SIDECAR_IMAGE,
                              hostname=fp["hostname"],
                              mac_address=fp["mac"],
                              environment={UPSTREAM_SOCKS5_*, ...})
      → docker.containers.run(WORKER_IMAGE,
                              hostname=fp["hostname"],
                              network_mode=f"container:{sidecar_name}",
                              environment={
                                "TASK_PROMPT", "RUN_ID", "TIMEOUT_SEC",
                                "ACC_NAME": account["name"],
                                "TZ": fp["tz"],
                                "LANG": fp["lang"],
                                "LC_ALL": fp["lang"],
                              })
      ↓
  worker entrypoint:
    → 装 CA
    → if [ -n "$ACC_NAME" ]; then
        echo "$(printf %s "$ACC_NAME" | sha256sum | cut -c1-32)" > /etc/machine-id
      fi
    → cp -a /mnt/profile/. /root/.claude/
    → rm -rf /root/.claude/telemetry /root/.claude/backups
    → 注入 Stop hook → tmux → claude
```

### 3.2 login 模式

```
orchestrator.login_start(name, socks5)
  → LoginManager.start(name, socks5)
    → fp = derive_fingerprint(name)
    → if socks5.host: docker.containers.run(SIDECAR_IMAGE,
                                            hostname=fp["hostname"],
                                            mac_address=fp["mac"], ...)
    → docker.containers.run(WORKER_IMAGE,
                            hostname=fp["hostname"],
                            tty=True, stdin_open=True,
                            environment={
                              "WORKER_MODE": "login",
                              "ACC_NAME": name,
                              "TZ": fp["tz"],
                              "LANG": fp["lang"],
                              "LC_ALL": fp["lang"],
                            })
      ↓
  worker entrypoint (login 分支):
    → 装 CA
    → if [ -n "$ACC_NAME" ]; then echo "$machine_id" > /etc/machine-id; fi
    → exec tail -f /dev/null
```

login 模式 entrypoint 的 machine-id 写入需要放在 `if [ "$WORKER_MODE" = "login" ]` 分支**之前**(否则 login 路径会跳过)。具体位置见 implement.md。

### 3.3 login_commit

```
login_commit(sid, body)
  → session = login_manager.get(sid)
  → [NEW] check_no_inflight_runs(session.name)
       SQL: SELECT COUNT(*) FROM runs r JOIN accounts a ON r.account_id=a.id
            WHERE a.name=? AND r.status IN ('queued','running')
       若 > 0 → raise HTTPException(409, f"account '{name}' has N in-flight run(s)")
       注意:account 可能尚未入库(首次登录),此时计数必为 0,自然通过
  → status = login_manager.auth_status(sid)
  → if not loggedIn → 422
  → [NEW] cleanup_profile_residue(session.name)
       host_profile = HOST_BENCH_DATA / "profiles" / session.name
       但 orchestrator 容器内看到的是 BENCH_DATA / "profiles" / session.name
       → 用 BENCH_DATA 路径做 rm(orchestrator 自己读写)
       → shutil.rmtree(BENCH_DATA / "profiles" / name / "telemetry", ignore_errors=True)
       → shutil.rmtree(BENCH_DATA / "profiles" / name / "backups",   ignore_errors=True)
  → 写 accounts 表(INSERT or UPDATE socks5)
  → login_manager.cleanup(sid)
```

**路径选择关键点**: orchestrator 容器内能看到 `BENCH_DATA=/data`(挂的就是 `./data`),而 `HOST_BENCH_DATA` 只用于给子容器报告挂载点。**做文件清理用 `BENCH_DATA`,不要用 `HOST_BENCH_DATA`** —— 后者在 orchestrator 容器内是不存在的路径。这一点是个易错点,implement 步骤里会显式校验。

## 4. 兼容性 & 回滚

### 4.1 现有数据兼容
- `data/profiles/smoketest/` 不变,派生函数 stateless,首次启用即生效
- 已有 `telemetry/1p_failed_events.*.json` 在源 profile 中保留(可被 mitmproxy 抓取分析),只是不再被 run 内 Claude Code 重放
- 已有 `accounts` 表 schema 不变,无 migration

### 4.2 worker entrypoint 向下兼容
- `ACC_NAME` 用 `${ACC_NAME:-}` 处理 missing → 不写 machine-id,不影响 legacy 路径
- 这是 `scripts/init-account.sh` legacy CLI 的安全网(它不知道账号名,但也不应崩)

### 4.3 回滚策略
- 单 commit 容易回滚:`git revert` 即恢复
- 派生函数即便存在,只要 `Runner.start_run` / `LoginManager.start` 不调用,行为完全等同 P0
- 中间状态(派生函数加了但未接入)安全,可分两次 PR

## 5. 显式 trade-off / 风险

| 项 | 接受的代价 |
|---|---|
| TZ 不同导致评测题答案差异 | 在 PRD 非目标里承认 "账号是 confounding variable",评测口径需要标注 |
| 镜像未装 ko_KR / fr_FR 等 locale | LANG 字面值仍是有效指纹(Claude Code 直接读 env 字符串,不需要 locale 实际生效) |
| account_name 与 machine-id 一对一 | 同名账号删除重建会拿到相同指纹 — 视为期望行为(用户语义上是"同一身份")  |
| MAC 第 1 字节固定 `0x02` | 所有账号都是"locally administered" 标志,理论上是弱信号(但远不如 OAuth token 区分度高) |
| login 模式无 socks5 时跳过 sidecar | 此时 worker 直接走 `bridge` 网络,MAC 由 Docker 分配 — 无法控制。但这条路径已被 README 标"用户自担风险" |

## 6. 不在本次 design 范围
- mitmproxy recorder 改造(D 不再统计 only-anthropic)
- accounts 表加 SOCKS5 唯一性约束
- /etc/machine-id 之外的 dbus machine-id(`/var/lib/dbus/machine-id`)— Claude Code 是 Node 程序,不读 dbus
- TLS JA3 / HTTP2 settings 指纹 — 这层是 Claude Code 编译时决定,改不动
