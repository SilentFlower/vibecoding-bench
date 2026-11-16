# 构建与发布解耦实施计划

## 顺序

1. 先补实际边界回归：push/PR/未知 ref/仓库/SHA/脏来源拒绝，两个正式分支手动发布通过；冻结原发行格式及旧目录高序号夹具。
2. 拆分 `v3-build.yml` 和新 `v3-release.yml`；收口 `docker-publish.yml` 自动发布入口。保留依赖版本、必要合同测试、构建与正式发布的兼容演练。
3. 同步两个 Python 发布入口的事件/ref/入口/显式发布标记校验；手动发布缺签名配置提前失败。固定宿主源码 SOURCE_FILES 同步直接依赖，并验证仓库外独立导入。
4. 用已验签目录生成持续递增序号，保留版本递增、附件先完整再更新目录、fast-forward 冲突和失败保护。
5. 更新 `deploy/v3/platform-release.json` 的后继补丁版本与说明；同步 `deploy/v3/SYSTEM-UPDATES.md`、`deploy/v3/README.md`、相关规范及旧 main 发布说明。
6. 执行定向验证、检查范围与证据，再交接 Spec/精确 Git 计划。计划中明确 flower2api 提交，以及 v3/main 旧触发规则的同步和手动入口注册步骤；每步按实际授权执行。

## 预期文件

- `.github/workflows/v3-build.yml`、`.github/workflows/v3-release.yml`（新）、`.github/workflows/docker-publish.yml`。
- `deploy/v3/manage.py`、`deploy/v3/publish_system_release.py`、`deploy/v3/install_system_updater.py`；如提取共享来源校验，限 deploy/v3 内小型模块并覆盖实际调用。
- `deploy/v3/test_publication.py`、`deploy/v3/test_system_publish.py`、新增工作流回归测试；按实际序号辅助函数定位补测。
- `deploy/v3/platform-release.json`、`deploy/v3/SYSTEM-UPDATES.md`、`deploy/v3/README.md`、根 README 发布说明及相关 deploy specs。

## 验证计划

- `PYTHONPATH=orchestrator:deploy/v3 .venv/bin/python -m unittest test_publication test_system_publish test_system_release test_system_platform_version test_system_migrations`。先核对实际可用项目解释器，缺少 .venv 时沿已有依赖环境运行并记录实际命令。
- 新工作流回归用实际 YAML 与条件断言验证 push/PR/手动构建零发布、手动正式入口和最小权限；使用 actionlint（可用时）与项目已有 YAML 解析能力，必要工具只作为本地验证依赖。
- `python3 deploy/v3/verify_database_definitions.py`；发行清单、旧目录和数据合同保持兼容。
- `python3 -m compileall` 精确改动 Python 文件，`git diff --check`。
- 在无真实发布的测试边界内验证新旧来源、目录序号、缺签名、上传失败、同 attempt 重复、fast-forward 冲突和旧发行读取。
- 正式工作流必须保留原 Python 3.12 全套系统更新验证、真实旧库兼容演练及摘要绑定；后续 GitHub 手动发布以实际 CI 结果作为安装前证据。

## 检查与边界

- 不用真实发行或生产安装代替本地回归；记录本地验证与实际 CI/安装证据的边界。
- 原 343 个工作区改动及其他任务保持归属；只编辑本任务涉及的代码、规范与任务记录。
- 本轮不启动源码归并、前端迁移和功能精简。
- 源码提交完成不等于旧 v3/main 分支触发规则已生效；以实际合入目标与工作流状态验收后续 Git 步骤。

## 本轮实施与验证证据

- 已拆分只读构建与明确手动发布，保留 v3/flower2api 的实际 SHA、run/attempt 与原发行身份。
- 发布来源回归、真实临时签名与旧目录高序号、v2 首发继承、签名损坏、目录竞争、安全整数上限及固定源码包独立导入均通过。
- `PYTHONPATH=orchestrator:deploy/v3 .venv/bin/python -m unittest discover -s deploy/v3 -p 'test_system*.py'`：84 项通过。
- `PYTHONPATH=orchestrator:deploy/v3 .venv/bin/python -m unittest test_database_definitions test_database_migrations test_database_compatibility test_publication`：26 项通过。
- `.venv/bin/python -m unittest discover -s orchestrator -p 'test_system_update*.py'`：13 项通过。
- `python3 deploy/v3/verify_database_definitions.py`：bench/gateway 均保持登记版本 1。
- `go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 -shellcheck= .github/workflows/v3-build.yml .github/workflows/v3-release.yml .github/workflows/docker-publish.yml`：通过。
- Python 精确改动文件编译、`git diff --check` 通过。原有 343 个文件 SHA256 核对保持一致。
- 后续远端验证：将修复同步到 v3/main、注册手动入口，再在正式发布与管理员原地升级时核对实际 CI/安装结果。
