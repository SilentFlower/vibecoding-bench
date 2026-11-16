# 补齐原生发送器安全异常诊断

## Goal

让管理员在下一次原生请求失败时，按请求关联信息查到实际失败阶段、异常类型、系统或 TLS 错误码及有界 cause 链。

## Background

- 用户在排查服务器请求 `18f1e7ce-2b6a-4d65-97a0-43dd3dba7424` 后要求“补齐”异常诊断。该请求于 `2026-11-12T17:30:53Z` 组装后返回 native_error，相同正文随后换进程成功。具体底层异常仍未核实。
- 线上发布对应提交 `0fad8e42e896d16a237695d29c13f24dccf83b1b`。sender 日志文件实测 0 字节。`services/gateway/src/bin/account-sender.rs:6` 缺少日志初始化。
- `services/gateway/src/service/native_runtime.rs:1093` 将原生错误替换成固定错误体，普通日志只投影受控 code 与原错误 SHA256。`services/runtime/src/runtime/293/worker.ts:136` 当前只传 error、可选 code/status。
- `services/gateway/src/service/native_runtime.rs:585` 在进程退役时清理私有目录，后续诊断必须独立于该目录生命周期。

## Requirements

- R1：sender 默认输出可检索的结构化日志，支持现有 RUST_LOG 过滤方式。
- R2：原生失败保留实际阶段、白名单异常类型、白名单错误码和最多八层 cause 摘要；未知值显示 unknown，循环和超限具有明确标记。
- R3：sender 独立安全校验摘要，关联 native job/attempt ID、worker ID/PID、账号 ID 和环境代次。沿用网关根请求 ID 与 attempt ID 的关联。
- R4：普通日志只包含固定枚举、数值、关联标识和原有 SHA。异常 message、stack、URL、凭据、邮箱、完整请求及响应正文保持私有。
- R5：兼容旧内核缺省诊断字段。缺失或不合法的新诊断单独显示采集状态，现有请求及响应语义继续沿既有路径。
- R6：保持每请求最多一次模型提交，取消、HTTP 错误、流中断和进程隔离沿既有生命周期。
- R7：使用合成身份和离线回环验证跨语言协议、真实错误路径、日志落地与秘密隔离。

## Acceptance Criteria

- A1 / R1、R3：实际 sender 启动入口在默认配置下输出日志，错误可按 job/worker/account 关联。
- A2 / R2、R7：连接拒绝、连接重置或提前关闭、TLS 错误、超时、普通构造异常保留实际阶段与已知分类，未知错误显示 unknown。
- A3 / R2、R4：cause 循环、超过八层、异常 getter、带秘密的 name/code/message/stack/URL 和任意扩展字段具有安全回归。
- A4 / R3、R5：新旧事件、缺省诊断、非法摘要和跨请求帧经过实际解码与 sender 路径验证；非法诊断原文不进入日志。
- A5 / R6：成功、上游 HTTP 拒绝、取消和退役保持原语义，夹具核对实际发送次数。
- A6 / R7：gateway 格式检查和完整 Rust 测试通过；runtime 类型检查、单元、集成和定向原生离线验证通过。

## Out of Scope

- 生产部署、签名内核发行、线上切换、真实账号调用和付费推理。
- 数据库迁移、管理页面、历史异常回填、自动重试或恢复策略。
- 保留失败进程完整 HOME、原始 IPC、完整异常 message/stack 或业务正文。
