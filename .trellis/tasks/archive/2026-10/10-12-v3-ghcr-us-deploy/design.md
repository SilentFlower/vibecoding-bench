# v3 GHCR 发布与美国服务器隔离部署设计

## 目标与边界

本任务以“同一批两个镜像能在指定服务器独立启动并验证”为共同验收边界。修改只发生在父仓 v3 的发布、部署及账号资源配置；子仓固定 17d3643，不修改协议/发送实现。服务器操作仅面向新部署 us，旧 bench 8080、旧 cc2api 5674、现有数据与账号保持原样。

## 两镜像发布

- 继续使用 manage.py build 冻结源码并联合构建 control/account，不让 CI 分别从不同 checkout 或重算的输入构建两件套。
- v3-build.yml 的 v3 push 与 workflow_dispatch 使用独立批次 ci-<run_id>-<run_attempt>；发布 job 只允许 refs/heads/v3。登录 GHCR 只使用 GITHUB_TOKEN，权限 contents:read、packages:write，不新增 PAT/SSH secrets。
- 专用镜像包为 ghcr.io/silentflower/vibebench-v3-control 与 ghcr.io/silentflower/vibebench-v3-account，标签统一 v3-<release>。不写 latest 或旧三镜像包；已有批次禁止覆盖。OCI source/revision labels 关联本仓和构建提交。
- manage.py 增加 publish：读取已成功构建的本地联合清单、严格核对两镜像及干净发布来源，将同一镜像配置 ID 标记为 GHCR 引用，再推送并取得仓库 manifest digest。发布只接受当前 v3 Action 的 ci-<run_id>-<run_attempt> 新批次，核对父提交与 GITHUB_SHA、仓库归属并建立独占的本次发布标记；手工批次或同一 attempt 重试拒绝，失败重跑使用 GitHub 新 attempt。这样无需把 GHCR 首次仓库查询的 denied 当成不存在，也无需新增包元数据权限。任何一件失败都不生成完整发布清单，不撤销已经成功上传的镜像。
- 原清单 digest 保留为构建机 Docker 的 image ID；真实演练确认 containerd 可以让 Id 指向 OCI 索引，故新增 config_digest 根据 docker save 原始配置字节计算，registry_digest 保存推送的仓库 manifest/索引 digest，reference 为专用 GHCR 批次标签。启动允许匹配已固定的本地 ID、原始 config 或 OCI 根，角色/平台/批次/提交检查仍严格执行。schema/bridge/layout、父/子仓提交、冻结内容哈希保留。只有两镜像全部成功才写新的 release.json，原构建清单不覆盖。
- 同一发布产物保存两镜像 docker save 包、SHA256 和清单；artifact 保存期明确配置。包不含部署密码、账号资料、登录缓存或 Docker registry config。默认不改变 GHCR 包可见性；若首次 private 无法匿名拉取，交付同批 artifact 包，在服务器校验后 docker load，不写入包访问凭据。
- manage.py 增加 pull：以清单 registry_digest 固定下载对应仓库内容，验证 image config ID/角色/提交/批次/平台后建立清单引用。镜像包方式则先校验包 SHA256，加载后执行同样的既有 inspect_images 校验。仓库 digest 与本地 image ID 不混用。

## RAM 与 swap 契约

- V3_ACCOUNT_MEMORY 继续表示 RAM 上限；新增 V3_ACCOUNT_SWAP 表示额外 swap 上限，默认 0。美国部署设置 1536m 和 2048m，Docker Memory 为 1610612736，MemorySwap 为 3758096384（RAM＋swap）。有限预算不接受 -1、负数或格式非法的无限 swap。
- 资源值通过一个无外部副作用的共享解析模块核对，支持正整数 m/g 的 RAM 和 0/正整数 m/g 的 swap。账号首次固化 RAM/swap 预算；旧 fingerprint 缺 swap 字段时为 0，重命名、恢复和重建不重新生成身份或自动改旧预算。
- compose.yml 把新增参数明确传给 orchestrator；示例配置展示 0 的兼容默认及美国测试配置。两管理服务使用独立数据根，只有 orchestrator 挂 Docker socket。
- preflight 分别检查 MemAvailable 与 SwapFree，不将 swap 算作物理内存。物理预算为活跃账号 RAM 之和＋1 GiB 管理服务/宿主余量，并继续尊重显式的更高 V3_MIN_FREE_MEMORY_BYTES。默认 4 GiB/单账号仍要求 5 GiB；美国方案要求约 2.5 GiB RAM 与至少 2 GiB 空闲 swap。
- swap 大于 0 时核对宿主/daemon 限额支持；余量不足或不支持时拒绝启动，保持原有端口/挂载/网络预检。部署前快照不能代替实时检查，不能停止旧服务腾内存。
- 内存上限是容量边界，不能当成实际驻留用量。低内存方案的真实 CLI 峰值与交换延迟等待独立账号验收。

## 美国服务器部署

- 安装目录 /opt/vibebench-v3-us，数据目录 /srv/vibebench-v3-us；Compose 项目与网络沿用既有部署标识 us 的标签归属规则。
- 外部入口 http://us.flower-cli.com:18080，配置 V3_BIND_ADDRESS=0.0.0.0；管理及内部秘密新建且只保存在 0600 的服务器配置，数据目录 0700，文档/输出不打印内部秘密。
- 下载最终发布清单与匹配镜像，核对 amd64 平台、父/子仓提交、配置 ID、发布批次、空间及实时预算。只传送部署所需文件，不覆盖 /root/vibecoding-bench 或 /root/claude-code-gateway。
- 起步空数据库，仅两个管理服务；不导入旧账号或凭据，也不启动真实 CLI。运行 check → up → status，检查健康与浏览器/管理桥鉴权、SSE、WS、退出后旧会话拒绝。
- 启动前后核对旧 bench/cc2api 的容器 ID、image ID、启动时间和 HTTP 状态。已持续重启的旧 warp 只记录原状态，不作为本次失败或修复对象，不读取旧凭据。

## 失败与回退

- 发布失败：保留真实日志及已上传镜像，完成清单缺失则禁止部署；重试使用新批次，不覆盖旧镜像。
- 下载/镜像校验/预算/冲突失败：停止后续动作，不修复或改动旧服务。
- 新版启动异常：仅按 product=v3、deployment=us 的精确归属停止本部署，保留数据、清单和日志；回退不执行 prune 或宽范围 compose down。
- 未授权的包可见性、凭据或宿主扩容边界不能自动扩大。发布和部署是用户已提出的工作，Git 提交仍按 Trellis Push 的精确方案评审执行。
