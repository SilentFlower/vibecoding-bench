# 当前实施进度

## 已完成

- 用户确认完整 Brief，task.py start 成功，implement 路由来自 route-prefs：inline。
- resource_budget.py 共用 RAM/swap 解析；固定账号新增 swap 预算、旧缺字段为 0、Docker 总额度使用 RAM＋swap。美国预算 1536m/2048m，预检分别核对 RAM、SwapFree 与 Docker SwapLimit。
- publish/pull/load、Action 的 packages:write/GITHUB_TOKEN 登录及两专用包发布、同批镜像包和 14 天 artifact 已实现。发布绑定当前仓库/父提交/run/attempt 并独占本次标记；失败重跑新 attempt，最终清单只在两件均完成后写入。
- orchestrator 132 项回归 exit 0：/tmp/v3-ghcr-runtime-tests.log。部署/发布最终 29 项 exit 0：/tmp/v3-ghcr-deploy-final-tests.log，包含已有固化预算高于当前配置时拒绝启动且不改原记录。Python 语法和 diff 检查通过；actionlint 1.7.12 验证 v3 工作流通过。
- 本地真实 registry 推送、按 digest 拉取、save/load 验证 exit 0：/tmp/v3-registry-proof.log。仅随机本地测试容器与标签，测试后已清理，没有 GHCR 写入。
- 实测确认本机和美国服务器使用 containerd snapshotter。Docker Id 可为 OCI 索引（43ff...），归档原始配置 digest 为 57974f...；两者不可混同。现新增 config_digest 和跨 store 的固定 hash 核对，实际配置解析已与归档字节一致。
- 中间批次 local-check-20261012-ghcr 构建 exit 0；因之后补齐原始配置清单，最终批次重新使用 local-check-20261012-ghcr-final，清单 /tmp/v3-local-check-ghcr-final.json、日志 /tmp/v3-image-build-ghcr-final.log，exit 0。
- 最终 /tmp/v3-docker-ghcr-final.log exit 0：实际 1536 MiB RAM/3584 MiB 总额度、原 HOME/container、共享 API 长流、取消/恢复、Recorder 故障及两账号隔离通过。/tmp/v3-stack-ghcr-browser.log exit 0：Compose、实际 Chrome 登录/环境/退出、HTTP/SSE/WS 鉴权、旧 Cookie 拒绝、备份/离线导入与旧哨兵不变通过；临时容器均已清理。
- /tmp/v3-offline-pair-proof.log exit 0：仅本地构造发布形状的清单，实际导出并加载两镜像，包大小 317787876 字节；SHA256、角色/批次/原始配置核对通过。不代表 GHCR 已发布。
- Full Check-All 完成本地提交前审查：requested=auto、effective=full、confidence=high，三维度通过，剩余 CHK/FBK 为 0；DOC-001 同步实现/演练完成状态，DOC-002 澄清初始 Docker Id 的真实语义。最终镜像冻结输入 SHA256 e31196f87dfc3172c19c190ad55a0f313bae6033a8358ed0da0ecbc123ad7dbe 与当前一致；22 项原有保留变更已逐项核对内容不变。

## 交付验收

- Update-Spec result=written；已固化有限 RAM/swap、GHCR 交付与三种镜像哈希契约。按用户确认的精确范围完成业务提交及推送，保留 22 项既有变更。
- Action 38245581074 attempt 1 成功，批次 ci-38245581074-1；两个专用 GHCR 镜像、清单及镜像包已发布。311087681 字节的交付包 SHA256 校验通过，父/子仓提交及 clean 来源吻合。
- 美国服务器使用空 DOCKER_CONFIG，按两个 registry_digest 匿名拉取成功，并通过版本、归属、端口、RAM/swap 预检后启动。新版仅 gateway/orchestrator 两容器，网络 vibebench-v3-us；空 accounts/account_environments/runs 均为 0。
- /tmp/v3-us-smoke-final.log exit 0：真实 Chrome 登录/环境页面/退出、HTTP/SSE/WS、旧 Cookie 和终端票据拒绝、外网 18080 登录及退出通过。首次验收脚本对未登录 /runtime/ 的预期写成 200，实际返回符合鉴权契约的 401；修正脚本后通过，产品代码未修改。
- /tmp/v3-us-status-evidence.json 与部署前基线逐项一致：旧 bench/cc2api 的 ID、镜像、启动时间、端口及 HTTP 200 均不变；没有停止旧服务或迁移旧账号。
- 安装 /opt/vibebench-v3-us，数据 /srv/vibebench-v3-us，管理秘密仅保存于服务器 v3.env（0600），数据根 0700；账号预算 1536m RAM＋2048m swap、活跃 1、CPU 2。新版访问入口 http://us.flower-cli.com:18080/login。
- 所有本次交付项验收完成；按已确认范围同步任务完成态及 Close，真实账号业务验证另行安排。

## 验证边界

- 新版已独立发布并部署；旧系统没有启停、账号读取或迁移。真实模型与 CLI 业务没有执行。
- 本地 CLI 业务仍用合成替身；真实 CLI 内存峰值、OAuth/模型调用及 arm64 不在本次空环境部署验收内。
