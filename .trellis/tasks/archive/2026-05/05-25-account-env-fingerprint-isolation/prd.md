# 账号环境指纹差异化 + 遥测重放清理

## 背景

vibecoding-bench 用一个 Docker 镜像(`vibebench-worker:latest`)+ 一份账号 OAuth profile 跑真实的 Claude Code。当前实现存在两类遥测面相关的问题:

1. **遥测重放**: 账号 profile 里 `telemetry/1p_failed_events.*.json` 是 Claude Code 上次未上传成功的事件缓存。因为 worker entrypoint 每次 `cp -a /mnt/profile/. /root/.claude/`,这些"上次没传上去的尾巴"会在每次 run 启动时被重新尝试上传。其中 `1p_failed_events` 文件名里嵌入的两个 UUID 是 Claude Code 刻在 profile 里的稳定 first-party identifier,跟着账号走。
2. **机器画像异常**: 当前所有账号、所有 run 共用同一镜像 → hostname 每 run 随机(同账号不稳定),`/etc/machine-id` / TZ / LANG / Node 版本完全相同(跨账号无差异)。从 Anthropic 端看,**同账号像是不停换设备,跨账号像是同一台机器开了多份**,与"多账号独立用户"的语义相反。

附加: login 模式直接 rw 挂 profile,OAuth 启动会真的写进 `telemetry/` + `backups/`,这些痕迹会被后续 task 模式 run 一路携带。

## Goal

让 Anthropic 端遥测看到的画像满足:
- **同账号跨 run 一致**: hostname / MAC / TZ / locale / machine-id 稳定不变
- **跨账号不同**: 上述维度按账号确定性派生,各账号互不相同
- **不累积历史尾巴**: profile 里的 `telemetry/failed_events` 不再被每个 run 重放
- **login 自带的遥测残留**不被后续 task run 继承

**非目标**:
- 不关闭 Claude Code 自带遥测(关掉本身就是强信号,且不符合 TOS 期望)
- 不修改 MITM 抓包链路 / stats.jsonl 统计口径
- 不改并发模型 / 调度策略
- 不改账号注册 / 题库 / 评测 UI

## Requirements

### R1. profile 遥测重放清理(task 模式)
- worker `entrypoint.sh` 在 `cp -a /mnt/profile/. /root/.claude/` 之后,立即 `rm -rf /root/.claude/telemetry`
- **只清运行时副本**,绝不动 `/mnt/profile`(ro 源)
- `backups/` 处理: **默认一起清**(理由: 这是 Claude Code 写的旧 `.claude.json` 备份,对 run 无功能影响,且大小会随时间增长)
- 本次 run 期间 Claude Code 自身可正常生成新的 telemetry/backups 到 `/root/.claude/`,容器销毁随之消失

### R2. login 提交时的 profile 残留清理
- `login_commit` 在认证成功、入库**之前**,清除宿主 `data/profiles/<name>/telemetry/` 和 `data/profiles/<name>/backups/`
- **路径安全**: 仅用 `session.name`(已被 `_ACC_NAME_RE` 校验为 `[a-zA-Z0-9_-]+`)拼路径,杜绝跨账号误删
- **并发安全**: commit 前查 `runs` 表,若该账号存在 `status IN ('queued','running')` 的 run,**拒绝 commit** 并返回明确错误,让用户先等任务结束再重新登录
- `LoginManager._name_locks` 已保证同账号不会并发 login,无需重复处理

### R3. 按账号派生稳定的环境指纹
派生算法: `seed = sha256(account_name)`,从 seed 不同字节切片各维度。

| 维度 | 派生方式 | 注入点 |
|---|---|---|
| `hostname` | `vb-{seed[0:4].hex()}`(11 字符,符合 DNS label) | sidecar 和 worker 容器 `hostname=` 参数(两者要一致, worker 共享 sidecar netns 但 `/etc/hostname` 各自独立) |
| sidecar MAC | `02:` + seed[0:5] 各字节(`0x02` 高位 = 本地管理 / individual) | sidecar 容器 `mac_address=`(worker 共享 netns,出口 MAC 由 sidecar 决定) |
| `TZ` 环境变量 | 候选池按 `seed[5] % 11` 取 | worker `environment` |
| `LANG` / `LC_ALL` | 候选池按 `seed[6] % 6` 取 | worker `environment` |
| `/etc/machine-id` | `sha256(account_name)` 取前 32 hex | worker entrypoint 启动早期写入(在 claude / tmux 起来之前) |

**适用范围(R3.scope)**: 派生函数 `derive_fingerprint(account_name)` 同时被 **task 模式** `Runner.start_run` 和 **login 模式** `LoginManager.start` 调用。任何接入 Anthropic 流量的 worker/sidecar 都使用账号派生指纹,确保 OAuth 时与后续 task run 看起来是同一台设备。

候选池(✅ 已确认,组合 50):
- **TZ(10)**: `Asia/Tokyo`, `Asia/Singapore`, `Asia/Seoul`, `Australia/Sydney`, `Europe/London`, `Europe/Berlin`, `Europe/Paris`, `America/Los_Angeles`, `America/New_York`, `America/Chicago`
- **LANG(5)**: `en_US.UTF-8`, `ja_JP.UTF-8`, `ko_KR.UTF-8`, `de_DE.UTF-8`, `fr_FR.UTF-8`
- 排除项:`Asia/Hong_Kong`、`Asia/Shanghai`、`zh_CN.UTF-8`(后两者:出口 IP 已偏中文区,locale/时区再叠中文会让"机器画像"和"网络出口"两个维度高度相关 → 反成更强关联信号)
- 镜像若未预装对应 locale,LANG 字面值仍作指纹生效(Claude Code 上报的是 env 字面值);design 中标注

