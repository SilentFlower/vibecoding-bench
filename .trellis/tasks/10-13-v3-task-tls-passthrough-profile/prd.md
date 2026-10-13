# v3 任务 TLS 透传与账号画像校正

## Goal

让 v3 的普通任务、正常养号和登录链路保留账号代理但不解密 HTTPS，使 Claude Code 自己建立 TLS；同时把新账号的固定环境画像改为地区一致、首次随机且永久持久化，并修复未绑定 cc2api 时无法单独保存普通任务额度阈值的问题。

## Background

- 当前固定账号容器把全部 CLI TCP 流量送进本地 mitmproxy，再由 proxychains 连接账号的 HTTP/SOCKS 代理；普通任务因此不是原生 TLS。
- 现有 Recorder 同时承担显式抓包、额度响应观察和普通任务网络转发。普通任务不需要 HTTP 明文证据，但依赖同一监听端口，必须先拆分“传输”与“检查”职责。
- v3 环境沿用 `derive_fingerprint(account_name)`：hostname 为 `vb-*`，machine-id/MAC/语言由账号名哈希派生。生产 `10-13` 使用 `us-8` HTTP 代理和 `America/Los_Angeles`，但 locale 是 `ja_JP.UTF-8`；该账号尚无 task/run、无设备观测、容器已停止，适合一次性校正。
- 普通任务与养号已经共享 5h/7d 阈值，但养号表单和 `WarmupConfigIn` 仍强制要求 `cc2api_account_id`。生产 `10-13` 尚未绑定，导致只能设置阈值也无法保存。

## Requirements

### R1 — 普通 CLI 使用原生 TLS 透传

- v3 普通任务、已有可信额度下的正常养号、OAuth 登录/重授权和凭据刷新必须使用 `passthrough` 网络模式：保留账号代理与强制出口，只转发原始 TCP 字节，不启动 mitmproxy、不安装或注入 MITM CA。
- passthrough 必须同时支持现有 `http`、`socks5` 和 `socks5h` 上游代理，不能因协议不同回退直连；代理配置缺失、认证失败、中继退出或模式确认失败一律失败关闭。
- Claude Code/Node 生成的 TLS ClientHello、HTTP/2 和应用请求字节必须原样穿过本地中继；中继不得增加 HTTP header、修改正文或生成 TLS。
- cc2api 的账号发送器继续使用现有独立 HTTPS 实现和代理配置，本任务不修改其请求重写、遥测或上游协议逻辑。

### R2 — 检查模式按场景显式切换

- 显式完整抓包 run 使用 `capture` 模式，沿用 mitmproxy、持久 CA、Recorder、完整 flow 与现有权限限制。
- 手动额度查询以及养号在未知/到期窗口领取的单次正式样本使用 `quota` 模式，允许 Recorder 读取必要响应并更新额度；样本收口后下一次正常运行恢复 passthrough。
- 网络模式必须写入当前执行的私有 context 与确认回执，调度器核对 `mode + source` 后才能启动 CLI。旧进程无法收口、监听端口未就绪或回执不匹配时不得启动。
- passthrough 不再提供普通任务的被动 HTTP quota header。阈值使用最近一次手动查询、quota/capture 样本或 cc2api 观察；数据未知/到期时继续按现有规则等待手动查询，不自动增加 usage 请求。
- 模式切换只能在 CLI 空闲或已取得独占维护门禁时进行；不得中断 cc2api 已接受的独立 API 流。

### R3 — v3 新账号画像首次随机并永久固定

- v3 新环境使用独立的 profile v2 生成器；不得复用旧版按账号名哈希的 `derive_fingerprint()`。
- hostname 使用首次生成并持久化的 12 位小写十六进制 Docker 风格名称；machine-id 使用独立随机 32 位小写十六进制；MAC 使用独立随机的本地管理单播地址。三者不得从账号名、账号 ID、环境 ID 或彼此派生。
- 时区以账号显式配置为事实来源；locale 按时区地区成组选择并持久化。美国时区使用 `en_US.UTF-8`，东京使用 `ja_JP.UTF-8`，首尔使用 `ko_KR.UTF-8`，柏林/巴黎使用对应德语/法语，伦敦使用 `en_GB.UTF-8`，其它地区使用可用的英语回退。
- RAM/swap 继续使用部署预算并在环境首次创建时固化，不伪造宿主硬件。容器重建、服务重启、任务、养号、抓包和 cc2api 调用不得改变画像。
- 正常任务工作目录不暴露 `vibebench`、`bench-*` 容器名或原始 run ID；编排状态、transcript/status 等控制文件移出项目工作树。历史证据入口继续可读。

