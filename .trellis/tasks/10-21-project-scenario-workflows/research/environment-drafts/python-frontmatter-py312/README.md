# Research: python-frontmatter 离线环境与目标镜像实测

- Query: 为四场景六任务准备完整冻结测试环境，并在指定账号镜像验证原版、正常业务和参考修复的可达验收。
- Scope: internal；固定版本 wheel 下载与本地无网络 Docker 取证，不调用模型。
- Date: 2026-10-21

## Findings

### 环境与制品

- `profile/profile.json` 使用实际 `validate_environment()` 格式，已通过该入口；8 个真实 wheel 位于 `artifacts/`，各自 SHA-256、字节数和冻结安装清单齐备，共 2,652,957 字节。
- 完整冻结环境：PyYAML 6.0.3、pytest 9.1.1、toml 0.10.2、pyaml 26.7.0、iniconfig 2.3.1、packaging 26.3、pluggy 1.7.0、Pygments 2.21.0。来源为既有成功环境，下载未查询或选择最新版。
- 目标镜像 `vibebench-v3-account:v3-project-repairs-local-20261021-e`，实际 image ID `sha256:d055c5f0035c8fb3f204ed97d6f774a38afdb3515f5503f7fa028adb6a5e908d`。容器内实际 Python 3.12.15、Linux x86_64／glibc 2.36、UID／GID 1000。
- 容器无网络、只读根、cap_drop ALL、no-new-privileges，512 MiB RAM／总内存上限、PID 64；`/work` 与 `/tmp` 为专属 tmpfs。源码和输入只读挂载，无账号 HOME、凭据或 Docker socket。实际配置见 `evidence/container.json`。
- 新建 venv 2.439 秒，`pip --no-index --find-links=/offline/artifacts --no-deps` 离线安装 1.572 秒；`install-report.json` 中实际 8 个发行包名称／版本与冻结清单精确一致。

### 原生覆盖与正常业务

| 验证对象 | 实际结果 | 完整进程耗时／峰值 RSS |
| --- | --- | --- |
| 原版完整原生集合 | 67 通过，0 失败／错误／跳过 | 0.583 秒／33,864 KiB |
| 参考补丁后完整原生集合 | 67 通过，0 失败／错误／跳过 | 0.580 秒／33,984 KiB |
| 原版既有业务观察 | 中文周报实际写入／读回相等；20 项原版观察落盘，退出 0 | 0.119 秒 |
| 咨询参考程序 | 原周报及第二份隐藏业务输入均满足，唯一可执行程序，原输入字节保持 | 0.222 秒 |
| 浅覆盖正常行为 | 整个 settings 浅覆盖，正文正确，原 defaults 对象内容保持 | 0.119 秒 |
| 原版修复目标 | 预期不满足，保留键等 8 项实际 TypeError | 0.119 秒 |
| 参考补丁修复目标 | 11 项独立行为全部满足，实际加载临时修复库 | 0.120 秒 |

两次完整原生集合均实际执行 `pytest . --doctest-modules --doctest-glob README.md`；插件记录实际 67 个节点及每项报告，其中 11 个真实 `DoctestItem` 与旧严格补充集合精确相等。JUnit 无 failure／error／skipped，67 个 call 报告全部 passed，节点集合与旧 56＋11 完整并集精确一致。没有用忽略 doctest 返回值的包装器代替严格断言，也没有减少适用集合。

`reference/repair.patch` 在容器内先校验前像唯一，并重建 unified diff 与冻结补丁逐字比较后，仅作用于 `/work/repaired/library`。原始 seed 和实际取证源码都未改。参考修复不是模型产物，不计模型任务通过。

### 资源与精确清理

本次单容器从启动至全部退出约 6.884 秒。cgroup 实际 `memory.peak=110333952` 字节，约 105.22 MiB，包含安装、临时 venv／源码 tmpfs 和运行；`pids.peak=6`，实际内存上限 536,870,912 字节、pids.max 64。该峰值与单个原生进程 rusage RSS 分开记录，不把两者混称。

profile 的业务与回归各 180 秒／512 MiB／64 PID 是已在本次限制下运行的保守资源上限，不声称最优预算或多项目并发容量。没有其他镜像、平台或低内存配置的通过证据。

只创建容器 `bench-scenario-research-fm-aa59e2fd38dd`，ID `082c97cef7ac7cbe0db4b3943b2f6d4aed63c5395ae2b7cbb062c35dcf5df75e`。退出后核对本次唯一标签和精确 ID 并移除，再确认 NotFound；`evidence/cleanup.json` 已保存。没有操作任何既有账号或兄弟容器。

### 复建与证据入口

- `prepare.py`、`requirements-frozen.txt`：精确下载命令；`evidence/download.log`／`download-result.json` 保留原始输出、退出码与耗时。
- `run_target.py`：本次 Docker 创建、资源、只读挂载和精确清理；使用既有带 Docker SDK 的控制 Python 执行。再次运行需先另存本轮证据，不能覆盖后混称原始当轮。
- `input/measure.py`：每个真实命令单独记录 elapsed／exit／子进程 rusage RSS；`input/pytest_runner.py` 保存真实节点类型及逐项结果。
- `evidence/*-process.json`／`*.log`、`*-tests.xml`、`*-collection.json`：命令、cwd、环境、退出码、完整原生结果和业务 JSON。
- `audit_results.py` 和 `evidence/completion-audit.json`：独立核对原始 XML、11 个严格 doctest、原生节点并集、业务预期、wheel SHA、安装版本、镜像资源及清理。
- `evidence/evidence-sha256.json`：本轮正式 profile、制品、脚本与原始证据摘要索引。研究下载缓存和临时下载目录不属于正式环境制品，集成时只采用 profile 声明制品并保留取证来源。

## Caveats / Not Found

- 本结果证明指定环境和参考验收的可达性，不证明同模型评审质量、真实模型解决率或成本，也不表示已正式接入／部署。
- FM-DG-02 的任意回答局部合并片段仍由语义 rubric 核查；当前浅覆盖原生观察未声称运行了任意模型片段。其余未物化的模型分支也不能借本次参考程序通过填充模型完成数。
- 仅写本任务 research，下载固定制品并精确创建／清理本次容器；未修改产品、规范、正式 catalog 或上游源码，未执行 Git 或模型调用。
