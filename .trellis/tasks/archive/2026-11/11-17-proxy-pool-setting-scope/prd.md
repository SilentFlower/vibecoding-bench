# 代理连接池设置适用范围说明

## Goal

让管理员准确理解 Rust 代理连接池开关对请求路径的适用范围。

## Background

proxy_client_pool_enabled 控制 Rust HTTP 客户端缓存。native 模型请求由原生 SDK 发送。其他通用或后台路径需按各自实际调用位置说明。

当前Vue设置控件的标签与帮助来自apps/web/src/lib/settingsSchema.ts:423；Settings.vue:720继续把该开关映射为字符串设置值。Rust侧由tlsfp.rs的set_request_client_pool_enabled控制带代理的reqwest客户端缓存，native模型通过独立原生提交路径发送。

## Requirements

- R5.1：在系统设置页明确标注 Rust 代理连接池开关的适用范围。
- R5.2：说明 native 模型发送的连接复用由原生 SDK 自身机制管理。
- R5.3：沿用现有设置键和保存行为。
- R5.4：标签采用“Rust 代理 HTTP 连接池”；说明为“复用 Rust HTTP 客户端连接。native 模型请求的连接复用由原生 SDK 管理。”其他后台请求的适用性以实际 Rust 客户端调用链为准。

## Acceptance Criteria

- [x] 页面文案准确描述开关控制的 Rust 客户端连接池。
- [x] 页面说明 native 模型发送使用原生连接复用机制。
- [x] 原有设置值和保存行为通过定向验证。

## 验证范围

执行Web构建及使用合成接口的定向浏览器验证，核对390/1440px下的标签、完整说明、开关草稿/撤销和保存载荷中的字符串true/false。文案改动复用现有控件和验证夹具。

## 范围边界

本项是现有控件的适用范围说明。账号批量迁移、原有后端退役及原生 SDK 连接池参数调整作为独立后续工作。

## 验证证据

- Web构建通过：/tmp/proxy-pool-web-build.log。
- 复用BlockFixture的定向浏览器验证通过，390/1440px均覆盖文案、无横向溢出、草稿撤销、字符串false/true保存及刷新回读；控制台错误、意外请求和外网请求为0：.deploy/proxy-pool-setting-scope/results.json。390px截图已查看。
- 将标签和帮助还原后与开工基线全文一致，实际元数据改动为两处文本；git diff --check通过。
