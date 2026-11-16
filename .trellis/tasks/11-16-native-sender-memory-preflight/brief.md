# Brief — 移除原生sender固定内存最低预检

## Goal

- 移除普通原生sender按预估内存公式阻断准备和启动的门槛。

## Scope

- Python编排和Rust发送器三处普通exec内存预检，覆盖280/293及历史单版。
- 相关配置注释、回归测试、部署说明和资源Spec。

## Non-Goals

- CRIU恢复预算调整、池架构改造和新增内存测量。
- 已发布v1.11.0的改写、后续发版和生产安装。

## Technical Overview

- 删除固定MiB公式。有限额度继续写入实际资源配置；无限模式继续使用memory_mib=0。两版共同使用原物理进程许可。

## Context & Decisions

- 默认账号内存已为unlimited。同账号同版共享映像，每worker保有独立堆和缓冲。
- 保留有限预算格式、账号总RAM及角色最低份额校验。
- 保留账号并发、RPM、max_workers=2×标准并发、真实退出归还及制品身份校验。
- CRIU继续独立判断恢复预算，额度不足时走普通exec。旧故障码继续兼容。

## Risks

- 过小的有限额度可能在实际启动时触发资源不足，沿既有错误处理。

## Acceptance

- 低于旧公式的合法有限预算通过普通配置准入，冻结额度和worker上限正确。
- unlimited保持原语义；缺失/非法有限预算、角色总额不足、零worker及身份异常仍拒绝。
- 跨版总容量、退出归还和CRIU回退回归通过，当前文档一致。

## Next Step

- 激活任务并通过Trellis路由开始实施。
