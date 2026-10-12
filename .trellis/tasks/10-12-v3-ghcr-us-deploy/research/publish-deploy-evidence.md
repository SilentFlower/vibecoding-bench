# v3 发布及服务器交付证据

## 已验证的 CI 和启动契约

- CI 38228843411 / 父仓 28dd685 / 子仓 17d3643 构建成功，artifact 仅版本清单。工作流只有 contents:read，无 registry 登录与 push。
- `build()` 构建冻结源码，清单 schema=3、images[role]={reference,digest,platform}；digest 为 Docker image inspect 的 Id。远程发布新增仓库 digest 必须保持其不同语义。
- `inspect_images()` 要求 reference 完全匹配，禁止 latest，必须含 :v3-；验证本地配置 ID、平台和 vibebench.product/role/release/parent-revision/gateway-revision。
- `preflight()` 默认账号 4g、活跃上限 1，要求至少 5 GiB 可用内存；还检查端口、名称、挂载、网络及数据目录归属。

## 2026-10-12 服务器核对

- SSH 使用既有身份可以连接；未使用或持久化用户在对话提供的密码。
- amd64 / 4 CPU / MemTotal 6066888 kB / MemAvailable 2791260 kB；磁盘可用 30044348416 字节。资源是当时快照，不能替代部署前检查。
- 旧 bench：容器 71f690870882，端口 8080，启动时间 2026-10-11T10:07:04.248791493Z；挂载 /root/vibecoding-bench/data。
- 旧 cc2api：容器 0ea549dc66ed，端口 5674，启动时间 2026-10-08T08:46:57.676390645Z；挂载 docker_claude-code-gateway-data。
- 18080 尚未占用；建议的新安装目录 /opt/vibebench-v3-us 与数据目录 /srv/vibebench-v3-us 均不存在。
- kin-02、vm2api 和 vm2api-caddy 均已停止；只读核对阶段没有启停任何服务器容器；最终新版启停记录见后文。
- gh 查询包列表返回缺少 read:packages 的 HTTP403。CI 使用独立的 GITHUB_TOKEN；不得把当前用户凭据缺少权限误报为 CI 发布被拒绝。

## 规划时边界（历史记录）

- 用户授权部署到指定服务器，沿用此前新版与旧版并行、端口与账号隔离的要求。
- 发布实现尚未开始；服务器内存方案已由用户选择每账号 1.5 GiB RAM＋2 GiB swap、活跃账号 1，仍禁止停止已有服务来凑资源。
- 新包初始可见性与实际匿名拉取仍待发布后核对；可从同批 artifact 交付精确镜像包，避免为此扩张服务器凭据权限。

## swap 与默认预算补充核对

- 后续只读快照：MemAvailable 2804184 kB，SwapTotal 8388600 kB，SwapFree 6639656 kB；两个约 4 GiB swapfile，已用约 1.67 GiB。vmstat 的两次间隔采样 si/so 均为 0，仅说明短采样内没有换入换出，不能代表业务负载。
- Docker 当前没有报告 swap limit 支持警告。旧 bench 约 152.7 MiB、旧 cc2api 约 320.5 MiB；这些是旧实例当时用量，不能推导 v3 CLI 峰值。
- `orchestrator/account_runtime.py:305` 同时设置 mem_limit=fingerprint["mem"] 与 memswap_limit=fingerprint["mem"]，账号容器实际不允许使用 swap。Docker 官方文档明确等值配置禁止 swap：https://docs.docker.com/engine/containers/resource_constraints/。
- `deploy/v3/manage.py:144` 将默认 5 GiB 与账号上限乘活跃数加 1 GiB 取最大值，仅比较 MemAvailable；未统计 SwapFree。4 GiB 是账号上限，不是进程启动即使用或预分配的容量；5 GiB 也不是实测最低要求。
- 先前以默认预检门槛提出扩容，是预算解释不充分；目前证据不支持必须扩容。用户随后选定单活跃账号 1536 MiB RAM 加 2 GiB swap；实现需同步配置、预检和实际运行限制，真实 CLI 最低配置仍未经实测。

## 发布文档与现有入口

- GitHub 官方容器发布文档支持 workflow 使用 contents:read、packages:write 与 GITHUB_TOKEN 登录 GHCR：https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images。
- 新容器包的可见性及包/仓库关联遵循官方容器仓库文档：https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry。既有三镜像 main 工作流使用 docker/login-action@v4；新 v3 工作流保持独立 ref/包名。
- `verify_stack.py` 的实际管理交换入口为 POST /admin/runtime/session，使用管理 Bearer 密码；环境查询 /runtime/api/environments，退出 /runtime/logout。远程 smoke 沿用这些已存在契约，不增加新的登录 API。
- 原账号预算首次保存于 fingerprint_json.mem；创建容器使用 mem_limit 和 memswap_limit。新增 swap 预算应和首次资源预算一同固化，缺失字段沿用旧行为，不覆盖已有身份。


## 2026-10-12 真实 CI/GHCR 发布

