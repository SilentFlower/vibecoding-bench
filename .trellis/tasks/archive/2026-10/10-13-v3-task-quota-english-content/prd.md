# v3 任务额度门禁与全英文内容改造

## Goal

把现有账号级 5h/7d 已用百分比阈值扩展到普通任务调度，并让 v3 新建任务收到的题库内容、默认 prompt 和运行中自动注入提示全部使用安全、自然的英文。

## Background

- 当前 `warmup_quota_5h_limit_percent` / `warmup_quota_7d_limit_percent` 只约束 `run_kind='warmup'`；普通单任务和批次 run 不检查这两个阈值。
- 共享额度事实已由正式请求和用户显式额度查询写入 `account_quota_states`，`QuotaGuard` 已能让共同额度耗尽的 run 进入 `quota_wait` 并恢复。
- `topics.md` 当前有 600 题、21 个中文分类；现有同步脚本按 `topic.no` 更新 SQLite 并先备份数据库。
- topic 的 `natural` / `canonical` 默认 prompt 包装和 worker 的续跑、超时收尾、认证恢复、API 卡顿恢复提示仍包含中文。
- 当前生产 v3 没有为运行时提示设置自定义环境变量覆盖；仓库默认文本就是实际来源。

## Requirements

### R1 — 普通任务使用同一账号阈值

- 现有两个 1～100 已用百分比阈值升级为账号级 bench 策略，同时作用于养号和普通任务；数据库字段名为兼容旧数据继续保留。
- 普通任务包括单任务及批次产生的 `run_kind='normal'`。抓包、继续对话和 cc2api API 转发不纳入本策略，继续沿用各自已有门禁。
- 任一启用窗口已有可信用量且 `utilization >= threshold` 时，新普通 run 可以创建记录，但在创建 worker 前进入 `quota_wait`；不得启动账号容器内 CLI 或消耗并发槽。
- 额度未知或窗口已过期时，普通 run 进入 `quota_wait`，提示用户先执行现有额度查询；普通任务不能借用养号的“一次正式请求”机会探测额度。
- 运行中的普通 run 不因阈值中途命中而中止；本次运行正常收尾，后续尚未启动的 run 再等待。
- 用户显式查询、被动观察或关闭/提高阈值后，符合条件的原 run 按现有 FIFO、批次和身份保护恢复；不得创建新 task、重写 prompt、重置 workspace 或改变账号身份。
- 养号原有单次正式请求、Recorder 收尾和暂停语义继续保留。

### R2 — 页面表达真实作用范围

- 账号配置中的额度区域改为“普通任务与养号额度控制”，明确阈值按已用百分比判断。
- 页面说明命中后的行为：运行中请求收尾，尚未启动的普通任务和养号等待；API 转发不受该阈值控制。
- 账号列表摘要同时展示普通任务和养号的门禁状态，不再把阈值描述为养号专用。
- 现有配置 API 和旧客户端保持兼容；省略、`null`、范围校验及旧数据默认关闭行为不变。

### R3 — 600 题安全英文迁移

- `topics.md` 的文件说明、21 个分类名称、600 个标题和 600 个描述全部改为自然英文；题号集合保持精确的 1～600，不新增、删除或重排 ID。
- 题目继续保持可演示、范围可控、有真实使用价值、适合 0.5～3 天完成 MVP 的基线。
- 将容易被理解为逆向、模型/风格蒸馏、账号自动化或抢占资源的题目替换为正常场景题。首批明确替换：#39 写作风格迁移、#73 多站点自动签到、#76 抢课/抢号页面监控；实现时再用固定高风险词表扫描全部 600 题并人工复核命中项。
- 安全扫描至少拒绝 reverse engineering、decompilation、credential harvesting、session hijacking、fingerprint spoofing、account farming、automated registration、model extraction、knowledge distillation、style imitation、CAPTCHA bypass、auto-booking 和 auto-purchasing 等目标。
- 网页归档、RSS、公开更新日志、隐私自检、测试故障注入等正常开发场景可以保留，但描述必须限定为用户授权、本地样例或公开数据，不能暗示绕过访问控制。

