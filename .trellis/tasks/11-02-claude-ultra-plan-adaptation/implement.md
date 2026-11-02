# 实施计划

- [x] 规划评审后启动此子任务，经 trellis-route 进入 inline；写代码前按 trellis-before-dev 加载相关层规范。
- [x] 贯通真实分级字段与双数据库存储、管理接口、设备画像、profile 同步及重授权幂等；补充跨层场景测试。
- [x] 统一 Rust 分级改写选择，完善 v3 与 ai-fund 展示及可选 5h 状态。
- [x] 实现旧来源明确停用能力，验证零请求及第二来源稳定身份。
- [x] 运行 cargo fmt --check、cargo test --locked；相关 Python test_login_reauth/test_credential_publication/test_account_runtime；cc2api/web npm run build；ai-fund worker 的 pools 测试与前端 pools-sources 组件测试和 build。
- [x] 完成 Check-All、Spec 与提交推送流程，保护当前无关脏文件；不因其他窗口的文档/skill 改动扩大提交范围。
- [x] 同批发布并部署 v3，按 SOP 发布 ai-fund 主版；只读验证新字段、页面、鉴权与数据库；记录新批次。

发布失败保持旧健康服务和真实完成事实；旧来源开关本任务只增加能力，迁移成功前不主动退出正在使用的旧源。

## 当前交付证据

- Rust 全量 814 项通过，4 项显式隔离环境测试默认跳过；本次 PostgreSQL 套餐存储合同已另建临时库执行通过。
- Python 162 项、ai-fund pools 64 项、页面组件 20 项、真实 Workers 1 项、v3 显示函数 2 项和两前端构建通过。
- 三仓业务变更均已推送；ai-fund 主版 Worker/Pages 已部署，公网资源及未授权401核对通过。
- v3 CI 41481059370 成功，生产已部署 `ci-41481059370-1`，页面/鉴权/双库/持久身份/非目标容器验收通过；私有操作目录 `.deploy/v3-ultra-ci-41481059370-1`。

- 旧 v3 镜像定向回收已完成核对，本次无合格候选；当前批次、两个完整历史批次及全部容器引用保持。
