# 实施与验证计划

## 开始前

- [x] 完成三件套收敛与 Brief，取得有效批准或后台领取和 started 回执。
- [x] 激活任务并进入 implement route，载入实际接口和相关规范。
- [x] 复核 `7625142c`、分支归属、当前远端与已有工作区，确定本轮精确范围。

## 顺序

1. [x] 为现有 XZ 处理产物实现本地导出、双层身份校验和有界解码准备入口，准备可评审的附件与清单。
2. [x] 将自有处理产物准备步骤接入 v3-build 与 v3-release 完整构建路径，复用固定缓存和本仓版本化附件；保持只读权限及候选复用顺序。
3. [x] 补齐 Dockerfile 专属白名单，验证执行体和 AGY 包资源确实进入上下文。
4. [x] 补齐候选/正式发布能力门禁和清单到真实镜像标签的一致性检查，保留历史读取与本地可选构建。
5. [x] 扩展探针为实际镜像内模式，接入构建、候选复用和发布的适当位置。
6. [x] 完成定向与真实 Docker 验证，记录命令、退出码、身份摘要、失败恢复及实际覆盖。
7. [ ] 进入 Check-All → Spec → 精确 Git 与附件发布计划，按确认范围执行后恢复原 v1.19.0 发版预览。

## 验证

- Python 使用 `/root/project/vibecoding-bench/.venv/bin/python`，设置 `PYTHONPATH=services/orchestrator:deploy/flower2api`。
- 准备器用合成 HTTP/XZ 测试正常、缓存复用、长度/摘要失配、截断、尾随或拼接流、超预算、中断及原子交付；以现有已处理 `agy.xz` 完成实际导出、解码和身份复验。
- 附件检查只接受预定压缩文件和有界清单；记录本地与远端的文件名、大小及摘要。附件发布动作在精确计划确认后执行。
- 构建上下文用真实 Docker/BuildKit 最小夹具验证必要文件 COPY 与包导入；避免只断言忽略文件中的字符串存在。
- 运行部署目录完整 unittest discover，涵盖 publication、candidate、workflow、release、manage 与宿主隔离导入。
- 受影响编排验证 `test_agy_auth`、`test_agy_environment`、AGY 监督器/资源身份相关用例；定义扫描确认两库版本保持 bench5/gateway6。
- 实际镜像探针覆盖两代准备、共享映像及正常/异常退出。正式镜像的完整 CI 构建与候选验收按实际运行记录核对，代码推送和正式发行各自经过原确认点。
- 外部模型调用为 0，使用隔离状态、合成凭据及断网容器。

## 恢复

- 新制品只在临时或缓存目录产生；失败保护已验证输入。
- 正式发布失败保留源码、run/attempt 与已完成事实，按原 SOP 恢复，禁止覆盖既有发行标签。
- 产品范围、新权限、费用或真实环境边界变化先同步规划并取得相应决定。

## 本地验证结果

- `PYTHONPATH=services/orchestrator:deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python -m unittest discover -s deploy/flower2api`：退出码 0，287 项，1 项跳过。日志为 `.trellis/.runtime/agy-ci-artifact/deploy-final.log`。
- `-m unittest test_agy_artifact test_agy_images test_system_workflow test_agy_auth test_agy_environment test_agy_supervisor -v`：退出码 0，47 项通过，日志 `affected.log`。
- CHK-001 修复后 `-m unittest test_system_workflow test_agy_images -v`：退出码 0，10 项通过，日志 `repair-focused.log`。两个 YAML 的全部 run 步骤通过 `bash -n`。
- `python3 deploy/flower2api/verify_database_definitions.py`：通过，bench5/gateway6。`git diff --check` 通过。
- 现有 XZ 经 `agy_artifact.py export` 和 `prepare --source` 实际核验，附件位于 gitignored runtime 的 `export/`；双层身份与研究记录一致。
- `research/verify_docker_package.py --binary <已核验执行体> --output <隔离证据目录>`：退出码 0，真实旧白名单 COPY 失败；当前白名单与源码构建的隔离 control/account 镜像通过模块、资源和正常/异常退出验收。
- 以实际 v3-build YAML 中的 sudo 验收命令和同一虚拟环境解释器重跑隔离镜像，退出码 0；正常/异常结果均为 `package_source=image`、`terminated=true`、两代凭据、单次解码与零模型。日志 `repair-image.log`。
- 本地镜像为隔离夹具。正式完整镜像验收在本仓附件交付、修复推送后的 CI 记录中核对。v1.19.0 按新远端源码重新预览，生产安装保持独立授权边界。
