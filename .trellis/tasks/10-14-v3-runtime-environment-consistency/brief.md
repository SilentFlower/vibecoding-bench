# Brief — v3 固定执行环境与题库主题修复

## Goal

- 统一账号容器与 CLI 的实际环境，新环境默认洛杉矶时区＋美国英语 UTF-8，并调整题库主题。

## Scope

- 修复任务、养号、抓包、恢复、续聊和登录的 TZ／LANG／LC_ALL 覆盖及页面展示。
- 停止创建并安全清理系统遗留的 `.claude-home` 空目录。
- 收紧 root 管理脚本及 /sidecar 的读取权限，保留 CLI 额度采集执行权限。
- 替换网络协议、代理、扫描、安全及生物医疗题目，检查模型训练／微调；普通联网应用保留。

## Non-Goals

- 历史业务产物、凭据、代理和设备身份保留；已有账号不批量改时区。
- 本轮完成本地代码与隔离验收，线上部署另走发布流程。

## Technical Overview

- 每次 CLI 从已持久化账号环境读取设置，覆盖旧 worker_env 和受管理 settings.env；只对已确认的空目录使用 rmdir。

## Context & Decisions

- 默认 `TZ=America/Los_Angeles`、`LANG=LC_ALL=en_US.UTF-8`，按夏令时自动切换。
- 已有环境沿用保存值；显式时区设置继续有效；旧 runner 保持原行为。
- 保留已检查通过的被动额度改动，本修复单独记录。

## Risks

- 脚本权限收紧须验证 root 网络与抓包仍正常；非空目录及未知链接不能删除。

## Acceptance

- 实际 CLI 的 locale、ls/date 和页面与账号环境一致。
- 任务目录不新增系统空目录，原 HOME／session 保持。
- 通过相关回归及隔离 Docker／浏览器验证，不使用封禁账号发送请求。

## Next Step

- Check-All 已通过，下一步进入规范同步。

