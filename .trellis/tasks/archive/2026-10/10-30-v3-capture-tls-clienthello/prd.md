# v3：补齐 TLS ClientHello 指纹采集

## Goal

在现有抓包中持久保存原生客户端 ClientHello 和可复算的握手指纹，使项目迭代及其他抓包执行能按实际版本、执行来源、连接和 HTTP flow 追踪 TLS 证据。

## Background

- 用户此前已要求用子 agent 增加 `tls_clienthello.jsonl`；原记录只完成六条合成握手的解析验证，此前未形成采集实现。
- 当前线上与源码只保存 HTTP 和 `.flow` 的部分 TLS 协商结果；没有原始 ClientHello、有序扩展、签名算法、组或 key_share。
- 当前正式运行使用 mitmproxy 11.1.3；已有 HTTP 抓包开关、分代目录、停止保留、冻结 CLI 版本及受限文件预览。
- 用户本次明确要求跟进完成，并授权自行推送、等待 Actions 打包及部署，不再逐步请求授权。

## Requirements

- R1：现有抓包开启时新增 `tls_clienthello.jsonl`，保存客户端侧握手原始内容及准确封装说明，不把合成 TLS record 说成原始 pcap。
- R2：保存有序 cipher suites、扩展类型及原始扩展内容、signature_algorithms、supported_groups、key_share 的组／顺序／长度、ALPN、SNI 和相关版本信息；解析失败保留原始证据与明确错误。
- R3：生成可独立复算的 JA3 字符串及摘要，保留原始顺序和 GREASE 事实，指纹计算按标准过滤 GREASE；JA4 和最终 TLS 画像对齐由后续研究决定。
- R4：用同一连接 ID 关联 ClientHello 与 HTTP flow，并记录真实执行来源、冻结 CLI 版本和可核对的 run／work 范围；明确 CLI→Recorder 方向，不能混入 Recorder→上游握手。
- R5：覆盖现有普通抓包、项目迭代和养号迭代入口，沿用现有开启方式与分代路径；历史没有 TLS 文件仍能读取，不覆盖旧执行证据。
- R6：后台抓包文件列表列出该产物，受鉴权预览只显示适合展示的指纹与字段，原始握手和不透明恢复材料保留在私有文件中；不扩大原始 HTTP／flow 的公开权限。
- R7：采集或字段解析故障不能阻断 TLS／HTTP 转发；记录可诊断失败，遵守当前捕获范围与运行来源隔离。

## Acceptance Criteria

- AC1：真实固定版本 mitmproxy 与本地 TLS 客户端产生记录，独立解析原始字节与全部有序字段相符；包含 TLS 1.2／1.3、未知扩展／GREASE、缺字段或错误输入边界。
- AC2：JA3 可由独立实现或固定向量复算；不从协商结果补造客户端 offer。
- AC3：入口测试证明实际版本及执行来源穿过网络 context，TLS 记录与 HTTP 记录的连接 ID 一致；两个迭代空间及分代保留正确。
- AC4：API 文件列表／受限预览覆盖新产物及历史缺失，原始握手、票据和认证材料不在摘要或公开预览泄漏。
- AC5：推送精确提交、确认匹配 Actions 成功、部署同批镜像并健康验收后，核对线上正常项目抓包生成的文件及关联，明确保留未覆盖条件。

## Non-Goals

- 本次不修改 cc2api TLS 模板、用户身份或协议正文；不启动 280／293／303 全版本对齐研究。
- 不把 MITM 的服务端连接当成 Claude Code 原生出口，不将 JA3 当作完整画像或安全身份。
- 不清理已有抓包、工作区、会话、账号凭据或其他任务；沿用 us 部署不备份、不重算资源的既有选择。
