# schedule 内容制作与原生准入

本报告只覆盖首批子任务中的 schedule；不替代主会话整包模拟、Check-All 或生产部署。证据根为 `.deploy/project-catalog-pilot-pack/schedule/`，本次真实模型、OAuth、生产写操作均为零。

## 实际内容

- 正式 `project_library/projects/schedule/` 包含固定上游 `dbader/schedule@82a43db1b938d8fdf60103bd41f329e06c8d3651` 的完整 32 个 Git 跟踪文件，166,428 字节；逐个 `git cat-file blob` 导出并保留文件模式，无 Git 目录、虚拟环境、临时结果或参考修复。证据 `source-export.json` 含完整原始 Git blob、SHA256、大小与模式。
- MIT 原始 `LICENSE.txt` SHA256 为 `30a8352c318ce1b645acde0299697342d4380ed2637d7ca18a8ad25661e3b41b`。seed 摘要 `8dd7615bcf48a05cc7f71d9b856eb76ce05e8531c4c41974863a2038ad6665c6`，包含两个原始缺陷，未预先修复。
- 实际五场景十三任务：理解二、咨询三、诊断四、方案二、修改二。十一项非修改任务的 `allowed_paths=[]`。两修改仅授权 `library/schedule/__init__.py` 与 `library/test_schedule.py`，均声明 `evaluation.semantic=true`，公开测试判定项显式允许候选文件证据。
- SC-M01 只依同场景 SC-D04 的 answer；SC-M02 只依同场景 SC-U02 的 answer。两个场景从独立原版工作区开始，参考候选没有带入另一场景的修改。
- 英文首问、业务说明、分支、rubric；中文项目／场景标题、goal、简介。原创代码注释与 docstring 为中文，完整上游原文保留。

## 材料与语义边界

SC-D03 初始只有症状；唯一披露分支 `complete-incident` 一次提供真实冻结 `callback.py`、`driver.py`、完整实测 traceback 和业务说明。该分支先请求材料，再解释合成业务 ValueError 的默认传播。未把隐藏复现作为通用 source_evidence 注入初始评审，也未给它挂载泄露根因的通用 native；独立复现事实只在专门校准记录中保存。

其余十二任务有独立 native，非修改任务的程序见证只证明事实与方案可行性，回答本身仍须语义评审。SC-D01、SC-D02 接受设计行为无需修改，SC-C02、SC-C03 接受现有公开 API。方案没有假造固定节奏、持久化或异常策略 API。

`diagnose_only` 入口仅选择 SC-D03 子集，不改变材料或合法结论；没有额外改变输入材料的非默认入口。默认 SC-D03 路径已覆盖所需披露，冻结 `recipes.json` 提供 `request_context`。`recipe_overrides.json` 为 `{}`。

## 当前镜像实际校准

目标为 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1`，主会话核定 RepoDigest `sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216`。本次容器实际读取 Python `3.12.15`，依赖精确锁定 pytest 9.1.1、pytz 2026.5、iniconfig 2.3.1、packaging 26.3、pluggy 1.7.0、Pygments 2.21.0；六个实际 wheel 及逐文件 SHA 已写入 `schedule-py312/profile/profile.json`。

`calibration-01/command.json`、`container-inspect.json` 证明实际 UID1000、network none、只读根／来源、cap-drop ALL、no-new-privileges、内存／swap同为256MiB、PID64。只读 bind 不含账号 HOME、凭据或 Docker socket。假时钟和 sleep spy 只在隔离观察子进程替换 schedule 引用，不接触平台 driver、timeout、预算或数据库。

- 原版完整适用上游集合实际重新收集并执行：**81 passed，0 skipped/failed/error**，wrapper 实测约 0.972 秒。冻结非空逐节点合同已写 `verification/native-contract.json`，不是沿用历史计数。
- 两独立参考各 **81/81** 冻结上游回归通过，逐节点与当前合同相同，候选导入位置由受控 wrapper 核对。
- 十项挂载 native 的非修改任务事实／可行性见证全部匹配预期；总共十二挂载 native 的任务中，两修改在原版按预期不通过，在各自参考全项通过。独立 SC-D03 实测为 ValueError、仅 failed_job，健康对照正常执行两个回调。
- 参考候选公开测试集合：SC-M01 **85 passed**，SC-M02 **83 passed**。把这两套公开新测试放回原版实现，分别 **3 failed / 82 passed**、**1 failed / 82 passed**，证明新增断言确实发现原始缺陷。原始失败输出完整保存，没有将其计入业务任务数。
- 校准子进程业务观测约 0.22～0.35 秒、峰值 RSS 约 28MiB；上游回归子进程约 52MiB。整个校准容器 `memory.peak=103157760` 字节，无 OOM。业务30秒／回归90秒为分别声明的保守运行上限，未增加账号资源。

可信 runner 最终副本与当前 `orchestrator/project_native_regression.py` 字节相同，SHA256 为 `a8fdc4721655636c354fc94fedde09290924da01f618fbdabf53b53758a57bdb`。另一 suite 的独立配置更新没有改变 schedule 校准合同。

## 正式适配器与反例

产品入口实跑记录位于 `formal-native/commands.json`，四条均退出零并满足预期：

```bash
.deploy/project-iteration-repairs/venv/bin/python scripts/validate-project-scenarios.py --root project_library --project schedule --task SC-M01 --image ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1 --expect failed --output .deploy/project-catalog-pilot-pack/schedule/formal-native/SC-M01-original.json
.deploy/project-iteration-repairs/venv/bin/python scripts/validate-project-scenarios.py --root project_library --project schedule --task SC-M01 --image ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1 --candidate .deploy/project-catalog-pilot-pack/schedule/references/SC-M01 --with-regression --output .deploy/project-catalog-pilot-pack/schedule/formal-native/SC-M01-reference.json
```

SC-M02 按同等实参独立执行。原版结果均 `failed`；参考结果均 `passed`，包含真实产品 `ProjectVerifier.verify_native` 业务与完整回归。

`negative-01/` 又实跑四个私有伪修复，全部被真实业务断言拒绝：完全省略延迟、遍历动态 jobs 列表、repr 隐式补 seconds 单位、repr 一律返回 str。分别验证延迟、任务快照、状态不变和已配置格式兼容约束。全部原始命令、stdout/stderr、返回码和 inspect 已保存。

## 静态与交接

已直接运行真实 `validate_scenario_project`、`validate_environment`、所有 `load_rubric/source_evidence`；schema、所有证据路径／行范围、六 wheel SHA、原版 seed 摘要、五场景十三任务、非修改空授权均通过。正式四次原生入口还实际安装并读取了当前六项目 catalog。

13 项模拟 recipes、两个独立 patch 与完整候选只保存在隔离 `.deploy`；不进入正式 seed 或公开材料。默认13项、披露后的输入消费、真实评审协议及 UI/API/SQLite 对账由主会话整包模拟负责。真实模型回答质量、评分可靠性、token 成本、Git 提交和部署均不在本子模块的已完成结论内。
