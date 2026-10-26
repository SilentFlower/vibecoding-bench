# TinyDB 首批内容包准入记录

记录日期：2026-10-21。实现范围仅本仓 `project_library/projects/tinydb/`、`project_library/environments/tinydb-py312/` 及本记录；共享回归和整包集成由主会话负责。正式内容已在 **14:34:31 UTC** 冻结，此后本实现者未再写正式目录。本记录不表示整包模拟、真实模型或生产部署完成。

## 固定来源和完整字节

- 上游：<https://github.com/msiemens/tinydb>，固定 `edff96aeb2616402e9489d46e90a592c05565621`，版本 4.9.0。
- 从真实 `git archive` 导出完整 65 个普通文件、597,655 字节，逐一与 `git cat-file blob` 比较通过；未复制 `.git`、环境或旧日志。完整 blob／SHA 清单见同目录 `tinydb-upstream-files.json`。
- 保留主 MIT LICENSE 全文及嵌入文档主题的完整许可证。主许可 SHA256 `b0e2a2d39271e3d96b717d7be8235ac413d74797bf7f742f0801cfaad6c8c912`。
- 原版 seed 未修复任何目标；控制端参考补丁、答案、候选和配方全部在忽略目录 `.deploy/project-catalog-pilot-pack/tinydb/`，不进入 seed、材料或候选模型输入。
- seed digest：`d478acdf6f6cf1c05645ad6ec2ceadd0a83d76755a2df6c34689e4bcae52cac7`。
- 项目内容树 digest：`d20683a7a731a32fdd5f655d15cef15190e5b6c2363e9ca81f9fc174d6a95d2f`。
- `verification/native_regression.py` 与主会话共享实现逐字节一致，SHA256 `a8fdc4721655636c354fc94fedde09290924da01f618fbdabf53b53758a57bdb`；旧三仓脚本未修改。
- 当前回归 contract SHA256：`94ec92e28eb970039c1ef617a47fd56d9e9944b7a5a952460de92267d535cd94`。

## 实际内容

| 场景 | 任务 | 业务边界 |
| --- | --- | --- |
| TD-S01 单机订单小工具接入 | U01、C01、C02 | 解释库与持久化边界、拒绝不适合的多进程 ACID 预期、可执行现有 API 用法 |
| TD-S02 查询结果不一致分诊 | D01、D02、M01 | 材料请求／无法提供、共享缓存正常约定、fragment 完整路径缓存身份修复 |
| TD-S03 批量促销规则一致性 | U02、D03、M02 | 顺序／重复 ID 正常语义、一次性有限规则耗尽诊断和修复 |
| TD-S04 落盘预期、导入和可靠性方案 | C03、P01、P02 | 缓冲正常时点、先明确 SKU 冲突规则再规划、备份恢复与现有非原子写边界 |

合计四场景、十二稳定任务：understand 2、consult 3、diagnose 3、plan 2、modify 2。十项非修改任务全部 `allowed_paths=[]`，不接受源码检查点。两项修改各自独立场景和独立原版候选；没有跨场景 code 依赖。默认清单在同一问题上先诊断再修改，modify_direct 入口自带完整复现且 `requires=[]`。

首问、业务材料说明、分支和 rubric 英文，页面字段中文；代码例中的原创文档注释依项目约定中文，原上游字节未翻译。十二份 rubric 使用事实／约束判定，允许简洁或等价回答，不做关键词／篇幅匹配。两项修改显式 `semantic=true`，测试交付与授权范围判定允许引用实际 candidate_files；独立行为通过不代替公开测试交付的语义检查。

## 入口与披露

- TD-D01 的正常路径请求证据后投放完整 caller 与 JSONStorage／clear-cache／reopen 观察；不把症状直接判为库缺陷。
- `TD-S02:unavailable` 入口有明确英文业务记录：caller、配置、原文件和完整观测已丢失，不能继续提供；只选 TD-D01，合法终点为 insufficient_information。其分支规则明确禁止披露正常复现；通用评审证据只含原版 search 契约，没有私有 caller／正常复现。
- TD-P01 请求重复 SKU 规则后投放固定业务决定，继续同一任务；披露不是新任务或新尝试。
- mock 主会话须覆盖的实际物料变化路径是 `TD-S02:unavailable`，以及 D01 的 caller-evidence、P01 的 duplicate-policy 两个正常披露。两场景 modify_direct 的源码起点应独立验证。consult_only／diagnose_only 只改变选集，没有额外材料内容。

## 当前镜像和真实原生结果

本轮镜像：`ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1`，RepoDigest `sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216`。实际 Python **3.12.15**，Linux amd64。离线 profile 含八份真实 wheel、2,890,590 字节：coverage 7.16.2、iniconfig 2.3.1、packaging 26.3、pluggy 1.7.0、Pygments 2.21.0、pytest 9.1.1、pytest-cov 7.1.0、PyYAML 6.0.3；逐份 SHA 已冻结。不存在安装 TinyDB wheel 以替代候选导入的路径。

所有以下执行都在目标镜像、UID1000、network none、只读根、只读 candidate/baseline/control/offline 挂载、256 MiB／PID64 下完成，没有账户 HOME、凭据或 socket。business 30 秒和 regression 90 秒分别固定，准备时间单独处理。

