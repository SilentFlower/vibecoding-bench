# 实施计划

1. 读取平台、编排、前端规范和真实DTO、鉴权桥，核对运行时版本文件的唯一生成与读取位置。
2. 定义管理API与TypeScript响应，补齐网关精确GET白名单，新增固定文件读取、原鉴权及旧端回退测试。
3. 更新两个展示入口和卸载收口；移除构建环境版本输入。
4. 调整manage快照、Dockerfile末端COPY、Docker上下文精确白名单及Cargo源码键，增加版本文件/缓存边界回归。
5. 运行orchestrator定向测试、platform版本/缓存/工作流测试、Vue生产构建及相关浏览器验证。
6. 使用真实Docker两版本对照证明frontend/backend缓存复用，记录环境和最终文件版本；不将一次冷构建写成稳定收益。
7. Check-All、Update-Spec、精确Push；集成兄弟任务的四路配置，复用已通过证据。

## CHK-001 修复

首页摘要刷新先共享既有管理会话签发，再并发读取版本、更新状态和运行摘要。浏览器夹具按实际会话顺序拒绝提前读取，覆盖首次登录、延迟签发、签发失败及签发期间卸载；两个展示入口和旧端回退继续回归。

## 验证入口

- `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_system_platform_version test_system_build_cache test_system_workflow`
- `npm --prefix apps/web run build`
- `.venv/bin/python deploy/flower2api/verify_dashboard_update.py`
- `.venv/bin/python deploy/flower2api/verify_runtime_platform_version.py`
- `.venv/bin/python deploy/flower2api/verify_management_ui.py --output <隔离目录>`
- `.venv/bin/python deploy/flower2api/verify_system_update_browser.py --output <隔离目录>`
- `cd services/gateway && cargo fmt --check && cargo test --locked`：新只读白名单和既有管理桥回归。

## 回退边界

代码及构建配方按本次业务提交整体回退，控制镜像沿既有已签发行回退流程恢复。旧控制端缺少新接口时，页面按current_release精确匹配目录展示；版本文件读取没有数据库写入。
