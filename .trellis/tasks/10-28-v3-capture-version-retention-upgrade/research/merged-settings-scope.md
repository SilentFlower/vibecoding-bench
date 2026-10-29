# 运行与双迭代抓包配置合并核对

核对日期：2026-10-29。用户要求沿用原运行抓包任务，合并项目迭代、养号迭代配置按钮和账号 Claude Code 版本继承。当前仅改任务规划材料。

## 已核实源码

| 位置 | 当前事实 | 规划影响 |
| --- | --- | --- |
| `orchestrator/main.py:1953` | `effective_claude_code_version()` 只解析全局页面覆盖与环境兜底 | 账号版本需要增加统一解析入口，不能仅改页面显示 |
| `orchestrator/main.py:7874` | `_project_execution_settings()` 无账号参数，版本直接取全局 | 两个迭代空间的新 work 设置必须能取得已核账号 |
| `orchestrator/projects.py:1905` | 新 work 调用 `terminal.settings()` 并写入 `settings_json` | 复用现有冻结机制；不能在每次恢复时重读账号默认覆盖原会话 |
| `orchestrator/projects_runtime.py:94` | 离线工程环境 PATH 使用 `work.settings_json` 的版本 | 页面、存储、CLI 安装和实际 PATH 必须一致 |
| `orchestrator/pi_terminal.py:75` | 两种 Pi 终端都以 `shared_cli=True` 认领，并检查逐作业监督支持 | 迭代抓包不能只把网络模式字符串替换成 capture，必须解决共享认领和互斥边界 |
| `orchestrator/pi_terminal.py:103`、`:111` | 作业记录及共享网络上下文固定为 passthrough | 需要让已冻结抓包配置贯穿实际执行，不能只增加开关 |
| `orchestrator/account_runtime.py:1338`、`:1410` | 现有普通抓包使用非共享 CLI 认领，并选择 capture 模式 | 复用现有隔离规则，不以切换共享监听中断兄弟执行 |
| `orchestrator/projects_api.py:13` | `ProjectsAgentIn` 只有项目池、业务指南和预算，禁止额外字段 | 需在 DTO、服务、持久化和公开视图同时接入配置 |
| `webui/index.html:70`、`webui/projects.js:297` | 两种迭代复用同一页面组件，现有配置是页面内折叠区域 | 新按钮应复用组件并核对账号、空间和异步回执归属 |
| `orchestrator/main.py:8747` | 当前账号创建 DTO 没有 Claude Code 版本字段 | 账号持久配置及读写 API 需要专门设计，不能把全局设置改成账号值 |
| `orchestrator/main.py:11024`、`:11398` | 抓包创建 DTO 无版本字段，创建逻辑使用全局版本 | 原单次版本子项继续保留，新增账号默认回退层 |
| `orchestrator/main.py:11853` | 现有抓包详情入口针对 capture run | 两个迭代空间还需有具备身份归属的查看入口；不能拿 work ID 冒充 run ID |

## 合并边界

- 主任务沿用 `10-28-v3-capture-version-retention-upgrade`，不创建重复父任务。
- 两个已有子项继续保留身份和历史，分别承接版本配置，以及三入口抓包和数据保留；需求的唯一合并入口为父 PRD。
- 新增账号继承后，原“单次留空只读全局”和“所有其他入口完全不变”的旧规划需要更新，不能让三份计划互相矛盾。
- 原先明确不做“可恢复暂停”的决定针对新增抓包控制，不删除项目/养号已有的业务暂停与原会话恢复能力。
- 用户已确认抓包默认关闭，手动开启并保存后仅影响后续新执行，缺少该字段的旧配置按关闭处理。已核现有 CLI 专用独占租约及逐作业监督的接入边界，详见 `execution-boundaries.md`。

## 下一步

用户已选择“单次显式指定 > 账号配置 > 全局”“抓包默认关闭”和“全部 CLI 入口统一覆盖”；已有会话及草稿仍用原版本。产品问题已收敛，技术核查已写入执行边界记录，统一刷新 Brief 后进入实施评审。
