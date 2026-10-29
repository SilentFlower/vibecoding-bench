# 观察效率设计

## 实现边界

Python `ProjectsService._observe` 拥有等待、取消、代次及持久化；`PiTerminal.observe` 继续提供完整原始事实。Node `images/pi-agent/host.mjs` 仅拥有模型工具回执投影。复用现有线程、JSONL 管道、SDK 上下文及测试替身，不引入额外后台控制者。

## 等待合同

`claude_observe` 的 wait_sec 保持严格整数 0..30，默认改为 30；首次/输入后观察立即读现场，显式 0 保持即时语义。后续非零等待不以 screen 文本变化立即结束，在新增原生文本、交互提示、稳定的新有效画面、执行退出、quota_paused、终端可读性变化或期限达到时返回。每轮在原采样周期检查 _current 与取消；只在有可发布最终观察时写 observation_json/observation_id、完整 observation 事件和原生用量。

读取游标与最近画面在单次等待内前进，新的文本必须返回且不会被游标越过丢弃；长等待不持数据库写锁。仅对固定 CLI 已核实的进度/计时显示做噪声归一化，前台空闲或出现编号选择界面时，新有效画面稳定约一秒即返回；未知内容保守交给 Pi，不让纯画面菜单等待三十秒。三十秒只作无有效变化兜底，不依赖某句回复或通用正则去猜业务完成。

作业级 settings 保留用户已有钩子，并为权限请求、明确提问/方案确认工具、回合结束等安装本地通知。通知只写有界唤醒标记，含会话、来源与事件标识；不记录完整参数/凭据，不给 CLI 返回授权决定。读取时核对本次执行归属、普通文件和字节上限。原生 JSONL 的 AskUserQuestion/ExitPlanMode 工具事件也能唤醒，不依赖通知的延迟。

## 模型视图合同

工具新增可选 `full_screen: boolean`，Python 校验类型，Node 根据原调用参数投影。Python→Node 原始结果和数据库保持完整。模型回执保留 observation_id、events、cursor、running、terminal_ready、退出/额度/错误等实际字段。

- full：包含完整 screen，并设 screen_mode=full。
- unchanged：省去重复整屏，设 screen_mode=unchanged 与 screen_base_observation_id。
- patch：省去重复整屏，设 screen_mode=patch、screen_base_observation_id、screen_patch={start_line,delete_count,lines}。由上次完整画面按原换行拆分、替换对应行后必须精确恢复当前屏幕；差异不小于全屏时退回 full。

基线属于本 Pi 会话的已交付观察。第一次、进程重启、fresh 与摘要成功后清空；full_screen=true 强制 full。错误/拒绝/取消不推进基线，摘要不能留下无模型可见基线的差异。更新 AGENT_GUIDE 与工具说明，使 Pi 知道默认等待、增量及完整读取方法。

## 关联文件

主要为 `orchestrator/projects.py`、`orchestrator/pi_terminal.py`、`images/account/projects_cli.py`、`images/pi-agent/host.mjs`、必要的本地通知/画面策略辅助与现有测试；确有必要时新增一个小型投影模块，并同步所有构建 COPY/白名单。`orchestrator/projects_api.py` 与页面 snapshot/events DTO 不改变。

## 风险与验证

重点是固定版本钩子覆盖、无钩子菜单快速唤醒、显示噪声误唤醒、停机/代次竞争、摘要后的基线和多工具回执顺序。分别使用可控时钟/取消替身、真实 SQLite 和 mock SDK 上游证明，不靠真实付费采样。回放来源的完整时间/摘要记录存于父任务 research/observation-trace.json，不含终端正文。

## 实施收敛

忙碌期间的流式正文也会造成频繁变屏，因而只在交互信号、正式原生文本、状态变化或无有效变化兜底时返回；没有忙碌指示的新稳定画面，以及与后台进度共存的编号选择界面，使用约一秒去抖快速返回。提示只包含事件、来源、会话和标识，不保存完整钩子输入。恢复执行时清除旧 observation_id，重新取得现场后才允许输入。
