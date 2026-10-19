# 实施与验收证据

## 当前结果

2026-10-16，S1–S8 已在独立 Docker 部署完成，最终演练包含 19 项通过断言。S9 当前生产发送器的非模型 HTTPS 检查通过；真实 Anthropic 模型 JSON/SSE 仍需可用账号，未用受限账号发模型探测。

| 场景 | 实际结果与证据 |
| --- | --- |
| S1 | 浏览器点击创建，SQLite 为 rewrite / 开启 / 4 / owner_only / 4 / 50，TTL 60 分钟；冲突创建 409 且不自动关联。独立关联保留刻意设置的 strip / 关闭 / 2 / mapped_request / 2 / 17，养号列不变；转发前恢复六项新建配置。 |
| S2 | 容器中运行官方原生 2.1.293 CLI，root 观察可核对进程路径/UID/RSS；点击指标更新后仅 canonical_process 与更新时间变化，两份凭据文件摘要不变。卡片分别显示 1.50G、实际 CLI RSS/时间以及另一账号的“未采集”。 |
| S3 | 缺失/伪造内部服务证明均 401；错误设备/来源/版本/样本的服务测试拒绝且旧数据不变。正式镜像的完整重授权/草稿浏览器回归通过，原 ID、两端凭据、六项配置、TTL 与原限流状态保留。 |
| S4 | 通用 JSON、正式 `/v1/messages` 非流式消息 JSON、完整消息 SSE 的状态/正文及字节哈希与隔离上游一致；发送器 request_id、环境/账号、代理来源 IP 和上游标记可关联。Billing 实际重写；5 个下游会话只使用 4 个池成员。 |
| S5 | HTTP CONNECT、SOCKS5h 均成功；错误 CA、错误主机名均 502，没有上游 HTTP 收包。正式管理及账号二进制均核对不含测试 CA 读取路径。 |
| S6 | 两账号请求只到各自代理；共享租约期间实际官方 CLI 进程在 API 前后均存活，API 成功返回。 |
| S7 | 有限慢流完整结束；取消长流后网关与发送器 active 均为零，取消传播到上游且 completed=false，唯一上游收包无重放；在途指标更新被拒绝且库中进程值不变。 |
| S8 | 真实内部发送路径被 TCP reset 时 API 明确 502；代理 407/端口不可达、错误账号/代次/秘密/目标均失败。网关网络命名空间阻断公网，全部场景的公网直连尝试计数为零。 |
| S9 | 生产 ci-38737388342-1 的原发送器，通过账号代理请求固定 `https://api.anthropic.com/api/hello`，GET、无上游 Authorization，返回 200 / 20 字节。匹配发送器 request_id `d6beddb9-84eb-4fc7-87ae-5cefb7deb776`；环境恢复 stopped，4 份身份/凭据文件与网关 12 项凭据/设备/代理/策略摘要不变。代次按正常唤醒递增，不回退。 |

## 命令与退出结果

全部命令已取得退出码 0，测试计数按独立执行统计，不按引用次数重复相加。

- `/tmp/vibebench-passive-quota-venv/bin/python -m unittest discover -s orchestrator -p 'test_*.py'`：266 项通过，日志 `/tmp/v3-process-sync-python-final.log`。
- `cd cc2api && cargo test`：645 项通过，1 项 PostgreSQL 独立 DSN 测试按原约定忽略；本轮未新增 schema/migration，条件 UPDATE 的 PostgreSQL 语法已核对。日志 `/tmp/v3-process-sync-rust-tests-final.log`。
- `cd cc2api && cargo fmt --check`；`node --check webui/app.js`；Python 语法检查与两仓 `git diff --check` 通过。
- `cd cc2api/web && npm run build`：Vue 类型检查及 Vite 构建通过，日志 `/tmp/v3-process-sync-web-build-2.log`。
- canonical `manage.py build`：正式 `process-sync-20261016-c`、测试 `verify-process-20261016-c` 联合镜像构建通过。
- `verify_forwarding.py --manifest /tmp/v3-process-verification-c-manifest.json --output /tmp/v3-process-forwarding-final2-results --cli-binary <本机已安装官方2.1.293二进制>`：19 项通过，日志 `/tmp/v3-process-forwarding-final2.log`，结果、代理/上游、发送器、进程记录及截图在结果目录。
- `verify_stack.py --manifest /tmp/v3-process-sync-c-manifest.json --browser --reauth`：经临时 wrapper 为本次部署选择未占用 IPAM 网段，其余正式断言不变；完整页面/WS/tmux/身份/凭据/草稿/旧哨兵/停机备份回归通过。日志 `/tmp/v3-process-sync-reauth-final.log`。

## 构建差异与恢复

- 正式与测试 C 批次冻结的产品源码哈希均为 `c77c09a6ea5fa5b308211673ee42e7935d95116d04d430dc791c6a0eb3b64fb7`。当前代码仅有一处 Rustfmt 断行差异；在临时副本还原该断行后，内容哈希精确匹配。该核对未修改工作区。
- 测试额外启用 `v3-verification`，只读取 root 私有临时 DER CA；origin 仍固定为 Anthropic，证书签名和主机名校验均保留。正常 control/account 构建不含额外根路径，不发布测试镜像。
- 所有测试账号/库/容器/网络均为本次随机部署专属；finally 按本次标签清理并回查无残留。重授权演练另核对旧哨兵容器及数据库内容不变。
- 生产只生成一条新的非模型 API 观察；没有上游账号凭据、真实对话、OAuth 刷新或 usage 查询。已恢复停止状态，无需用户清理测试数据。
- 原有 Flower 升级、旧任务目录及其他 dirty 基线继续保留，不纳入本轮业务变更。

## 验证过程中纠正的假设

- Docker 默认无 SYS_PTRACE，root 不能直接读取 UID 1000 的 `/proc/<pid>/exe`；只改 fsuid 仍因 fsgid 不匹配被拒绝。最终只在 readlink 期间切换 fsuid/fsgid，恢复后核对 root 缓存；实际 Docker 与真实 UID 回归证明可用，不增加容器权限。
- session 池前四个属主保留原会话 ID；第五个才映射到已有成员，不能误把“首个会话 ID 不变”判为池未启用。
- Billing 夹具必须使用带三位后缀的真实格式；不完整假头无法证明正式改写。请求/响应原文不保存，保留合成标记和哈希。
- urllib3 分块读取器被回收会关闭连接；取消测试必须保留读取器并先确认 active>0，再检查在途拒绝与取消收口。
- 页面 readyState=complete 早于首次账号查询结束；草稿演练等待实际事件处理器安装，避免额外刷新与初始快照查询并发。早期等待失败已保留日志，未改产品的草稿恢复逻辑。

## 后续边界

- 尚未提交、推送或替换生产版本。部署采用正式 CI 联合清单，遵循原服务器密码兼容覆盖与资源预检，空闲重建保留 HOME。
- 新版上线后给原绑定账号补齐进程指标并核对页面；仅更新进程字段，已有六项策略不追溯覆盖。
- 真实 Anthropic JSON/SSE 推理需可用账号后单独验收；隔离 200 与生产非模型 200 均不能代替该结论。
