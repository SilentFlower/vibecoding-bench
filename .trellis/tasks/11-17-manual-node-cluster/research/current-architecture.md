# 当前架构与规划依据

## 用户确认的方向

本会话已确认人工指定执行节点、账号固定归属、统一后台和统一 API 网关。用户已同意启动任务规划，并选择首版接入长期在线、网络可达的 Linux 服务器。

## 仓库证据

- `deploy/flower2api/README.md:7`：管理服务与账号角色分离，每账号包含 network、CLI、sender 三个角色容器。
- `deploy/flower2api/compose.yml:74`：编排容器挂载本地 bench 数据目录与本机 `/var/run/docker.sock`。
- `services/orchestrator/account_runtime.py:132`：`AccountRuntime` 接收一个 Docker 客户端、本地数据根、宿主数据根及数据库回调；作业和环境锁位于当前进程。
- `services/orchestrator/account_runtime.py:1267`：`transport` 通过当前账号环境准备路径返回传输绑定；绑定后凭据发布沿用网关所有权，并从执行副本移除 refresh token。
- `services/orchestrator/main.py:12664`：`GET /internal/v3/transport/{account_id}` 按网关账号找到唯一任务账号，调用当前 `AccountRuntime` 解析或准备发送环境。
- `services/gateway/src/service/runtime_transport.rs:55`：`TransportBinding` 当前含账号、环境、代次、endpoint、服务秘密和发布归属。
- `services/gateway/src/service/runtime_transport.rs:260`：网关向 `V3_RUNTIME_URL` 解析账号传输，再通过 sender 发送请求。
- `services/gateway/src/service/runtime_transport.rs:757`：提交携带请求身份、环境代次和截止预算，保持当前防重放边界。
- `services/gateway/src/service/runtime_transport.rs:844`：传输校验限定部署推导的 Docker DNS 名、HTTP 和 8091 端口；跨机入口需重新设计受信绑定校验。
- `services/orchestrator/database_schema.py:543`：账号环境使用现有 SQLite 表定义；新增节点归属涉及数据库迁移合同。
- `services/orchestrator/main.py:1399`：编排服务创建本地 SQLite 连接。

## 规划需要覆盖的边界

1. 账号节点归属的唯一权威、默认节点升级和迁移代次。
2. 节点执行边界：Docker、环境文件、终端、工程执行、诊断采集及备份。
3. 控制通道与业务流量通道：认证、加密、流式响应、取消、超时和断连收口。
4. 保持全局账号准入与原有凭据刷新所有权；节点接入不复制出第二个刷新所有者。
5. 手动迁移的排空、持久数据校验、切换顺序、旧节点失效及失败恢复。
6. 发布兼容、节点协议能力和多节点升级过程中的安全拒绝。

## 本轮知识发现

已按 `spec_router.py` 返回策略读取账号运行环境的命中章节、代理目录合同及项目状态查询的命中章节。账号凭据所有权、资源真实采样、配置维护门禁与长流超时边界需持续遵守。任务文档检索当前仅命中新建任务。

## 补充耦合证据

- `services/gateway/src/service/runtime_lease.rs`：全局账号 API 活跃计数、CLI 槽位及排他维护在网关集中管理；节点接入需要维持这一权威。
- `services/orchestrator/projects_runtime.py`：`ProjectsTerminal` 继承 `PiTerminal`，直接读取环境行和本地工作区；远程执行需要显式适配终端与工程资产操作。
- `services/orchestrator/project_review_runtime.py`：评审复用账号环境、执行证据与原凭据所有者；迁移排空必须包含评审子容器和未完成刷新请求。
- `services/gateway/src/service/oauth.rs`、`telemetry.rs`：部分后台请求通过账号代理直接发送；跨机方案必须覆盖这些路径，保持中央刷新权及节点出口归属。
- `services/gateway/src/service/runtime_bridge.rs`：浏览器桥有路径/方法白名单及独立 HTTP/SSE/WebSocket 转发边界；节点管理需要增加精确公开路由。
- `apps/web/src/components/runtime/runtimeApi.ts`：环境公开投影已有 `environment_id/generation`，节点归属可作为兼容新增字段，服务秘密继续留在内部。
- `images/v3/control-entrypoint.sh`：管理镜像当前仅有 gateway/orchestrator 角色；执行节点服务需要新增角色入口。
- `images/v3/Dockerfile` 与 `deploy/flower2api/source_layout.py`：两个最终镜像及历史逻辑路径兼容需要同步维护。
- `services/orchestrator/database_migration_contract.py`：迁移步骤有固定版本链与摘要，新增节点结构需追加迁移。

## 技术实施前的验证项

跨机控制接口、节点执行适配和租约传播为新增机制，应先完成一条合成账号纵向链路；失败时修正规划机制，保持已确认的人工分配与统一网关范围。
