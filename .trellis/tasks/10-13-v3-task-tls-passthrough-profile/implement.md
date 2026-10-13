# v3 任务 TLS 透传与账号画像校正 — 实施计划

## 1. 开始条件

- [x] 最终 Brief 通过用户评审后运行 `task.py start`。
- [x] 通过 `trellis-route(target=implement)` 确认 inline/subagent；inline 时加载 `trellis-before-dev` 与相关 backend/deploy/frontend spec。
- [x] 记录父仓、cc2api 子仓和既有 22 项 dirty baseline；不得改动暂停的遥测任务与 `official-protocol-capture.md` 现有用户修改。

## 2. 网络模式与 passthrough relay

- [x] N1：实现独立 raw SOCKS relay，覆盖 HTTP CONNECT、SOCKS5/SOCKS5H、认证、IPv4/IPv6/域名、半关闭、超时和脱敏错误。
- [x] N2：把 `v3-network-context` 改为 passthrough/quota/capture 状态机，回执绑定 mode+source，旧监听未知时失败关闭。
- [x] N3：在账号运行时为普通任务、养号样本、手动额度、完整抓包、登录/重授权分别选择模式；重命名仅 Recorder 语义的 helper，避免普通路径假装存在抓包。
- [x] N4：passthrough exec 移除全部 MITM CA 注入和系统信任；quota/capture 继续显式注入。验证账号发送器与独立 API 流不受模式切换影响。
- [x] N5：调整 quota 数据新鲜度与提示，只接受真实观察；普通 passthrough run 不生成虚假 stats 或被动额度。

## 3. 固定画像 v2 与工作树

- [x] P1：实现 v3 专用随机 profile v2 和 timezone→locale 映射，补齐 `en_GB.UTF-8` 镜像 locale；旧 runner 的 `derive_fingerprint()` 保持不变。
- [x] P2：环境首次创建、显式时区更新、容器重建和身份导入使用同一持久画像；增加 schema/version 兼容测试。
- [x] P3：容器 cwd 使用不含 run/environment ID 的普通项目别名，把 `.bench-*` 控制文件移出项目树，同时保持 transcript/status/恢复入口兼容。
- [x] P4：增加受门禁保护的 `reprofile` 维护操作和 `profile_reauth` 状态；完成账号页/环境页入口、提示和重授权成功收口。

## 4. 额度配置解耦

- [x] Q1：将 `WarmupConfigIn.cc2api_account_id` 改为可选，后端区分“保留绑定、显式选择、未绑定阈值-only”，无绑定启用养号明确拒绝。
- [x] Q2：更新 WebUI 下拉、养号开关和 payload；未绑定账号可以保存 5h/7d，页面刷新准确回显。
- [x] Q3：回归绑定切换、同步、解绑、阈值 null/省略、范围/类型错误和并发配置发布。

## 5. 验证

- [x] 单元：relay 协议/认证/字节复制、network context 切换/回执、profile 随机/地区/持久、reprofile 全部拒绝条件、WarmupConfigIn/API。
- [x] Shell/Python 静态：`py_compile`、`bash -n`、`node --check`、`git diff --check`。
- [x] Docker：HTTP 与 SOCKS 上游各跑 passthrough，目标 TLS 服务比较 ClientHello/应用字节；杀 relay/代理断言无直连。
- [x] Docker：quota/capture 仍产生目标观察与 flow，passthrough 不产生明文证据且普通任务成功。
- [x] Stack：普通任务、养号单次样本、登录、继续/取消、cc2api 长流隔离、重启对账、固定 HOME 与同 run resume。
- [x] Browser：未绑定阈值保存、无绑定养号拒绝、reprofile 提示，1280/390 与明暗主题。
- [x] 全量：orchestrator、sidecar/account、deploy/v3、cc2api 受影响测试及 Check-All。

## 6. 发布与生产迁移

- [ ] 构建同批 control/account 镜像并完成本地隔离演练；Actions/GHCR 成功后再部署。
- [ ] 生产预检无活动 v3 CLI/登录，停止 v3、完整备份、加载同批镜像并启动；旧版服务保持运行。
- [ ] 先用合成环境验证三种网络模式，再对 `10-13` 执行 reprofile；确认进入 `profile_reauth` 后交给用户完成真实 CLI 重授权。
- [ ] 重授权成功后核对 locale=`en_US.UTF-8`、时区=`America/Los_Angeles`、画像持久、普通任务 TLS 透传和阈值保存；不输出代理凭据、token、prompt 或完整抓包。
- [ ] 写部署记录与双镜像/DB/HOME 回滚点；生产异常时停止新 v3，按是否已重授权选择整包回滚或离线凭据核对。