### R4. 把 account_name 传到 worker
- 现在 worker 只有 `TASK_PROMPT / RUN_ID / TIMEOUT_SEC`,需要新增 `ACC_NAME`(也可作为后续审计用)

### R5. worker 容器内存上限差异化(Docker mem_limit)
- `derive_fingerprint` 再派生一个 `mem` 维度,池: `["4g", "8g", "16g", "32g"]`(`seed[8] % 4`)
- task 模式和 login 模式的 worker `containers.run` 加 `mem_limit=fp["mem"]` + `memswap_limit=fp["mem"]`(防 Node 走 swap 被 oom-killer 杀)
- 不动 sidecar(轻量进程,统一即可)
- 效果: Node `process.constrainedMemory()` / `os.totalmem()` 走 cgroup 读到不同值 → Claude Code 上报的内存上限按账号差异化
- 池规模避开 2g:防止编译/测试密集的题 OOM 污染评测;4g 起即可保证常见任务不触发 OOM

## Acceptance Criteria

- [ ] **A1**: 触发同一账号连续两次 run,两次容器内 `cat /etc/hostname && cat /etc/machine-id && echo $TZ && echo $LANG` 输出完全相同
- [ ] **A2**: 触发不同账号各一次 run,两个容器上述五项**均不相同**(MAC 通过 `ip link show eth0` 验证)
- [ ] **A3**: 故意在账号 profile 的 `telemetry/` 放一个测试 `1p_failed_events.test.json`,跑一次 task 后该文件**不出现**在 run 容器内 `/root/.claude/telemetry/`(目录可不存在,也可存在但不含该测试文件)
- [ ] **A4**: 源 profile `data/profiles/<acc>/telemetry/` 在 run 结束后**不被修改**(对照修改时间戳和内容 hash)
- [ ] **A5**: 对一个已存在账号触发 login(重新登录场景),login 流程内 OAuth 走完后调 commit,`data/profiles/<acc>/telemetry/` 和 `backups/` 被清空(目录可保留为空,也可不存在)
- [ ] **A6**: 当账号 X 存在 `status='running'` 的 run 时,对账号 X 触发 login_commit,返回 HTTP 409(或同类错误码)并附明确错误信息;待 run 结束后重试可成功
- [ ] **A7**: orchestrator / worker 启动均无 error 级日志;现有 `init-account.sh` 走 CLI 登录路径(未走 sidecar)依然能产出可用 profile
- [ ] **A8**: 现有 smoketest 账号无需手动迁移即可享受 R1/R3 效果(派生算法是 stateless 的)
- [ ] **A9**: 同一账号名分别走 login 模式和 task 模式,容器内 `hostname / machine-id / TZ / LANG / MAC` 五项**完全一致**(login 容器内通过 `docker exec` 取值对照)
- [ ] **A10**: 同账号两次 run,容器内 `node -e "console.log(process.constrainedMemory())"` 输出相同(且等于 `mem` 池字节值: 4g=4294967296 / 8g=8589934592 / 16g=17179869184 / 32g=34359738368)
- [ ] **A11**: `docker inspect <container> -f '{{.HostConfig.Memory}}'` 与 `derive_fingerprint(name)["mem"]` 一致;两个账号的 `constrainedMemory` **可能相同也可能不同**(池只有 4 项)
- ⚠ **注意**: `os.totalmem()` / `os.freemem()` 读 `/proc/meminfo` 是宿主物理内存,**不被 cgroup 影响** —— 这是 Node 已知行为。Claude Code telemetry 上报的字段是 `constrainedMemory`(参见 cc2api `src/service/telemetry.rs:322`),正好被 cgroup 约束,R5 因此有效

## 待用户确认 ❓

**Q1. TZ / LANG 候选池范围** ✅ 已定
- 中池: TZ 11 × LANG 6 = 66 组合(不含 Asia/Hong_Kong)

**Q2. `backups/` 是不是要一起清** ✅ 已定
- R1(task 运行时副本)+ R2(login 提交)均清 `telemetry/` 和 `backups/`

**Q3. login_commit 撞上该账号有 in-flight run 时的行为** ✅ 已定
- 查 `runs WHERE account_id=? AND status IN ('queued','running')`,有则返回 409,错误信息明示 in-flight 数量,不动 profile,不入库

(Q1/Q2/Q3 三问均已锁定)

**Q4. login 容器是否也用账号派生指纹** ✅ 已定
- 是。`LoginManager.start()` 调用同一个 `derive_fingerprint(name)`,login 与 task 模式身份完全一致,避免 OAuth 与后续 API 调用设备指纹错位
- 派生函数集中在一处实现,两个调用点复用

## Notes

- `init-account.sh` 是 legacy CLI 路径,**本任务不为它做差异化指纹**(它不经过 orchestrator,不知道账号名 hash 派生上下文)。其 README 已注明走代理建议改用 WebUI
- 本任务**不动 `vibebench-worker` Dockerfile**——所有差异化都在容器运行时注入,镜像保持单一
