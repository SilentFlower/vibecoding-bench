# 实施计划

1. 读取平台、编排、前端规范和真实DTO、鉴权桥，核对运行时版本文件的唯一生成与读取位置。
2. 定义管理API与TypeScript响应，新增固定文件读取和旧端回退测试。
3. 更新两个展示入口和卸载收口；移除构建环境版本输入。
4. 调整manage快照、Dockerfile末端COPY及Cargo源码键，增加版本文件/缓存边界回归。
5. 运行orchestrator定向测试、platform版本/缓存/工作流测试、Vue生产构建及相关浏览器验证。
6. 使用真实Docker两版本对照证明frontend/backend缓存复用，记录环境和最终文件版本；不将一次冷构建写成稳定收益。
7. Check-All、Update-Spec、精确Push；集成兄弟任务的四路配置，复用已通过证据。

## 验证入口

- `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_system_platform_version test_system_build_cache test_system_workflow`
- `npm --prefix apps/web run build`
- `.venv/bin/python deploy/flower2api/verify_dashboard_update.py`
- `.venv/bin/python deploy/flower2api/verify_management_ui.py --output <隔离目录>`
