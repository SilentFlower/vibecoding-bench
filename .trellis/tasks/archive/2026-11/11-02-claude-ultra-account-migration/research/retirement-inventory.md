# 旧版退役盘点（2026-11-02，只读）

## 精确已知资源

| 资源 | 当前状态 | 对应数据 |
| --- | --- | --- |
| 容器 `vibebench-orchestrator` | running，Compose project `vibecoding-bench` | bind mount `/root/vibecoding-bench/data` → `/data` |
| 容器 `docker-claude-code-gateway-1` | running，Compose project `docker` | 命名卷 `docker_claude-code-gateway-data` → `/app/data` |
| 镜像 `vibebench-orchestrator:ac0d59b-workerfp2to6g-auto-nudge-2abe4b4185` | 当前由上述旧 orchestrator 引用 | 删除前必须先退出相应容器并复核全部引用 |
| 镜像 `cc2api:deploy-34ed25f-293-20261008t083527z` | 当前由上述旧 gateway 引用 | 删除前必须先退出相应容器并复核全部引用 |

当前未发现其他容器挂载旧 bench 数据根；该结果是单次快照，执行前必须重新盘点，不能据此省略活动 worker 与共享引用检查。其他现有容器不属于本清单。

## 数据边界

- 旧 bench 数据根 `du -sb` 为 7,398,326,662 字节，约 7.4 GB；这是目录逻辑大小，不是承诺的磁盘释放量。
- 旧 gateway 卷数据为 139,320 字节。应通过精确 `docker volume rm` 管理命名卷，不能直接删除 Docker 私有数据目录。
- 旧库共有 17 条账号记录、11,115 条任务、11,116 条运行。未软删除账号为 7-19 与 9-17，后者是本轮迁移对象。
- 9-17 自身有 721 条任务与 721 条运行，用户最新已明确选择永久删除旧历史、不归档，取代之前的保留安排。
- 旧版实际 `delete_account` 在有历史引用时使用软删除；`_account_is_available` 要求 enabled 且未软删除。能够退出旧调度而保留历史记录，不必用整库删除实现账号迁移。
- 旧网关 34ed25f 的 disabled 状态更新有独立快速分支，不写回整个账号凭据；`resolve_oauth_credentials` 在校验 active 之前获取刷新锁，可用于关闭入口后的在途刷新屏障。执行者仍须核对部署版本、实际错误类型与凭据最终状态。
- profile 的最后观测 CLI 为 2.1.293；旧服务环境默认配置为 2.1.280，v3 默认 2.1.293。应使用已核对的原 CLI 身份和 v3 当前精确版本来源，不把旧服务默认值当作 profile 的实际版本。

## 消费方

ai-fund 当前 `worker/wrangler.toml` 的原 cc2api 来源仍为 `http://us.flower-cli.com:5674`，第二来源是 v3 的 `http://us.flower-cli.com:18080`。拆除旧服务前要正确退出旧来源；同时核对 NewAPI 等下游渠道是否仍指向旧地址，不猜测已切流。

## 执行约束

- 目前没有停止、删除、迁移或停用任何生产资源，只有只读盘点。
- 先迁移及验收 9-17，退出旧业务引用，再按确认的精确清单退役。
- 不执行全局 prune，不删除共享镜像、其他应用、当前 v3 数据与有效恢复镜像。
- 私有原始脱敏收据：`.deploy/ultra-9-17-inspection-20261102/retirement-inventory.json`；目录 0700、文件 0600，不含 OAuth 密钥。

## 最新授权

用户已确认永久删除、不归档；并明确本组工作自行提交、推送和部署，其他步骤也无需再次确认。该授权不改变迁移验收、精确归属和共享引用检查。
