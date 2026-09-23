# 技术设计

- 版本注册表增加 2.1.280 端点画像及模型级客户端可选 beta 声明；旧画像不变。
- rewriter 按精确路径识别已观察端点，专用头仅在对应端点保留。Frame 版本号来自账号选定画像；会话标识透传；不同 API 的 beta 不复用 messages 集合。
- 当前 reqwest 0.12.4 丢失名字大小写，hyper 1.9.0 已有私有 HeaderCaseMap 编码机制。固定版本源码纳入 vendor，最小补丁公开经过校验的构造接口，并在 reqwest 增加显式请求级 casing 选项，贯穿克隆、重试、重定向；未启用时维持上游行为。
- gateway 业务请求明确启用 casing；遥测路径不启用。复用现有 TLS/代理/连接池/响应转换，不重写网络栈。
- Sonnet 可选 beta 仅从原生请求的 required 集合移除，随后现有合并逻辑保留客户端提供的 token。

## 证据

基线 cc2api ded49ec。既有 data/captures/2.1.280 本地抓包、正式抓包审计摘要及 /tmp/cc280-audit/report-no-telemetry.md；不得提交包含身份和凭据的原始抓包。

## 风险

依赖补丁需要固定版本、来源及差异文件，后续升级重新核验。大小写属于 HTTP/1 表现差异，不能据此断言服务端检测规则。
