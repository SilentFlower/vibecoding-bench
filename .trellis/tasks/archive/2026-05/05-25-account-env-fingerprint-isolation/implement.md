# 实施计划

## 改动文件清单

| 文件 | 改动性质 | 行数估计 |
|---|---|---|
| `orchestrator/main.py` | 增 `derive_fingerprint`(含 mem)、改 `Runner.start_run` / `LoginManager.start` / `login_commit` | +65 / -5 |
| `images/worker/entrypoint.sh` | 增 machine-id 写入、telemetry/backups 清理 | +10 / -0 |

**不动**: `docker-compose.yml`、`Dockerfile`(任一)、`webui/`、`scripts/init-account.sh`、DB schema。

## 执行顺序

### 步骤 1: 派生函数(可独立验证)

文件: `orchestrator/main.py`

在 `# ============== Docker 运行器 ==============` 注释**之前**(即 `class Runner:` 上方),增加纯函数 + 候选池常量:

```python
import hashlib

_TZ_POOL = [
    "Asia/Shanghai", "Asia/Tokyo", "Asia/Singapore", "Asia/Seoul",
    "Australia/Sydney", "Europe/London", "Europe/Berlin", "Europe/Paris",
    "America/Los_Angeles", "America/New_York", "America/Chicago",
]
_LANG_POOL = [
    "en_US.UTF-8", "zh_CN.UTF-8", "ja_JP.UTF-8", "ko_KR.UTF-8",
    "de_DE.UTF-8", "fr_FR.UTF-8",
]


def derive_fingerprint(account_name: str) -> dict[str, str]:
    """
    按账号名 hash 派生稳定环境指纹。详见 design.md §2。

    :param account_name: 账号名(已被 _ACC_NAME_RE 校验为 [a-zA-Z0-9_-]+)
    :return: {hostname, mac, tz, lang, machine_id}
    """
    digest = hashlib.sha256(account_name.encode("utf-8")).digest()
    hostname = "vb-" + digest[0:4].hex()
    mac_bytes = bytes([0x02]) + digest[1:6]
    mac = ":".join(f"{b:02x}" for b in mac_bytes)
    return {
        "hostname": hostname,
        "mac": mac,
        "tz": _TZ_POOL[digest[6] % len(_TZ_POOL)],
        "lang": _LANG_POOL[digest[7] % len(_LANG_POOL)],
        "machine_id": digest.hex()[:32],
    }
```

**验证(无需启容器)**:
```bash
docker compose exec orchestrator python3 -c "
from main import derive_fingerprint
import json
for n in ['smoketest','main','alice','bob']:
    print(n, json.dumps(derive_fingerprint(n), ensure_ascii=False))
"
```
预期: 同名两次结果一致; 4 个名字结果不同。

### 步骤 2: task 模式接入(Runner.start_run)

文件: `orchestrator/main.py` 的 `Runner.start_run`(约 154-212 行)

修改点:
1. 函数开头(`acc_name = account["name"]` 之后)加 `fp = derive_fingerprint(acc_name)`
2. sidecar `containers.run(...)` 加参数 `hostname=fp["hostname"]`,`mac_address=fp["mac"]`
3. worker `containers.run(...)` 加参数 `hostname=fp["hostname"]`
4. worker `environment` 增 4 项: `ACC_NAME / TZ / LANG / LC_ALL`

注意:不动 `network_mode=f"container:{sidecar_name}"` —— worker 仍共享 sidecar netns,出口 MAC 自然就是 sidecar 的。

### 步骤 3: login 模式接入(LoginManager.start)

文件: `orchestrator/main.py` 的 `LoginManager.start`(约 280-353 行)

同步骤 2 改造,**注意**:
- 即便 `socks5.host` 为空(无 sidecar 路径),worker 仍要设 `hostname/TZ/LANG/ACC_NAME` —— 这条路径走 bridge 网络,MAC 我们控不了,但其他维度还是要保持一致
- sidecar 分支才设 `mac_address`

### 步骤 4: login_commit 加 in-flight 校验 + 清理

文件: `orchestrator/main.py` 的 `login_commit`(约 717-785 行)

修改点:
1. 函数开头校验 `session` 之后,执行 in-flight 检查(SQL 见 design.md §3.3),失败抛 409
2. `if not status.get("loggedIn")` 已抛 400 → 改为 422(语义更准)?**保留 400 不改**,避免与现有前端 alert 不一致;只增不改
3. `cleanup_profile_residue(name)` 在写 accounts 表 **之前**调用:
   ```python
   import shutil
   prof = BENCH_DATA / "profiles" / name
   shutil.rmtree(prof / "telemetry", ignore_errors=True)
   shutil.rmtree(prof / "backups",   ignore_errors=True)
   ```
4. import shutil 加在文件顶部(已有 import sqlite3 / threading 等,跟着加)

**易错**: 必须用 `BENCH_DATA`(orchestrator 容器内路径),不要用 `HOST_BENCH_DATA`(那是给 docker daemon 报告挂载用的宿主路径,orchestrator 容器内访问不到)。

### 步骤 4b: derive_fingerprint 加 mem 维度 + 两处 containers.run 加 mem_limit

文件: `orchestrator/main.py`

修改点:
1. `derive_fingerprint` 返回 dict 加 `"mem": _MEM_POOL[digest[8] % len(_MEM_POOL)]`
2. 文件顶层加 `_MEM_POOL = ["4g", "8g", "16g", "32g"]`(放在 `_LANG_POOL` 下方)
3. `Runner.start_run` 的 worker `containers.run` 加 `mem_limit=fp["mem"]`, `memswap_limit=fp["mem"]`
4. `LoginManager.start` 的 worker `containers.run` 同步加(login 路径也要)
5. **不动** sidecar 的 mem(轻量,统一)

