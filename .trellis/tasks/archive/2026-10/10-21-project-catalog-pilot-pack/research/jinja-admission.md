# Jinja 首批内容与本地原生准入

日期：2026-10-21。所有候选运行均位于正式 account 镜像的隔离容器内，真实模型、OAuth、生产数据、提交与部署操作均为零。本报告只覆盖 Jinja 子模块，整包模拟、页面／API／SQLite 与最终 Git 导出由主任务集成。

## 已制作内容

正式目录为 `project_library/projects/jinja/` 与 `project_library/environments/jinja-py312/`。四场景十二稳定任务：understand 1、consult 3、diagnose 4、plan 2、modify 2。十个非修改任务均 `allowed_paths=[]`；需要可运行示例的咨询任务从回答中抽取唯一完整代码块，在临时业务目录执行，分别改变输入，实际读回输出和文件字节。固定事实 native 只支持业务事实，不能替代语义解释质量。

| 场景 | 任务 | 业务边界 |
| --- | --- | --- |
| JI-S01 | U01、C01、P01 | 理解渲染、HTML／TXT 转义、覆盖与回退方案 |
| JI-S02 | D01、D02、D03 | 请求异常材料／无法提供、缓存与末尾换行的无需改库结论 |
| JI-S03 | D04、M01、M02 | 原版 Mapping 分派诊断及两项累计修复 |
| JI-S04 | C02、P02、C03 | 有界异步排序、静态／动态依赖方案、Path 和文件流兼容 |

M01 与 M02 同场景；M01 无强造 answer 依赖，M02 只声明 M01 的 `code` 依赖。没有绕过 M01 的单独 M02 入口。两修改均 `semantic=true`，私有规则显式允许引用候选实现和公开测试证据；行为通过不能代替“实际交付公开测试”的语义核验。

D01 无 native，避免验证器没有 entry 参数时误用私有复现。`unavailable` 入口冻结明确英文业务记录：原模板、调用、上下文与完整异常确已无法提供。该任务 rubric 不内嵌未披露的特定复现或诊断，必须以实际消费对话为依据；该入口不得激活正常 incident-evidence 披露。正常路径可请求 incident-evidence；无根据的确定断言可先披露 certainty-challenge，再请求实际材料。

任务提示、物料指令、分支条件、rubric 英文；中文页面标题、分类、场景与任务目标；合成中文业务值与原始报错按原样保留。

## 固定来源与离线环境