| 核验 | 实际结果 | 原始证据（相对 `.deploy/project-catalog-pilot-pack/tinydb/`） |
| --- | --- | --- |
| 当前原版完整回归重新校准 | 228 passed，0 skip/error/fail，2.478 秒 wrapper；导入冻结原版 | `calibration-2/run/summary.json`、`junit.xml`、`native-contract.json` |
| TD-M01 原版独立业务 | expected failed | `native-results/TD-M01-original.json` |
| TD-M02 原版独立业务 | expected failed | `native-results/TD-M02-original.json` |
| TD-D02、D03 原版诊断对照 | 各 passed，真实 billing/shipping 与 list/generator 结果 | `native-results/TD-D02-original.json`、`TD-D03-original.json` |
| TD-C02 唯一完整可执行示例 | passed，实际 JSON 重开读回 A=2/B=2、默认表空、打印查询对象 | `native-results/TD-C02-example.json` |
| TD-M01 独立参考 | business passed，完整 228 passed，逐节点合同相等 | `native-results/TD-M01-reference.json` |
| TD-M02 独立参考 | business passed，完整 228 passed，逐节点合同相等 | `native-results/TD-M02-reference.json` |
| 新增公开回归用例 | M01 原版 1 fail/1 pass、参考 2 pass；M02 原版 2 fail、参考 2 pass | `public-tests/*.xml`、`summary.json` |
| 禁用全部缓存反例 | expected failed | `native-results/TD-M01-disable-cache.json` |
| 去除重复返回 ID 反例 | expected failed | `native-results/TD-M02-deduplicate-ids-corrected.json` |
| 只打印正确答案、两个完整示例反例 | 各 expected failed | `native-results/TD-C02-print-only.json`、`TD-C02-ambiguous.json` |
| 其他问答的合成事实控制 | 16 项观察全 true：默认／具名表、重开、内存、陈旧快照覆盖、共享缓存、真实 update、顺序、flush、写次数、upsert、备份表/ID与下一ID | `business-facts-2.json` |

原版校准准备 4.689 秒、总计 7.460 秒；`children_peak_rss_kib=72404` 包括环境准备和测试，不冒充单独 pytest 峰值。独立问答事实进程 0.240 秒，self／children 峰值均 15,572 KiB。业务与回归各自已在 256 MiB 资源限制实际成功，但这些不是最优资源值，也不代表真实模型答题质量。

完整回归恢复原版测试／配置，以受控 runner 叠加候选实现并证明实际从候选测试树导入；候选自己新增测试不参与冻结原版集合，另外通过公开用例对照与语义交付检查。两个参考分别从原版起点执行，M02 没有继承 M01 修复。完整节点数是本轮重新收集所得，未把历史 228 当本轮证据。

## 重跑入口与 mock 交接

```bash
.deploy/project-iteration-repairs/venv/bin/python .deploy/project-catalog-pilot-pack/tinydb/calibrate-2.py
.deploy/project-iteration-repairs/venv/bin/python .deploy/project-catalog-pilot-pack/tinydb/validate_all.py
.deploy/project-iteration-repairs/venv/bin/python .deploy/project-catalog-pilot-pack/tinydb/check_public_tests.py
.deploy/project-iteration-repairs/venv/bin/python .deploy/project-catalog-pilot-pack/tinydb/validate_negative_corrected.py
.deploy/project-iteration-repairs/venv/bin/python .deploy/project-catalog-pilot-pack/tinydb/run_business_facts_2.py
```

校准与公开测试脚本要求输出目录不存在，以保留原始证据；重跑须在新证据目录执行，不覆盖现有合同。`validate_all.py` 内逐条调用既有 `scripts/validate-project-scenarios.py`；测试使用只含该正式项目/环境的字节镜像目录 `test-library/`，其 manifest、native 脚本、contract 和 wheel 对应正式内容，profile 最后仅补了准入说明字段，执行参数及依赖未变。整包最终版本和 digest 由主会话冻结。

- 十二项配方：`.deploy/project-catalog-pilot-pack/tinydb/recipes.json`，key=task ID，包含英文 answer、合法 MOCK_OUTCOME、allowed_paths 和两修改的完整参考 writes。
- 正常材料请求放 request_context，含 branch_id、英文问句和真实披露片段；这两个字段只服务 mock，不进入正式 manifest。
- 无材料替代：`recipe_overrides.json` 为 `{'TD-S02:unavailable': {'TD-D01': <完整recipe>}}`，不带 request_context，合法 insufficient_information。
- 私有参考根：`references/TD-M01/` 和 `references/TD-M02/`；同级 `TD-M01.patch`、`TD-M02.patch` 和 `answers/`；不在源码 seed 内。

## 保留的工具失败及限制

1. `calibration/` 首轮 pytest 配置失败：固定 pytest.ini 有覆盖率参数，但初始共享 suite 禁止 autoload 且未显式加载 pytest-cov，无节点收集。主会话为 TinyDB suite 添加真实显式插件后，另存 calibration-2 通过；没有裁剪 tests、改原版 pytest.ini 或缩减适用集合。
2. 首个去重 ID mutant 错把 Table.update 的相同文本改了，未触及本任务的 update_multiple，因此业务正确通过；该假阴性属于测试构造错误，原目录与结果保留。随后在 update_multiple 定义内精确构造 corrected mutant，独立业务成功拒绝；未修改正式 oracle。
3. 首轮额外 facts 脚本把 disclosure caller 当成 materials 路径，因文件不存在退出；原脚本/log 保留。只修本地取证挂载路径，另存 business-facts-2 后 16 项通过，正式材料和产品未变。
4. 本记录不代表十二项语义质量已验证；模拟协议、UI/API/DB、最终 catalog 字节和历史兼容由主会话整合。真实模型/OAuth调用为零，未提交、推送、发布或部署。
