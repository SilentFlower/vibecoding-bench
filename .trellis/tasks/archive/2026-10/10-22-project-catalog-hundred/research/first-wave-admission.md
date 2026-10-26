# 第一阶段起始四项目规划依据

本文件记录第一阶段三十仓中起始四仓的已读研究与当前产品代码准入差异，不是整个阶段仅交付四仓，也不是新增原生校准或内容就绪证明。

| 项目 | 固定提交 | 研究阶段真实业务与原生结果 | 当前需复核事项 |
| --- | --- | --- | --- |
| cachetools | `6f23e2a7b75a42d30cb9d890ab3ca4059ee01bfd` | TTL文件缓存命中及过期；366主项、8子测试 | src包、计时与条件路径、主项与子项分别冻结 |
| xmltodict | `6e29fba282e68631034dd2722a413b4e35276584` | 订单XML、流式回调、独立XML往返；134通过 | 单文件候选绑定；可选defusedexpat示例与适用tests分列；正常限制不冒称缺陷 |
| tabulate | `268615a5c27dc40e5c22454c07b44d5c50410da0` | 中文商品表、真实CLI输出；366通过、17跳过 | SCM版本、CLI实际导入、doctest、可选依赖、宽字符模式 |
| python-decouple | `0573e6f96637f08fb4cb85e0552f0622d36827d4` | 合成配置优先级、类型转换、Csv与仓库行为；67通过 | 单文件、mock与旧pytest要求、临时检出存在性、隔离配置发现 |

四份报告记录MIT许可，实际准入仍核固定源码与许可证。选择依据是已有实测成本较小、无需外部业务服务和领域有差异，不据此推断当前镜像已经通过。

## 已发现差异

- `ProjectLibrary` 已支持schema2，旧报告“仅app.py”不是当前限制。
- 可信回归当前 `SUITES` 只有十仓，`_suite_paths` 验证包目录与模块名一致；xmltodict、decouple为 `.py` 模块，不能直接套用包目录注册。
- cachetools的366主项和8子项与JUnit374属于不同汇总层，不能重复相加；已有子测试能力仍须针对本仓校准。
- tabulate报告／路线为5修复、15增强，历史 `progress.json` 仍为0修复、20增强。本批按实际源码与原始证据判断，不修改研究快照，也不据分类数字生成正式任务。
- python-decouple历史源码在可清理的 `/tmp`，须核存在性和commit，必要时按固定来源重建；只使用合成配置。

## 任务设计与依据

围绕缓存、订单XML、业务表格、配置来源定义独立问题。二十步路线只作候选，区分已有能力、正常限制、缺陷与可选增强；读取实际相关实现后冻结场景矩阵、材料、授权、正反验收与真实依赖，不预承诺固定数量或新公共API。

已完整读取四仓单仓报告，读取相关路线起始章节核候选方向；全部二十项尚不等于本批确定目标。平台依据是 `project_library.py` 的 `ProjectDefinition`／`ProjectLibrary`、实际场景manifest校验，以及 `project_native_regression.py` 的 `SUITES`／`_suite_paths`／`_subtest_results`。上一批交付依据为 `.trellis/tasks/10-22-project-catalog-second-pack/` 的三件套及 `research/integration-report.md`。
