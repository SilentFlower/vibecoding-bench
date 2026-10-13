# Brief — v3 任务 TLS 透传与账号画像校正

## Goal

- 让 v3 的普通 CLI 使用账号代理但保留 Claude Code 原生 TLS，并把账号环境改为地区一致、首次随机且永久固定的画像，同时允许未绑定 cc2api 的账号单独保存普通任务额度阈值。

## Scope

- 为普通任务、正常养号、登录和凭据刷新增加无 MITM 的 passthrough 网络模式。
- 为手动额度采样和显式抓包保留相互隔离的 quota/capture 检查模式。
- 新增 v3 profile v2、地区与 locale 配对、普通工作目录及控制文件隔离。
- 新增受门禁保护的显式 `reprofile`，用于符合条件的 legacy 环境一次性校正并强制重授权。
- 解耦额度阈值保存与 cc2api 绑定，修复 `10-13` 当前无法保存 5h/7d 的问题。
- 完成双镜像、本地代理/TLS、Docker、浏览器、完整 stack 与生产迁移验证。

## Non-Goals

- 不关闭或改写 Claude 官方遥测内容。
- 不修改 cc2api 的请求重写、TLS 客户端画像、session pool 或 token 管理。
- 不自动迁移有正式运行历史的账号，也不批量旋转设备身份。
- 不在普通任务中保留 HTTP 明文 token 统计；需要明文证据时使用显式抓包。
- 不承诺隐藏 Docker 或规避上游风控。

## Technical Overview

- CLI 流量继续经过 `tun0 -> hev-socks5-tunnel -> 127.0.0.1:8080`；passthrough 使用自带测试的 raw SOCKS relay，对接现有 HTTP/SOCKS 账号代理并只复制字节，quota/capture 才启动 mitmdump 与 Recorder。
- 调度器把 `passthrough | quota | capture` 和执行 source 写入私有 context；账号容器切换监听进程后返回绑定 mode+source 的原子回执，回执不一致时不启动 CLI。
- passthrough 不加载 MITM CA；普通任务不再被动读取 quota header，额度未知/过期继续等待用户现有的手动查询入口。
- profile v2 分别随机并持久化 hostname、machine-id 和 MAC；时区来自账号配置，locale 由时区地区映射。旧 fingerprint 保持不变，只有显式 `reprofile` 才迁移。
- `reprofile` 只允许未绑定、无 task/run、无设备观测且完全空闲的环境；迁移后进入 `profile_reauth`，只有真实重授权成功才解除。
- `WarmupConfigIn.cc2api_account_id` 改为可选；未绑定且不启用定时养号时，只保存间隔与显式阈值，不触碰凭据或绑定。

## Context & Decisions

- 生产 `10-13` 使用 `us-8` HTTP 代理和 `America/Los_Angeles`，但 locale 为 `ja_JP.UTF-8`；当前没有 task/run、没有设备观测、容器已停止，满足显式校正的基础条件。
- passthrough 必须支持 HTTP、SOCKS5 和 SOCKS5H，代理故障时失败关闭，不能回退直连。
- 正常养号使用 passthrough；只有未知/到期额度领取的单次样本使用 quota，样本暂停后恢复到 passthrough。
- cc2api 账号发送器独立于 CLI 网络监听，本轮保持原行为。
- 暂停的遥测任务与用户已有的 `official-protocol-capture.md` 修改不进入本任务改动范围。

## Risks

- raw relay 同时处理 HTTP/SOCKS 认证、半关闭和失败收口；必须用本地代理与 TLS 字节级测试证明没有改写或直连回退。
- 普通任务失去被动 quota header 后，阈值数据可能更早过期；现有 fail-closed 和手动查询必须保持可用。
- 画像迁移会造成一次明确的设备变化；生产 `10-13` 必须先备份、再校正、再由用户完成真实重授权，任何中断都保持门禁。
- 工作目录与控制文件迁移可能影响 session resume、transcript 和历史证据路径，需要兼容回归。

## Acceptance

- HTTP/SOCKS 代理下普通任务和正常养号不启动 mitmproxy，目标服务收到 Claude/Node 原生 TLS 字节；代理故障没有直连。
- quota/capture 仍能产生预期额度与 flow 证据，三种模式切换和重启不会串用 context。
- profile v2 随机字段跨账号不同、同账号重建不变，美国画像使用 `en_US.UTF-8`；普通工作树与上游请求不出现 bench 标记或原始 ID。
- 不符合条件的环境拒绝 `reprofile`；符合条件的环境重启后仍保持 `profile_reauth`，真实重授权成功才恢复。
- 未绑定账号可保存 5h=70、7d=85，刷新后不变；无绑定启用定时养号被明确拒绝，已有绑定不会被隐式清空。
- 单测、字节级 TLS/代理集成、Docker、真实 Chrome、完整 v3 stack 和旧版服务哨兵验证全部通过。

## Next Step

- Check-All 已严格通过；等待用户回复继续后进入规范更新。
