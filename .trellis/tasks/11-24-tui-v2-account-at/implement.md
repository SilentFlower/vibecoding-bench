# 实施和验证

1. 用合成账号凭据和官方 2.1.293 复现 V1 的注入，在隔离回环 HTTP 服务核对 OAuth 模式及授权头。复用 [原版 CLI 联调脚本](../../../deploy/flower2api/verify_tui_cli_handoff.py) 的模型回环和时序验收方法。核对待改类型 `TuiReservationIdentity`、`AccountSource`、`SessionDriver` 和现有 V1 凭据解析。
2. 接通 Gateway 的已选账号凭据与一次性私有提交。核对过期、刷新、跨账号、旧镜像与无法获得授权的情形。验证秘密的内存生命周期和日志脱敏。
3. 在默认账号镜像启动原版交互 CLI，核对合成 AT 注入、回环鉴权及账号上游的真实接收。验证工具轮换代及迁移排空，留住同进程工具回执。保持本地开发提供方可通过同一隔离入口回归。
4. 在 `services/gateway` 运行 `cargo test --locked --lib tui` 及受影响的现有凭据回归。从账号镜像验证切换，运行 `deploy/flower2api/verify_tui_account_switch.py` 的定向路径，补齐正常 CLI 首轮和 Read 续轮、两账号交错、更新 AT、重复回填以及回切 V1 的观察。
5. 在账号页开放受管账号的 V2 选择。通过真实 Gateway 和账号 sender 的隔离场景核对页面读取、休眠账号启用、V2 回切和在途工具归属。
6. 把候选制品和验证证据交给母任务，沿签名 SOP 完成线上安装、全量开放选择和真实订阅验收。

## 账号自主切换验证

Chromium 使用两个休眠账号核对选项展示及按账号保存。隔离 Docker 使用实际 Gateway 和账号 sender，编排登记与事件源由本机测试程序提供。休眠启用 V2、休眠切回 V1、重复双向切换和已有续轮保留原内核均通过。完整证据见[账号凭据和切换实测](research/managed-oauth-smoke.json)。