### R4 — 新 run 的默认 prompt 全英文

- `natural` 模式的分类映射、开场、需求、交付、报告和布局片段全部使用英文；21 个新英文分类必须全部映射到已定义风格。
- `canonical` 模式的字段标签和 MVP 交付说明全部使用英文；同一 topic 仍保持稳定输出。
- 未分类回退和 prompt 指纹占位文本使用英文，不在英文 topic 外重新引入中文包装。
- 自定义 `prompt_override` 原样保留，历史 task/run 已持久化 prompt 不改写。

### R5 — run 内自动注入提示全英文

- worker 默认的 resume prompt、timeout wrap-up prompt、OAuth refresh retry prompt 和 Claude API stall recovery prompt 全部改为英文。
- 自动提示保持现有触发时机、重试次数、优先级、收尾和退出码，不改变任务生命周期。
- WebUI 状态、错误说明、运维日志和后端中文注释不属于 prompt 内容，可继续使用中文。
- 仓库和目标 v3 部署不得存在覆盖上述默认提示的中文环境变量；如果未来显式配置覆盖值，其语言由操作者负责。

### R6 — 同步、兼容和回滚

- topic 解析器同时接受旧中文分类标题格式和新英文标题格式，避免历史工具或回滚材料立即失效；新 `topics.md` 只使用英文格式。
- 同步前必须校验 600 条、1～600 完整集合、21 个分类、必填字段、字段无 CJK、高风险词表无命中。
- 对现有 v3 SQLite 先执行 dry-run，再用 SQLite backup API 或现有受控备份生成新备份，最后按 `topic.no` 原位更新；保留 topics.id、task/run 历史和已持久化 prompt。
- 不同步旧版 bench 数据库，不停止旧版服务，不修改 cc2api 上游发送、额度统计或凭据。
- 回滚代码和双镜像时，题库数据库使用本次同步前备份恢复；历史 task/run 无需转换。

## Acceptance Criteria

- [ ] A1（R1、R2）：5h 或 7d 已用量等于阈值时，单任务与批次 run 在 worker 创建前进入 `quota_wait`；运行中 run 完成，cc2api API、抓包和继续对话行为不变。
- [ ] A2（R1）：额度未知的普通 run 不发探测请求；显式额度查询更新为低于阈值后恢复原 run，高于阈值则继续等待；关闭阈值后同一 run 恢复且 prompt/workspace/身份不变。
- [ ] A3（R1）：养号的一次请求、Recorder 收尾、重启恢复、多窗口 reset、永久认证错误及停止/删除保护全部回归通过。
- [ ] A4（R2）：真实浏览器中保存、重读、独立关闭两窗口，账号摘要和 1280/390 明暗布局准确说明“普通任务与养号”，非法值不写数据库。
- [ ] A5（R3、R6）：解析结果恰好 600 题、编号 1～600、21 个英文分类；标题/描述/分类无 CJK，固定高风险扫描为零，#39/#73/#76 已替换为无害项目。
- [ ] A6（R4、R5）：自然/规范 prompt 与四类 worker 自动注入提示均为英文；自动测试覆盖触发文本，仓库和目标 v3 环境无中文 prompt 覆盖。
- [ ] A7（R3、R4、R6）：临时旧库 dry-run/apply 后保留 topic id、task/run prompt 和历史数量；只更新 600 个 topic 字段，并可用备份恢复。
- [ ] A8（全量）：同批 control/account 镜像通过单测、隔离 Docker、真实 Chrome、额度恢复和题库同步演练；生产 v3 同步后展示 600 个英文题目，旧版服务容器身份和启动时间不变。

## Out of Scope

- 不对既有历史 task/run prompt 做翻译或回填。
- 不把账号阈值扩展到 cc2api API 请求、抓包或继续对话。
- 不自动修改用户未来显式提供的自定义 prompt 或环境变量覆盖。
- 不重写 WebUI 全站文案、运行状态、错误消息或代码注释为英文。
- 不修改额度遥测来源、主动新增 usage 轮询或改变 Claude 官方额度算法。
