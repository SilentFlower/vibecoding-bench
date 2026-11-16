# 实施计划

## 执行顺序

- [x] 通过 Brief 评审，激活任务并经 trellis-route 进入 inline 实施。
- [x] 读取 gateway/web 规范及实际模型定义，增加根请求字段、入站提取与一次性冻结方法。
- [x] 同步所有 RequestDiagnostic 构造，验证原始会话经过写入、列表、详情读取及历史 JSON 兼容。
- [x] 更新前端接口、原始会话列与详情，复用复制按钮和反馈；在模型/转发方式列展示末次版本，在 Token 列展示平均 TPS；列表时间省略时区文字，同步合成 UI 夹具。
- [x] 定向验证格式、来源优先级、边界、info/debug、本地拒绝、两版本及原有转发映射；验证混合版本、API 实际版本及旧记录缺失空态；验证 TPS 正常/零值/未知/不完整和两时区列表展示。
- [x] 运行正式构建与 Rust 检查，执行合成 UI 验证。
- [x] 经 Check-All、Spec 评估、精确 Push 计划完成交接。

## 验证

- `cd services/gateway && cargo fmt --check`
- `cd services/gateway && cargo test --locked diagnostics -- --test-threads=4`
- 原生/原有转发会话映射及新增原始字段真实链路测试，按实际测试名定向运行。
- `cd services/gateway && cargo test --locked -- --test-threads=4`
- `npm --prefix apps/web run build`
- `python3 deploy/flower2api/verify_management_ui.py --output .deploy/request-original-session-id-ui`；依现有夹具使用真实静态构建产物及合成 API，覆盖复制、缺字段、长值和窄屏。
- `git diff --check`，只使用合成请求及独立测试数据库。

## 完成与恢复

- 确认旧 JSON 与原始值持久化后可读，普通 API 缺省值保持空，映射后保留原始值。
- 更新原始 session 明文例外及管理展示规范。
- 提交范围包括本任务业务改动、相关规范及任务材料；建任务时冻结的 397 个已有改动沿原基线保留。
- 发布及线上部署由后续明确指令进入项目 SOP。

## 已验证结果

- Check-All 全面检查通过，CHK 0、FBK 0；Spec 复核 written。
- 最终 `cargo test --locked -- --test-threads=4`：926 项通过，9 项专用环境测试按既有配置忽略。日志 `/tmp/request-original-session-rust-verified.log`。
- 原生网关显式回环：280/293 混合 18 次，293 映射场景 6 次；实际版本、原始会话及本地 TLS 接收校验通过。报告 `/tmp/request-original-session-native-mixed-final.json`、`/tmp/request-original-session-native-293-final.json`。
- 前端生产构建通过，合成管理页面覆盖两个时区、1280/390px、完整会话复制、末次版本和平均 TPS 边界。报告 `.deploy/request-original-session-id-ui/report.json`。
- Rust 格式、Python 语法、diff 格式通过；397 项已有改动逐项核对保持原状。
- 下一步为精确业务提交与推送，再同步任务完成态和 Close。
