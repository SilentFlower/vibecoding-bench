# 单部署切换依据

## 已确认决策

2026-11-13 后续收敛：用户将本次 Flower2API 版本作为正式维护起点，历史旧版本主动回退退出交付范围。当前旧来源读取、既有已签材料及首次迁移的失败恢复继续保留；已经完成的演练结果直接复用。

用户在 2026-11-13 选择现有唯一部署的一次性切换，范围包含 GHCR 正式包名、现有控制/账号容器和相关网络命名。原多用户过渡发布与新增通道方案由此替换。历史验签及首次迁移失败恢复继续保留。

## 现场只读盘点

- 部署 `us`，SSH 主机 `23.80.83.23`；两项控制与四个环境三角色，共 14 个运行容器。
- 当前来源 `ci-43357757874-1`，两个正式引用仍为 `vibebench-v3-control/account:v3-ci-43357757874-1`。
- 数据 `/srv/vibebench-v3-us`；固定执行器 `/opt/vibebench-v3-us/updates`；服务 `vibebench-updater-us.service`。
- 当前网络 `vibebench-v3-us`，挂载 gate/socket 到 `/run/v3-updates/`。凭据留在原受控配置，研究文件仅包含公开身份与范围。

## 代码边界

发布与本地构建：`deploy/flower2api/manage.py:514/:683/:736`。原 PRD 的 `manage.py:679` 已随代码移动。

来源读取：`services/orchestrator/system_update_contract.py:179`、`account_update_identity.py:37`；兼容演练 `deploy/flower2api/verify_database_compatibility.py:216` 按旧仓库拼接来源 digest。

运行命名：`services/orchestrator/account_runtime.py:750`、`deploy/flower2api/compose.yml:1/:45/:85`；宿主网络解析 `system_update_host.py:113`。控制服务归属已按精确产品/部署/角色标签与挂载校验，可作为新旧命名切换的权威身份。

固定源码：`install_system_updater.SOURCE_FILES`；`upgrade_system_updater.py:127` 仅将 v1 升至 v2，v2 返回 already-current。同协议刷新走 `.trellis/spec/platform/deploy/platform-online-update.md` 的固定源码专项维护 SOP。

## GHCR 首次发布

GitHub 官方文档说明新包首次发布默认 private，公开包可匿名下载；既有工作流使用 GITHUB_TOKEN 发布并建立仓库关联。新包上线前需完成可见性配置及匿名拉取验收。当前本地 gh 登录态查询 Packages 返回 read:packages 权限不足，实际发布沿既有 Actions packages:write 入口。

来源：https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#pushing-container-images

## 实施中验证项

同批新包摘要、首次迁移失败恢复、Compose 新旧项目交接、固定执行器部分替换和账号部分重建的恢复，以实际隔离 Docker 场景验证。后续正式升级与回退从新基线起算。上线前重盘点持久身份、占用及当前来源，历史只读快照用于定位，不替代现场范围检查。
