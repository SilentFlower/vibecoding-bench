# v3 GHCR 发布与美国服务器隔离部署

## Goal

使 v3 的同批 control/account 两镜像可从 CI 交付到 us.flower-cli.com 的独立实例，并可核对版本与回退。

## Background

- 现有 `.github/workflows/v3-build.yml:1` 仅构建两个本地镜像并上传版本清单；最新运行 38228843411 已成功，没有 GHCR 登录或推送步骤。
- 初始 `deploy/v3/manage.py:56` 的启动校验使用 Docker 本地 Id、角色、批次、平台及父/子仓提交；后续实测发现 Id 可指向 OCI 索引，原始 config_digest 与仓库 registry_digest 应分别记录，不能一概把本地 Id 当成配置哈希。
- 2026-10-12 只读核对：服务器为 amd64、4 核、约 5.8 GiB 总内存，约 2.7 GiB 可用，磁盘余量约 28 GiB，Compose 5.1.4。旧 bench 使用 8080，旧 cc2api 使用 5674；18080 空闲。
- `/opt/vibebench-v3-us` 与 `/srv/vibebench-v3-us` 均不存在。旧 bench、cc2api、AstrBot/llbot 正在运行，kin-02、vm2api 及其 Caddy 已停止。
- 当前 gh 凭据缺少 read:packages，包列表查询返回 403；这不代表 workflow 自身的 GITHUB_TOKEN 无法按 packages:write 发布。首次包可见性需以发布后的实际匿名拉取结果为准。
- `deploy/v3/manage.py:138` 的默认启动门槛为至少 5 GiB 可用内存及每活跃账号 4 GiB，目前服务器不满足默认预算。
- 后续 swap 核对：宿主有约 8 GiB swap、剩余约 6.3 GiB；`orchestrator/account_runtime.py:305` 将 mem_limit 与 memswap_limit 设为相同值，当前账号容器不能使用 swap。上述默认内存值是预算/上限，不是实测最低需求。

## Requirements

- R1：v3 CI 发布两个专用 GHCR 镜像，使用相同的唯一批次标签，不覆盖旧镜像或 latest；保存父/子仓版本、实际配置 ID 及仓库 manifest digest。
- R2：联合版本清单能用于远程交付，镜像从 GHCR 拉取后仍通过现有严格校验；两个镜像均成功后才产生可交付清单。
- R3：保留同批镜像离线包及内容校验，首次私有包不可匿名拉取时可通过已授权的仓库 artifact 交付；服务器不保存新增 GHCR PAT，不把凭据放到 artifact、日志或任务文件。
- R4：在 us.flower-cli.com 新建独立的 v3 安装及数据目录、Compose 项目、网络和 18080 端口；生成独立管理及内部秘密。起步使用空数据库与空账号环境。
- R5：部署前后核对旧服务容器 ID、镜像、启动时间及端口；不重启旧服务、不读取或迁移其 OAuth/profile、不修改现有代理，不执行宽范围 prune。
- R6：用户已选定美国服务器起步预算：每账号 1536 MiB RAM＋2048 MiB swap，活跃账号上限 1；配置、创建容器和预检使用同一语义。部署前分别核对物理内存和 swap 余量，通过预检才启动，不停止其它服务来凑预算。
- R7：验证新版管理入口、登录/退出、运行环境列表、HTTP/SSE/WS 桥接鉴权和持久目录；本次实际账号 CLI 业务验证等待独立测试账号及足够资源。

## Acceptance Criteria

- [x] A1（R1、R2）：GitHub Actions 发布成功，两镜像及清单属于同一批次；配置 ID 与仓库 digest 分别记录且可回查。
- [x] A2（R2、R3）：同批镜像在干净加载/拉取环境通过现有镜像校验；任一推送失败不生成完整交付清单；旧清单/标签不被覆盖。
- [x] A3（R4、R6）：远程启动仅在端口、挂载和实时资源预检通过后执行；新目录及网络归属正确，秘密文件权限受限。
- [x] A4（R4、R5、R7）：两个管理服务健康，独立管理入口可登录并显示空环境；旧 bench 与 cc2api 容器及服务状态保持原样。
- [x] A5（R1～R7）：记录实际批次、部署验收和精确回退路径；真实账号、arm64 和压力场景未执行时明确标注。

## Non-Goals

- 不改动 cc2api 请求协议及账号发送实现，不增加第三个最终镜像，不合并 main 分支。
- 不切换旧流量，不自动接管旧账号/调度，不恢复 kin-02/vm2api，不改现有服务端口或数据目录。
- 不自动改变 GHCR 包可见性、不新建或长期保存包访问 PAT，不把服务器 SSH 密码加入 GitHub Secrets。
- 不实施额度阈值、遥测修复或真实账号养号/模型调用；arm64 和真实 CLI 峰值另行验收。本次独立入口为 http://us.flower-cli.com:18080，使用新管理密码。

## Decisions

- 2026-10-12 用户对每账号 1.5 GiB RAM＋2 GiB swap、活跃账号 1 的方案回复“可以”。这确定本次资源预算；最终方案仍通过 Brief 评审再进入实现。
- 保留现有默认 4 GiB RAM、账号 swap 关闭的兼容行为；低内存预算只用于新美国部署。历史环境缺少 swap 字段时仍按关闭处理，已保存身份及 HOME 不随配置重算。
- 初次部署只启用两个管理服务。实际账号容器随新增账号创建，CLI 登录、养号或模型调用等待独立账号验证，不把空账号部署当作真实业务验收。