### 步骤 5: worker entrypoint 机器指纹 + 清理

文件: `images/worker/entrypoint.sh`

修改两处:

**5a**: 在 `# ---------- 1) MITM CA 注入 ----------` 注释**之前**(即 `log() {...}` 之后),增加 machine-id 写入。这样无论 task 还是 login 模式都生效:

```bash
# ---------- 0) machine-id (按账号名 hash, 任 worker 模式都先写) ----------
if [ -n "${ACC_NAME:-}" ]; then
  printf %s "$ACC_NAME" | sha256sum | cut -c1-32 > /etc/machine-id
  log "Wrote /etc/machine-id from ACC_NAME hash"
fi
```

**5b**: 在 task 模式 `cp -a /mnt/profile/. /root/.claude/`(行 64)**之后**立即增加清理:

```bash
  # 不让历史 telemetry / backups 在每次 run 重放
  rm -rf /root/.claude/telemetry /root/.claude/backups
```

注意保持原有 if/else 结构 ——`cp` 在 `if [ -d /mnt/profile ]` 分支内,清理也要在 then 块内 cp 后立即。

### 步骤 6: 镜像重建 + 重启

```bash
cd /root/project/vibecoding-bench

# 1. worker 镜像(entrypoint.sh 改了)
docker compose --profile build build worker-image

# 2. orchestrator 镜像(main.py 在 Dockerfile 里是 COPY,不是挂载)
docker compose build orchestrator

# 3. 重建容器并启动(--force-recreate 让它加载新 image)
docker compose up -d --force-recreate orchestrator
```

(sidecar 不动,不需要 rebuild)

⚠ 注意: `docker compose restart` **不够** —— restart 只是重启容器进程,仍用旧 image。代码已 `COPY` 进镜像的必须 `--force-recreate`。

## 验证(对应 PRD 验收)

### V1: 派生函数单测(对应 A1/A2/A8)
```bash
docker compose exec orchestrator python3 -c "
from main import derive_fingerprint
a1 = derive_fingerprint('smoketest')
a2 = derive_fingerprint('smoketest')
a3 = derive_fingerprint('other')
assert a1 == a2, 'same name must give same fp'
assert a1 != a3, 'different name must give different fp'
print('OK', a1)
"
```

### V2: 同账号两次 run 一致(对应 A1)
对 smoketest 触发同一 task 两次,各 ssh 进 worker 容器(在容器存活窗口期内):
```bash
docker exec bench-worker-<run_id> sh -c 'cat /etc/hostname; cat /etc/machine-id; echo TZ=$TZ; echo LANG=$LANG'
```
两次输出应完全相同。MAC 验:`docker exec bench-sidecar-<run_id> ip link show eth0 | grep ether`。

### V3: 不同账号 run 不同(对应 A2)
对账号 A、账号 B 各触发一次,V2 的五项**均不同**。

### V4: telemetry replay 阻断(对应 A3/A4)
```bash
# 注入测试文件
echo '{"test":true}' > data/profiles/smoketest/telemetry/1p_failed_events.test.json
# 记录源 mtime
stat -c %Y data/profiles/smoketest/telemetry/1p_failed_events.test.json
# 跑 task,容器存活窗口期内 exec
docker exec bench-worker-<run_id> ls /root/.claude/telemetry 2>&1
# 应输出:目录不存在,或为空目录
# run 结束后再 stat 源文件,mtime 不变
```

### V5: login 清理(对应 A5)
- 走一次 login 流程,commit 前在源 profile 放测试 telemetry 文件
- commit 成功后 `ls data/profiles/<name>/telemetry/ data/profiles/<name>/backups/` 应不存在或为空

### V6: in-flight 拒绝(对应 A6)
- 触发账号 X 的 task 让它进 running 状态
- 此时 curl POST login_commit:应 HTTP 409 + 含 "in-flight" 字样
- 等 task 跑完,再 commit:应 200 入库

### V7: login/task 指纹一致(对应 A9)
- 启一个 login 会话(账号 Z),在 worker 里取五项
- 用账号 Z 跑一次 task,在 task worker 里取五项
- 对比必须一致

### V8: 烟雾测试(对应 A7)
- `docker logs vibebench-orchestrator` 无 ERROR
- `init-account.sh foo`(legacy CLI)应能正常起容器,profile 落盘

## Review Gates

- **写完 design+implement 后** → 暂停,等用户 review 三件套,然后 `task.py start`
- **步骤 1 完成后** → V1 通过才进入步骤 2
- **步骤 5 完成后** → 重建镜像前,人工 diff 一遍 entrypoint,确认 if/then 嵌套没破
- **全部完成后** → V2–V8 全过 → `trellis-check-all` → 提交

## Rollback Points

| 阶段 | 状态 | 回滚方式 |
|---|---|---|
| 步骤 1 完成 | 只增了函数,未接入 | 无需回滚(代码无副作用) |
| 步骤 2-3 完成 | task / login 起容器带新参数 | `git revert <commit>` 重启 orchestrator |
| 步骤 4 完成 | login_commit 行为变更 | 同上 |
| 步骤 5 完成 | 镜像变了 | revert + `docker compose build worker-image` 重建 |

## 子代理(若启用)

本任务 SLOC 小、文件少,**建议主代理直连 implement**,不必拆 subagent。如果走 sub-agent,manifest 应包含:
- 实现侧:`orchestrator/main.py`、`images/worker/entrypoint.sh`、`design.md` 全文
- 检查侧:`prd.md`、`design.md`、`implement.md`、改动后的两个文件