- 官方上游 `https://github.com/pallets/jinja`，完整提交 `5ef70112a1ff19c05324ff889dd30405b1002044`，BSD-3-Clause。
- 源码由 `git archive --format=tar <commit>` 导出；以 `git ls-tree -r --name-only` 核完整集合，并对每个 `git show <commit>:<path>` 的字节计算 SHA256。107 个 Git blob 全部一致，无链接、环境或参考修复。
- `LICENSE.txt` SHA256 为 `3b49dcee4105eb37bac10faf1be260408fe85d252b8e9df2e0979fc1e094437b`。
- 完整导出清单 `.deploy/project-catalog-pilot-pack/jinja/source-export.json`；seed/library 最终再次逐文件核对相等。固定提交没有 AGENTS.md；先前一次消息误把 `git check-ignore` 对不存在路径的匹配当成文件存在，已实际以 Git 对象纠正，未把该文件加入 seed，主代理已撤回无必要忽略例外。
- Python 精确版本 3.12.15；目标镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1`，RepoDigest `sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216`。实际完整镜像元数据见 `target-image.json`。
- 14 个实际 wheel 全部精确版本及逐制品 SHA 已写 profile：attrs26.1.0、Babel2.18.0、idna3.20、iniconfig2.3.1、MarkupSafe3.0.4、outcome1.3.0.post0、packaging26.3、pluggy1.7.0、Pygments2.21.0、pytest9.1.1、pytest-timeout2.4.0、sniffio1.3.1、sortedcontainers2.4.0、trio0.34.0。
- 业务 30 秒、回归 180 秒，各 512 MiB／PID64，UID1000／network none／只读根及来源／无凭据。上述上限下真实运行成功；没有声称测得精确峰值或模型 CLI 全角色总内存。

## 当前镜像完整原生合同

实际重新收集并执行后冻结 911 个节点，911 通过、零 skip／xfail／失败，约 3.591 秒；不是引用历史 911 计数。插件 pytest9.1.1、pytest-timeout2.4.0；Babel 和 trio 真实可用。候选实际导入 `src/jinja2/__init__.py`，模块名保持 `jinja2`。

合同正式副本 `verification/native-contract.json`；原始证据 `calibration/native-contract.json`、`calibration/frozen/{summary.json,junit.xml,pytest-master.json,stdout.log,stderr.log}`。冻结命令由 `calibration-command.log` 配套容器参数记录，核心入口为：

```text
/work/python/bin/python -I -B /verification/native_regression.py --project jinja --baseline-root /baseline --freeze-baseline-contract /evidence/native-contract.json --evidence-dir /evidence/frozen --timeout-sec 120
```

共享 runner 副本最终 SHA256 `a8fdc4721655636c354fc94fedde09290924da01f618fbdabf53b53758a57bdb`，与主模块逐字节相同。初次 Jinja 校准后共享模块只改 TinyDB 另一 suite 的插件配置，主代理明确无需重跑未改变的 Jinja 集合；最终副本已经同步。

## 业务、参考与反例结果

所有下列结果都通过真实产品 `ProjectVerifier.verify_native` 执行，不在宿主导入候选。隔离驱动 `.deploy/project-catalog-pilot-pack/jinja/validate_native.py`，原始结果 `native-results.json`、`native-validation.log`。

- 九个非修改 native 正常通过：U01、C01、P01、D02、D03、D04、C02、P02、C03。C01 两组标题、C02 三组（含重复和空输入）、C03 两组 UTF-8 内容实际执行示例。
- M01 原版真实失败；仅 M01 参考通过业务，冻结完整上游 911／911 通过。
- M02 原版真实失败；累计 M01＋M02 参考通过业务，完整上游 911／911 通过。其业务同时复验 M01 的 Mapping、pair 重复键、字符串路径等能力。
- 主表共 15 次，15 次期望一致；额外两次 M02 负对照也均失败且符合预期：M01-only 仍缺显式 None 修复；完成 M02 却还原 Mapping 分派会被累计能力检查拒绝。证据 `negative-controls.py`、`negative-controls.json`、`negative-controls.log`。
- 参考交付的公开测试在同镜像、相同无网只读隔离中另行实际运行：Mapping1、同步 None1、异步 asyncio／trio2，共 4 节点通过（约 0.18 秒）。证据 `public-tests/{run.py,result.json,junit.xml,output.log}`。此操作独立于冻结原版集合，不能用候选新测试替代原版节点。

业务 runner SHA256 `65c41d87bebc9bbec59c2243a3450decfb806d14e1a439fa76482ad3a63fd4e9`，与已运行产品冻结副本相同。私有参考仅 `.deploy/project-catalog-pilot-pack/jinja/{m01,m02,m01.patch,m02.patch}`，不进入正式 seed、材料或模型初始输入。

## 静态与交接

- schema、环境制品 hash、全部 rubric 引用已真实校验；最终 `scripts/validate-project-library.py --root project_library` 实读 6 项目／26 场景／57 任务。该计数只证明静态内容，不替代整包模拟或上线。
- 模拟输入 `recipes.json` 有十二项英文回答及写入，M02 为累计版本；D01 的 `request_context` 使用真实 incident-evidence 片段。`recipe_overrides.json` 的 `JI-S02:unavailable -> JI-D01` 是材料无法提供回答。`challenge-recipe.json` 另有两次真实物料消费队列：certainty-challenge 后撤回无根据的确定断言，再请求 incident-evidence；末答仍按正常完整证据诊断。它们只供隔离 mock，不能计真实模型语义质量。
- 正式内容于交接时已稳定，不再修改；后续只可增加本子模块 `.deploy` 与本研究摘要证据。整包 mock 的材料消费、代码父链、语义协议、UI／API／SQLite、Git 全集和 Docker 构建上下文由主会话继续。
- 未完成且不冒称通过：真实模型回答质量／评分可靠性／token 成本，最终整包模拟与生产部署。本子模块没有自动提交或发布。
