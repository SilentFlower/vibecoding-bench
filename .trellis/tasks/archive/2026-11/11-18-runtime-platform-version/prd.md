# 运行时平台版本与编译缓存解耦

## Goal

管理员看到当前控制镜像的真实平台版本，纯版本号变化复用前端及Rust编译结果。

## Background

- `images/v3/Dockerfile:9`将VITE_PLATFORM_VERSION传入前端，`:27`将前端dist复制进Rust阶段。
- `services/gateway/src/handler/router.rs:1801`通过RustEmbed嵌入前端。
- `apps/web/src/lib/platformVersion.ts:3`读取构建变量；Dashboard与SystemUpdates分别展示当前版本。
- `deploy/flower2api/manage.py:494`读取唯一发行元数据，并将其纳入来源快照。

## Requirements

- R1：从当前控制镜像的独立运行时版本文件读取规范版本，提供已鉴权管理只读API。
- R2：首页侧栏和系统更新页优先显示运行时版本；旧服务兼容现有已验签目录，按current_release精确匹配。目录过期或当前发行退出目录时，运行时版本仍正确。
- R3：无版本、非法版本和服务失败使用现有未知/历史展示，禁止把最新可用版本当作已安装版本。
- R4：移除版本号对前端与Rust编译的依赖，保持签名说明、快照来源摘要、同SHA候选和组件身份合同。

## Acceptance Criteria

- [ ] 同一代码仅改变版本号，前端与Rust阶段命中缓存，当前版本文件随控制镜像正确变化。
- [ ] Dashboard与SystemUpdates显示当前控制版本；旧后端、更新器未接入/不可达、目录无当前发行的行为分别覆盖。
- [ ] 非管理员请求沿原管理鉴权拒绝；新API只返回版本字段。
- [ ] 版本递增、签名说明、来源摘要及数据库合同回归通过。

## Out of Scope

- 演练并发由兄弟任务负责；候选换批协议、宿主更新器维护和正式发版另行处理。
