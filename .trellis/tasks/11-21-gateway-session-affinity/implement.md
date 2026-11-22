# 实施与验证

## 实施顺序

1. 核对当前工作区的反重力工具回填重放、Claude 正文与头对齐，以及账号工作门禁。读取 gateway/backend、web/frontend 和跨层指南的相关合同。
2. 实现共有会话解析与摘要计算。增强合成请求测试，覆盖显式优先级、同锚点跨轮、协议与 Token 隔离、缓存标记、多模态、长输入与无有效首轮。验证客户端可选头的入站和转发边界。
3. 将 Claude V3 接入共享键，以已存键验证升级兼容。抽取现有绑定 CAS 的共同实现，接入反重力普通请求的读、准入及竞争重选。验证数据库双实现、同会话并发、绑定生命周期、暂停/限流语义和未提交候选的资源回收。
4. 在两条入口冻结请求诊断字段，并接入反重力已验证工具关联。扩展 `apps/web/src/api.ts` 和 `RequestDiagnostics.vue` 的同列展示及完整复制。将缓存缺省和历史缺字段作为合成页面场景。
5. 用正常 API 路由与合成发送器串联双账号、两轮请求、持久行、管理 API、页面内容。核对反重力工具回填与重放、Claude 原生和普通转发、管理权限与预期拒绝。随后同步已变更的调度和展示规范。

## 验证入口

- `cd services/gateway && cargo test --locked --test v3_scheduling_test`，覆盖会话并发原子性。以 `CC2API_SCHEDULING_TEST_POSTGRES_DSN` 指向隔离库运行 `cargo test --locked --test v3_scheduling_test postgres_concurrent_binding_and_budget_rollback -- --ignored`。通过合成 HTTP 路由验证 Claude 和反重力的实际提交账号。
- `cd services/gateway && cargo fmt --check && cargo test --locked`，验证共享绑定、诊断持久化、旧 JSON 以及既有进程内工具归属与重放路径。
- `npm --prefix apps/web ci` 与 `npm --prefix apps/web run build`。用 `python3 deploy/flower2api/verify_management_ui.py --output <隔离产物目录>` 验证列表、详情、复制、390px/桌面宽度和旧记录。
- `python3 deploy/flower2api/verify_agy_gemini.py --image <隔离测试镜像>` 走实际 Gateway HTTP、数据库及合成发送器。沿 `verify_agy_native_loopback.py --parallel-tools` 对反重力原生工具回填、同账号归属及重放做回归。使用当前隔离制品和合成凭据。

## 回退与核对

- 回退代码时恢复原选号和原显示方式，既有表与旧 `original_session_id` 数据继续可读。派生绑定与诊断字段按既有期限过期。
- 核对独立进行的工具回填重放任务的实际版本和相关代码范围。诊断数据模型与入口代码改动基于当时工作区，不覆盖相邻在研变更。
