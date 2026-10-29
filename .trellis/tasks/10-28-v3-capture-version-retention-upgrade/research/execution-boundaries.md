# 全部 CLI 入口及捕获执行边界

核查日期：2026-10-29。三个产品选择已收敛：单次指定 > 账号配置 > 全局；迭代抓包默认关闭；账号版本覆盖全部 CLI 入口。以下为源码依据及拟实施方案，未修改产品或启动真实账号。

## 版本入口分类

| 入口与位置 | 当前行为 | 接入规则 |
| --- | --- | --- |
| `main.py:1254` `_claude_exec_env` | 缺省读全局，extra 可覆盖；带抓包 CA 环境 | 调用方传已解析/冻结值，不能因二次 helper 默认值换版本 |
| `main.py:1953`、`:1962`、`:1975` | 全局解析、run 解析及旧空快照回填 | 全局函数保留职责；新账号解析层与旧快照兼容分开 |
| `main.py:3953`、`:4374`、`:12074` | 普通启动/续聊读取 run/task 快照 | 继续优先原快照；只对旧空值兼容回填 |
| `main.py:6605`、`:7673`、`:11533` | 批次、旧养号、普通 run 创建时读全局 | 已有账号参数或已取账号行，在创建身份时解析账号默认 |
| `main.py:11398` | 运行抓包直接读全局 | 增加单次字段，取到账号后解析并冻结 |
| `main.py:7874`、`projects.py:1905` | 新 Pi work 的 settings 回调无账号参数 | 创建 work 时传已核账号，保留 settings_json 的冻结语义 |
| `project_iteration.py:778`、`project_plans.py:440`、`project_scenarios.py:1140` | 兼容项目及场景计划仍有无参 settings；已有 execution_json 被复用 | 同步账号上下文，保留已冻结候选/评审版本，不能遗漏隐藏兼容入口 |
| `project_review_runtime.py:602`、`:663` | CLI 评审沿 worker_env 的版本准备及启动 | 沿原冻结值，不另取账号或全局覆盖同包评审 |
| `main.py:5048`、`:5216`、`:5241`、`:9981` | LoginSession 默认全局；start 有原版本参数；草稿恢复读 record.version | 新登录/重授权解析账号值，已有 session/草稿保留原值，无账号新草稿用全局 |
| `main.py:4478`、`:4712`、`:4741`、`:4987` | 既有 CLI 查询/维护准备及环境使用全局 | 沿原门禁、调用频率及凭据所有权，只替换实际版本选择，不新增探测 |
| `main.py:9093`、`:9167`、`:12525` | 身份/进程观察与导入带版本参数 | 区分目标默认与实际观察；不把配置版本伪装成已执行版本，不绕过身份来源校验 |
| `main.py:12476`；`account_runtime.py:913` | transport 接收版本兼容参数，但只 ensure API 环境 | 维持不安装/唤醒 CLI 的行为，不修改 API 版本画像 |

完整 main 与兼容 settings 调用索引见 `cli-version-callers.json`；实施时按角色逐项核对，不做全局文本替换。

## CLI 独占与逐作业监督是两个条件

- `account_runtime.py:1045` 的 claim 已支持 `shared_cli=False, exclusive=False`，对应 `prepare-cli`；`cc2api/src/service/runtime_lease.rs:254` 明确该租约独占 CLI、允许独立 API。
- `account_runtime.py:1086` 在认领前检查兄弟作业；捕获应等待，不停止兄弟。`exclusive=True` 是维护排空 API 的语义，不能用于普通捕获。
- `pi_terminal.py:75`、`:79` 当前既要求共享租约，也用该标志代替逐作业监督能力；`:103`、`:111` 固定透传。仅替换 capture 字符串或直接删除检查均不完整。
- `_save_execution`（`account_runtime.py:1164`）已保存 execution_role、process、settings_override 和网络模式。既有 project-review 在非普通共享路径也使用内核证明，说明监督能力不能等同于共享租约。
- 拟为本账号捕获增加明确监督角色，保持真实非共享租约；核对 control_execution（`:1739`）、wait_worker（`:1702`）、cleanup（`:1812`）和单执行恢复（`:2829`），不能把捕获伪装成私有评审容器。
- 单执行恢复当前未拷回 settings_override/network_inspection_mode；捕获接入需补齐其恢复信息，避免重启后用错监督或网络收尾路径。
- 停止先核 source/PID/started 并收口本作业，再收尾唯一 Recorder、恢复 passthrough、释放租约。共享透传作业仍复用兄弟监听，捕获关闭不降低其并发能力。

## 数据与 CA

- 普通完整抓包已在 `account_runtime.py:1410`～`:1438` 配置捕获模式、分代路径与 ACK；两个迭代入口复用相同约定和已核 CA 环境映射。
- 抓包默认关闭；保存只改变后续认领，不热切当前网络。已有 run/work 的版本与会话仍保持，捕获开关按每次新执行记录。
- `projects_api.py:138` 已有 work 归属读取入口，但没有捕获详情。新入口复用两个服务前缀和服务端 work 归属，不能复用 capture run ID 查询冒充 work 数据。
- 原控制台已区分 Pi 与 Claude 交流，新增 HTTP 捕获只取 Claude Code CLI 经本账号网络角色的流量，独立 API 的 sender 路径保持。
- Recorder 的已有约 2 秒优雅退出窗口可能转强制结束；必须验证文件仍在、部分状态及未完成索引，不能仅凭 stop API 成功判断产物完整。

## 身份与兼容

- `account_runtime.py:41` 直接配置映射仅登记 2.1.293；`:2682` 可使用其他版本已有的真实请求观察。仅选择一个可安装版本，不代表其身份来源或网关访问范围自动获得证明。
- 登录/重授权沿 session.version、草稿 version 和既有提交/迟到回包保护；不为账号版本更改重建身份、轮换凭据或修改网关画像。
- 对任务所用的精确官方 CLI 版本补可复核的本地隔离证据；未知来源明确失败，不猜字段，不静默退回全局，也不以真实账号/模型请求作为探针。
- 旧空快照优先可核对的执行版本，无证明时按兼容规则解析并回填一次，之后保持；来源在历史详情中可辨认。

## 规划结论

产品问题均已解决；后续实现细节沿上述既有能力收敛。先做统一账号配置及版本冻结链路，再接入捕获监督/恢复、查看及数据保留，按主 PRD AC1～AC10 验收。
