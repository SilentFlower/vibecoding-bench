# 退役旧三镜像发布并清理对应 GHCR 包

## Goal

清理GitHub Packages中的旧三镜像，并使它们的旧发布入口正式退役。

## Background

- 用户明确授权删除vibebench-orchestrator、vibebench-worker、vibebench-sidecar。
- 当前平台使用vibebench-v3-control/account；签名校验位于services/orchestrator/system_update_contract.py:179，旧三项属于独立历史架构。
- main的.github/workflows/docker-publish.yml仍提供旧三项的手动发布。
- 两份项目远程配置指向同一宿主；只读核查15个容器，旧三项引用为0。证据见research/findings.md。
- 当前本机GitHub令牌查询包列表返回403，明确缺少read:packages。GitHub官方支持具有包admin权限的仓库GITHUB_TOKEN执行REST包删除，实际权限需通过受控预览验证。

## Requirements

- L1：退役flower2api与默认main中旧三镜像的发布入口，当前两镜像构建及手动发行保持原合同。
- L2：清理目标精确为SilentFlower所有、关联SilentFlower/vibecoding-bench的三个container包，全部版本归本次删除范围。新旧正式两镜像均进入保护集。
- L3：先预览实际包身份、版本、引用与权限，再冻结删除计划。预检完整成功后才应用；403、归属不符、计划漂移或仍有旧发布/部署引用时停止。
- L4：权限采用仓库Actions临时令牌及最小权限。令牌与私有配置保持私有；输出只包含安全身份、版本与操作结果。
- L5：逐项保存实际删除和复查结果；部分成功如实记录。404在缺少可核验删除收据时不当作成功删除。
- L6：保留当前实例、历史v3签名发行、账号数据及内核制品；原有工作区变更按原归属保留。

## Acceptance Criteria

- [x] 两分支旧发布入口退役，当前构建与手动发行合同回归通过。
- [x] 权限/归属/版本/引用预检和冻结计划可审计，三项之外的包零修改。
- [x] 三项旧包逐项有删除收据及远端复查；部分失败有精确恢复位置。
- [x] 合成API测试覆盖403、404、漂移、错误归属、保护包及部分删除；actionlint和脚本检查通过。

## Non-Goals

当前control/account镜像改名、正式平台发版、宿主容器或数据删除。