### R4 — 现有环境只允许显式安全校正

- 增加显式 `reprofile` 维护操作；不在启动、部署或普通重建时自动旋转任何环境画像。
- 只有环境空闲、账号未绑定 cc2api、没有 task/run 历史、没有已观测 device identity、没有登录提交/对账和活动容器时才允许校正；否则返回可解释冲突。
- 校正保留账号记录、OAuth HOME 和代理配置，删除旧网络/CA 运行产物，写入新的 profile v2，并进入 `profile_reauth` 门禁。门禁期间普通任务、养号、抓包和 API 发送均拒绝，只有该账号显式重授权可进入。
- 重授权成功后清除门禁并永久冻结新画像；取消或失败继续保持门禁，不能携带一半新旧画像运行。
- 生产 `10-13` 在停机备份后执行一次 `reprofile`，由用户完成真实 CLI 重授权；完成前保持不可运行，不猜测或复用旧设备观测。

### R5 — 未绑定账号可独立保存任务阈值

- `cc2api_account_id` 在养号配置请求中改为可选。未绑定账号且 `enabled=false` 时允许保存/关闭 5h、7d 阈值和间隔，不创建绑定、不读取或修改凭据。
- 启用定时养号仍必须有 active OAuth cc2api 绑定；无绑定时前后端都给出明确提示。
- 已绑定账号省略 `cc2api_account_id` 时保留当前绑定；绑定、切换和解绑仍走既有身份核对与独立接口，阈值保存不能隐式解绑。
- 页面无可用 cc2api 账号时仍允许提交阈值；账号下拉显示未绑定状态，定时养号开关禁用或在提交前明确拒绝。

### R6 — 兼容、发布与回滚

- 旧版非 v3 runner、旧服务容器、cc2api 请求处理和既有历史任务不得改变。
- 旧 fingerprint JSON 缺 `profile_version` 时按 legacy 展示并继续固定，除显式 `reprofile` 外不迁移。
- control/account 必须同批构建发布；生产升级前备份 v3 数据和环境 HOME。回滚代码时，profile v2 与 network context 的持久格式必须由上一版明确拒绝或兼容，不能静默混用。
- 本任务不宣称隐藏 Docker 或绕过上游风控，只移除本系统额外引入的 MITM 和确定性 bench 标记。

## Acceptance Criteria

- [ ] A1（R1、R2）：本地 HTTP 与 SOCKS 上游代理演练中，普通任务和正常养号不启动 mitmproxy，目标 TLS 服务收到的 ClientHello 与 Claude/Node 发出的字节一致，且代理不可用时没有直连请求。
- [ ] A2（R2）：显式抓包仍生成 HTTP/flow 证据；手动额度查询和养号单次样本仍更新 5h/7d 状态；三种模式切换、重启和异常收口不会串用上一执行 context。
- [ ] A3（R2）：普通任务在 passthrough 下可完成、续跑、取消和超时收尾；没有被动 quota header 时不伪造额度，未知/过期策略继续等待手动查询。
- [ ] A4（R3）：两个新账号得到不同且不可由账号名复算的 profile v2；每个账号重建后 hostname/MAC/machine-id/时区/locale 完全不变，美国代理画像使用 `en_US.UTF-8`。
- [ ] A5（R3）：普通任务可见工作树与上游抓包均不出现 `vibebench`、`benchmark`、`vb-*`、`.bench-*`、原始环境 ID 或原始 run ID；内部 Docker labels 和受限证据路径不进入请求。
- [ ] A6（R4）：不满足迁移前提的环境拒绝 `reprofile`；符合条件的合成环境进入 `profile_reauth`，重启后仍阻断普通工作，真实重授权成功才恢复。
- [ ] A7（R5）：未绑定 cc2api 的账号可以在 WebUI 保存 5h=70、7d=85 且定时养号关闭；刷新后值不变。无绑定启用养号被拒绝，现有绑定不会因省略字段被清空。
- [ ] A8（R6）：相关单测、passthrough/抓包/额度 Docker 集成、真实 Chrome 1280/390 明暗主题及完整 v3 stack 验证通过；旧版服务哨兵和 cc2api 既有请求行为不变。

## Out of Scope

- 不关闭或改写 Claude 官方遥测内容；该议题仍属于暂停的独立任务。
- 不修改 cc2api 的请求重写、TLS 客户端画像、session pool 或 token 管理。
- 不自动迁移已有正式运行历史的账号，也不批量旋转设备身份。
- 不为普通任务恢复 HTTP 明文 token 统计；需要网络明文证据时使用显式抓包。
