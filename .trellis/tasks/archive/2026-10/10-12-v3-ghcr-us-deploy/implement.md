# v3 GHCR 发布与美国服务器隔离部署执行计划

## 当前状态

- 用户已确认完整 Brief，任务处于 in_progress，implement 路由为 inline。代码、单元回归、最终 Docker/Chrome 演练及双镜像离线加载均完成；Full Check-All、Update-Spec、真实 CI/GHCR 发布及美国服务器部署验收均通过，当前同步任务完成记录。
- 受保护内容：已有 official-protocol-capture.md 修改与两个历史任务，共 22 项，保持不变。父仓基线 28dd685，子仓 17d3643。

## 1. 资源配置与兼容实现

- [x] 通过 task.py start 与 trellis-route implement 后，读取 backend/deploy specs 和相关实际数据定义。
- [x] 增加共享纯资源解析模块，供部署入口和账号 Runtime 使用；不引入新后台状态服务。
- [x] 在新账号预算中固化额外 swap，创建 Docker 时使用 RAM＋swap 总上限；缺字段的历史账号保持 swap=0，身份不重算。
- [x] Compose 传递 V3_ACCOUNT_SWAP，示例和 README 说明默认/美国起步配置；预检分别核对 RAM、SwapFree 和 daemon 支持，保留原冲突保护。
- [x] 增加有效回归：1536m＋2048m 对应实际 Docker 参数、0/旧缺字段兼容、非法/无限值拒绝、swap 缺少/不足、默认 4g 门槛与低预算、恢复后身份和预算保持。

## 2. 联合发布实现

- [x] 增加 manage.py publish/pull/load 和明确参数，基于实际两镜像清单，不重建或改写既有 batch。
- [x] 绑定当前 Action 的仓库、父提交、run ID/attempt 和新输出路径，独占发布标记拒绝同批重试；认证/网络失败不伪报不存在，重跑使用新批次。
- [x] 分别记录本地 ID、原始 config_digest 与 registry_digest；两件成功后才原子写最终清单并保存同批镜像包及校验。
- [x] v3 工作流登录/权限/发布步骤、独立包名/批次标签、artifact，Dockerfile 增加必要 OCI 归属 labels。
- [x] 定向验证第一件/第二件推送失败、来源/批次、digest 错配、半清单与镜像包篡改；本地 build 不自动发布。最终实际 GHCR 发布仍待 CI。

## 3. 本地核对与质量流程

- [x] Python 部署和 Runtime 回归、语法/diff 检查；工作流语法与 CI ref/permission/secret 检查。
- [x] 联合重建两个 amd64 镜像；本地实际 Docker 核对资源上限、合成 CLI 生命周期与管理桥。复用未变化 Rust 有效证据，受影响来源不一致时重跑。
- [x] 进入 check 路由做 Check-All，修复后保留失败与最终通过证据；按当前 owner 推进 Update-Spec，再展示精确 Git 推送方案。
- [x] 不在验证未完成时宣称发布或部署成功。确定与旧系统无关的修改才纳入提交，task 记录同步遵循实际交付状态。

## 4. CI 发布与服务器部署

- [x] 已确认精确提交/推送后，等待或触发 v3 Action；核对两镜像、最终清单、镜像包和 SHA256，记录真实 run/release/digest。
- [x] 只读刷新远程资源与旧服务基线；核对 18080 和两个新目录均无冲突。
- [x] 两个 GHCR 镜像已通过空 DOCKER_CONFIG 按 registry_digest 匿名拉取并校验；同批 artifact 包完成 SHA256 核对，没有新增 PAT 或修改包可见性。
- [x] 安装新版部署文件与 0600 配置，生成独立管理/内部秘密；采用账号 1536m RAM＋2048m swap、活跃 1，CPU 上限 2。
- [x] 执行 check → up → status；如实时预算不满足，停止并报告实际差额，不停止旧服务或悄悄下调预算。
- [x] 核对管理登录、空环境、鉴权/HTTP/SSE/WS/退出和持久目录；核对旧 bench/cc2api 容器及 HTTP 状态不变。
- [x] 将精确访问入口、管理密码获取位置、版本和仅新版的停止/回退方式交付；管理密码不得混入公开日志或 Git。

## 验证入口

- python3 -m unittest discover -s deploy/v3 -p 'test_*.py'
- 项目既有 orchestrator 回归入口及 AccountRuntime 定向测试，按实际 Python 依赖环境执行。
- python3 -m py_compile deploy/v3/manage.py orchestrator/account_runtime.py 及新增资源模块
- python3 deploy/v3/run_local_verification.py --manifest <最终本地批次清单>
- python3 deploy/v3/verify_stack.py --manifest <最终本地批次清单> --browser
- git diff --check；gh run view <真实发布运行>；远程 scripts/v3-stack check/up/status --env <独立配置>

## 验收限制

- 所有本地 CLI 业务演练明确为合成替身，真实账号 OAuth/会话/模型调用不在本次空环境验收中。
- 当前平台只验证 linux/amd64，arm64 和真实 CLI 内存/交换峰值另行验收。
- 新版资源异常只停止 deployment=us；保留旧服务、账号与数据，不自动接管、重启或清理。