- Action：https://github.com/SilentFlower/vibecoding-bench/actions/runs/38245581074，attempt=1，全部步骤 success；原始日志 /tmp/v3-ghcr-ci-38245581074.log。
- 批次 ci-38245581074-1，父仓 9eb94536ddb69adfbee17f064d589907a3c3abfb，子仓 17d36431b9aebbffe2fada5d0825ef8be33673cf，dirty_worktree=false，平台 linux/amd64。
- control：ghcr.io/silentflower/vibebench-v3-control:v3-ci-38245581074-1；config_digest=sha256:46ec36ea0b683bfc75a1ceb990d64a6a02355f39156ad30179ae09aef3802725；registry_digest=sha256:065135b163f315e9c9e0720582b60c02829d8107bbf8eded521c02b6208612d1。
- account：ghcr.io/silentflower/vibebench-v3-account:v3-ci-38245581074-1；config_digest=sha256:4a57ca4e0ed8007e0c2fba681e256d5e75773ae6da95770b18ea5e83e046e9bc；registry_digest=sha256:ba5ac696858eb362e7782f95da58f52542f4688352db62cb3012ca1623834e4f。
- artifact v3-release-38245581074-1 下载至 /tmp/v3-ghcr-artifact-38245581074。镜像包 311087681 字节，SHA256 d3bdc7a7fb1498e49eddac182e9d9803e30f10e7b68dfb293e59e7e1b1ce0d42，与清单核对通过；没有把部署密码或账号资料写入 artifact。

## 美国服务器实际部署及验收

- 业务提交的部署文件通过 git archive 导出，压缩包 SHA256 2a4ef0c0eab55c6f1a9360a945f01fc059b5be451b8ab25c900cee85db72a0c3；安装后先核对归档与 source-revision.txt。服务器 Python 不支持 tarfile 的 filter 参数；解包前已拒绝链接、非常规成员及越界路径，修正调用后安装成功。
- 启动前 MemAvailable=2876567552、SwapFree=6799532032 字节，Docker SwapLimit=true，18080 空闲，新安装/数据目录未被占用。scripts/v3-stack check 和 up exit 0。
- 空 DOCKER_CONFIG=/opt/vibebench-v3-us/.docker-anonymous 实际按 digest 拉取两镜像 exit 0，无新增 PAT、包可见性变更或离线替代加载。服务器 containerd 的实际镜像 ID 是仓库 digest，status 的 matches_release=true，验证跨存储清单匹配。
- 新容器 gateway=0272c741d340（healthy）、orchestrator=206a0855fe22（running、HTTP 就绪），RestartCount=0；均属于 deployment=us，独立网络 vibebench-v3-us，仅 gateway 发布 0.0.0.0:18080，账号容器尚未创建。
- 数据 /srv/vibebench-v3-us（0700）、归属 marker=us，gateway/gateway.sqlite 与 bench/db.sqlite 各自创建；accounts/account_environments/runs 均为 0。配置 /opt/vibebench-v3-us/v3.env（0600），管理密码字段 V3_ADMIN_PASSWORD；内部秘密不展示、不写入任务记录。
- 配置及 orchestrator 实际环境：V3_ACCOUNT_MEMORY=1536m、V3_ACCOUNT_SWAP=2048m、V3_MAX_ACTIVE_ACCOUNTS=1、V3_ACCOUNT_CPUS=2。实际 Docker 1536 MiB RAM/3584 MiB 总额限制已由本地演练验证；未以真实账号在服务器运行 CLI。
- /tmp/v3-us-smoke-final.log exit 0：临时 SSH 转发下 HTTP/SSE/WS、终端票据鉴权、真实 Chrome 登录/环境页面/退出、旧 Cookie 重放拒绝通过；外网 http://us.flower-cli.com:18080 的登录、空环境查询、退出和未登录 401 均通过。临时浏览器和转发已收口。
- 首次 /tmp/v3-us-smoke.log 仅因脚本把未登录 /runtime/ 期望误写成 200 而 exit 1；实测 401 符合现有鉴权契约。修正验收脚本并加入外网鉴权完整交换后通过，没有产品修复。
- 部署前 /tmp/v3-us-old-baseline.json 与部署后 /tmp/v3-us-status-evidence.json 对比通过：旧 bench 71f690870882、旧 cc2api 0ea549dc66ed 的完整 ID、镜像、启动时间及 8080/5674 映射一致，两个入口仍 HTTP 200。没有旧服务 stop/restart、旧凭据读取、账号迁移或宽范围清理。

## 访问及仅新版的回退入口

- 新版入口：http://us.flower-cli.com:18080/login；管理密码仅从服务器 /opt/vibebench-v3-us/v3.env 的 V3_ADMIN_PASSWORD 获取。
- 状态：/opt/vibebench-v3-us/scripts/v3-stack status --env /opt/vibebench-v3-us/v3.env。
- 停止/撤回新版入口：/opt/vibebench-v3-us/scripts/v3-stack stop --env /opt/vibebench-v3-us/v3.env。只收口 product=v3、deployment=us 的角色，保留目录与容器；旧 8080/5674 继续运行。
- 本次是首个已部署 v3 批次，没有可自动切换的历史 v3。停机后可用 backup --env /opt/vibebench-v3-us/v3.env --backup-dir <全新独立绝对目录> 保存快照；不得用旧版镜像直接启动新数据库。
- 真实账号 OAuth/CLI/养号/模型调用、CLI 峰值与交换延迟、arm64 未执行，继续作为后续独立验收，不以空管理环境验证代替。
