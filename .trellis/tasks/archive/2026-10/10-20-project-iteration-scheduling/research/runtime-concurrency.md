# 同账号并行与会话内逐步验收的可行性

## 当前限制

- `orchestrator/main.py:82` 在 v3 下强制账号信号量为 1；Tasks 的表单仍允许 2。
- `AccountRuntime.claim()` 的 `jobs` 以环境 ID 保存单作业；`_save_execution()` 写单个 `runtime/execution.json`；网关 `RuntimeGate.state` 仅容纳一个租约。三处均需配套升级。
- `AccountRuntime.cleanup()` 在 isolation version 2 下调用 `v3-cli-control stop`，后者按 UID 1000 清理整个 CLI 容器；直接放大信号量会误停同账号另一作业。
- `AccountRuntime._install_cli_quota()` 把当前作业采集配置写进共享 HOME 的 `settings.json.statusLine`，释放时恢复旧值；并行执行会交叉覆盖。共享网络 context 的切换和清空同样基于单作业假设。
- CLI 角色由 `account_isolation.create_environment()` 以 UID 1000、cap_drop ALL、只读根和 no-new-privileges 启动；不能为本功能改成 root、增加容器权限或暴露发送器秘密。
- `images/worker/entrypoint.sh` 已使用原生主会话 JSONL 判断完整回复，并能往同一 tmux 中发送后续输入。`task_followups.read_dialogue()` 提供父链、输入正文、字节边界与工具／合成错误排除，可复用解析，不能把旧定时补充的“到点即投递”用作业务验收。

## 计划采用的机制

1. 账号维护全量执行登记，普通 Tasks 与项目计划共用有界 CLI 槽位；维护仍排他。每个执行按 source、generation、token 独立登记、续期、对账和释放。
2. 增加每作业监督进程，用 Linux child subreaper 接管该作业脱离进程组后的后台子进程。监督进程启动握手独立于 CLI 输出，子进程不继承握手通道；控制端持久核对容器归属、PID、启动时刻和执行代次，不能信任项目内自写的 PID 或“已完成”文件。
3. 到逐步验收边界时，由独立管理命令暂停当前作业的完整进程子树，核对稳定的内核暂停状态后再封存候选。验收和检查点持久化完成后才恢复同一 CLI 并投递下一步。暂停或定向清理不扫描并终止整个账号 UID。
4. 普通 passthrough 作业共用账号既有 relay，不在每个作业收口时清空兄弟作业的网络上下文；需要切换 capture 模式的执行保持 CLI 排他。登录／重授权／环境维护继续使用原排他保护。
5. 采集配置通过每 CLI 会话的 settings 覆盖传入；共享 HOME 中的用户配置不再为不同作业来回改写 statusLine。原用户状态栏命令继续收到相同 stdin。

## 已执行的离线实验

- 目录：`/tmp/project-scheduling-review-20261020-lahw8b6g`。
- 脚本：`process-review.py`；结果：`process-review.log`。
- 镜像：本机既有 `vibebench-v3-account:v3-project-iteration-20261020-d`，没有构建或发布新镜像。
- Docker：network none、只读根、UID 1000、cap_drop ALL、no-new-privileges、0.5 CPU、128 MiB、PID 64；仅挂载实验脚本与临时 tmpfs，没有账号 HOME、凭据、代理或 Docker socket。
- 同时运行 A、B 两个监督作业，每个作业包含普通持续写入进程与双重 fork／setsid 后台进程。
- 结果退出码 0：有效 capabilities 为全零；A 的后台进程被本作业监督器收养；冻结 A 后两个 A 写入源均稳定而 B 继续写；恢复后 A 继续写；定向停止 A 后 B 的进程和两个写入源均正常。
- 实验容器使用 `--rm`。这只是进程隔离机制的可行性证据，没有运行真实模型，也没有证明最终 driver、同会话多步或生产链路已实现。

## CLI 参数依据与限制

- 本机只读检查 `claude --version` 得到 `2.1.296`；`claude --help` 明确列出 `--settings <file-or-json>`、`--session-id <uuid>` 与 `--resume [value]`。命令只查看帮助，没有启动会话或发起模型请求。
- 官方 [CLI reference](https://code.claude.com/docs/en/cli-reference) 说明 `--settings` 的键仅覆盖该会话同名设置，未指定的设置继续继承；恢复可指定明确会话 ID。
- Linux [PR_SET_CHILD_SUBREAPER](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html) 说明孤儿后代会重新归属最近的存活 subreaper；实际无权限容器实验也验证了这点。
- 产品默认版本在当前源码中为 `2.1.280`，与本机帮助版本不同。实现验收必须使用本轮冻结的实际 CLI 版本检查支持和生效结果；不能把本机帮助冒充生产版本验证，也不为本功能自动更新用户固定的 CLI 版本。

## 必须在实现后验证

- 两个真实 driver 的并行区间、同一 native session 两步、每步冻结／快照／验收／再投递的完整交接。
- 第一步通过、第二步部分改动后超时，重启后保留原计划、原会话与未完成改动；接受检查点后但回复前崩溃也不能重复接受。
- UID 1000 的脱离进程组子进程、PID 复用、监督器提前退出和暂停证明丢失均不能误杀兄弟或冒充可验收。
- 每执行采集、账户级被动额度更新和 Run／步骤 token 边界独立，不能因一个 Run 包含多个步骤而重复汇总整个 Run。
