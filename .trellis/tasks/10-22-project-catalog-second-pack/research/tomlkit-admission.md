# TOMLKit 第二批内容包准入记录

## 范围与状态

本仓交付 `project_library/projects/tomlkit/` 与 `environments/tomlkit-py312/`，5 场景／12 个稳定任务：understand 1、consult 3、diagnose 4、plan 2、modify 2。10 个非修改任务授权路径为空；两个修改分别从各自场景原版开始，材料自足、`requires=[]`，没有代码累计。唯一 answer 依赖为 TK-P01 → TK-D02；normal／dialect_plan 两个选择 P01 的入口均包含 D02。

逐仓真实原生准入已通过；整包 review 协议、mock 调度／页面／API／SQLite、历史与导出保真、正式 Check-All 由主会话随后执行。本报告不将它们提前标为通过。真实模型质量、评分可靠性与 token 成本未验证，真实模型及 OAuth 调用为零，未生产部署、未提交或推送。

## 固定真实来源

- 主仓：[python-poetry/tomlkit@eddd27e43a62fe58707c311bfad2f52e72493f53](https://github.com/python-poetry/tomlkit/tree/eddd27e43a62fe58707c311bfad2f52e72493f53)，0.15.2，MIT。完整官方归档与固定 recursive tree API 的 **82 个普通 blob** 逐个 Git SHA1 匹配，缺失／多余／不同均为零。
- 主仓真实 gitlink 指向 [BurntSushi/toml-test@08ed8697864548b3cdb4b8decbf496bef47e1c82](https://github.com/BurntSushi/toml-test/tree/08ed8697864548b3cdb4b8decbf496bef47e1c82)。固定官方归档与其独立 tree API 的 **1,042 个普通 blob** 逐个匹配，缺失／多余／不同均为零；无链接及特殊成员。完整展开到 `seed/library/tests/toml-test/`，没有用空目录替代语料。
- 合计 **1,124 个固定来源普通文件**。主仓 LICENSE SHA256：`f2f9b460ba719da6626add264d3782f275a4ff7aab677beda08b330911e23adb`；子模块 LICENSE SHA256：`01ef58ee6449fa01a284c10808e27800d66bfea271bc29281125ff8e5642b86f`，两份 MIT 归属均原字节保留。gitlink 不计作普通 blob。
- 主仓及展开子模块的逐路径 Git blob／SHA256／大小、归档 SHA、原 gitlink、官方 URL 和全部匹配结果固定在同目录 `tomlkit-admission.json`；原归档／官方树回应位于下述证据根。正式 seed 经最终逐文件复核，与这 1,124 个来源字节完全相同，未预修两个目标，未混入 `.git`、环境、日志或参考答案。

## 场景、材料与合法结果

| 场景 | 稳定任务 | 业务结果 |
| --- | --- | --- |
| TK-S01 配置编辑接入与局部保真 | U01、C01、C02 | 理解文档树与保真边界；运行既有 API 示例安全替换字符串与字面带点键，无需改库 |
| TK-S02 解析失败与方言兼容 | D01、D02、P01 | 先取证诊断；支持明确材料不足；区分 TOML 1.1 与 Python3.12 TOML1.0 消费者，规划兼容发布 |
| TK-S03 数组扩容一致性 | D03、M01 | 独立定位并修复 Array 原位重复的逻辑／片段／索引分歧 |
| TK-S04 inline 点分配置删除 | D04、M02 | 独立定位并修复空 dotted 父表丢失及分隔问题，保护普通 flat 删除原字节 |
| TK-S05 编码扩展与写盘边界 | C03、P02 | 实际执行既有编码器示例并恢复全局规则；规划调用方安全写盘与冲突处理 |

模型首问、业务材料说明、披露条件及 rubric 为英文；页面 title／category／description／goal 为中文。原源码、原始错误及“配置”等业务字面原样保留。未披露的 D01 精确输入／原因不进入通用 rubric 的确定事实，也没有挂到初始 native 结果中。该任务只有语义评审；原生重复键／其他非法文本／合法文本的独立校准证据单独保存，不提前作为候选收到的材料。

全部入口：S01 normal；S02 normal、unavailable（只选 D01 并公开无法提供证据）、dialect_plan（D02＋P01）；S03／S04 各 normal、diagnose_only、modify_direct；S05 normal。D01 的 `parse-reproducer` 仅在实际请求最小必要证据且没有 unavailable 记录时披露；正常追问不拆任务。两个直接修改入口均包含完整公开复现和授权。

## 真实运行环境与完整冻结回归

目标镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1`，实际固定 RepoDigest `sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216`，linux-amd64，Python **3.12.15**。所有候选业务及回归在 UID1000、无网、只读来源／根目录、无账号 HOME／凭据的独立容器中运行；只用归属明确的临时工作树及合成文件。

四个真实 wheel：`pytest==7.4.4`、`iniconfig==2.3.0`、`packaging==25.0`、`pluggy==1.6.0`，逐制品路径／SHA256／字节大小见环境 profile 和 admission JSON。当前套件没有必需额外 pytest plugin；没有安装 PyPI TOMLKit 冒充候选，真实导入均落在受控源码。

业务资源为 30 秒／256 MiB／PID64；完整回归为独立 120 秒／256 MiB／PID64，均在该上限实际运行通过。原版校准离线 venv／安装准备 3.097 秒、完整 runner 3.128 秒、总 6.606 秒；准备与业务时限分开。未测精确峰值，不能将此数字当账号所有角色或模型 CLI 的总资源。

当前镜像实际完整收集并执行 **1,203 passed／0 failed／0 error／0 skipped／0 xfailed**，JUnit 恰有 1,203 testcase；包含固定子模块的 680 个 TOML1.1 语料项。没有删掉语料或将 Python3.12 的 TOML1.0 tomllib 当成 1.1 全量裁判；独立业务样本选 1.0 交集时才使用 tomllib 复核。

冻结合同 SHA256 为 `f8788ecc8448a251cacfe943e91b6aec9b019c761eac36a0f46c74ac1dfd182c`，collection digest 为 `73c01fd0d34e5ce064a7409a9ef3ae334a4af044aabc20bf2502c2a02233d317`。原版使用可信 runner v1 `e36ec55b5bddb08c791fbb3bf376caa0dd250acb424f2597e782d1fd693d45e9` 校准；最终副本同步 v2 `b3e75e056b684fa6d5a6a4871bf8793b8422d373460562110207612c97ba65c3`（只增他仓 Hypothesis 插件），并在最终 v2 上分别再次验证两个参考的完整 1,203 项回归；旧六仓私有脚本未改。

## 独立验收结果

共 **23 个产品真实验证入口案例**全部符合预期（含最后针对顺序／注释补强的三项定向复核）：

- 9 个只读 native 任务真实通过。C01 实跑五类名称／端口输入，C02 实跑三个镜像输入并核字面键／真嵌套控制和缺目标异常，C03 实跑两种 PurePath 与失败输入并核完整 encoder 对象序列恢复，均不只匹配答案关键词。D01 因材料消费边界保留为纯语义任务。
- M01 原版目标失败，独立参考业务通过；覆盖 4 类文档 × 8 类合法计数、非法计数不变、对象及文档绑定、嵌套数组／inline 值 Python 引用语义、后续 append／替换／删除、原有注释及 count-one 精确字节。错误“复制 unwrap 值”修复虽然首次值／文本正常，仍因丢共享引用被拒。
- M02 原版目标失败，独立参考业务通过；独立期望树覆盖空父表首／中／尾／唯一、多级、quoted key、两个子树、已有空表、剩余叶子、先删后加、sibling 顺序及外层注释。保护普通 flat 删除五个精确输出、已有 dotted 插入与显式父键删除。错误“空表改成标量0”修复虽可解析仍被拒。
- 两参考在各自原版场景上通过完整可信上游回归；没有 M01 → M02 代码继承。两仓参考新增公开测试另在无网容器实际运行：M01 两项和 M02 一项在原版均失败、对应参考均通过。
- 三个咨询错误答案（丢 literal 样式、误按 nested 路径修改、未卸载临时 encoder）均由真实示例执行拒绝。

原版目标失败与错误候选是预期负对照，不记录为未修复环境故障。完整精确命令、冻结候选摘要、实际 JSON、stdout／stderr、XML、退出码、资源与清理原样保留。

## 证据与复跑

证据根为 `.deploy/project-catalog-second-pack/tomlkit/`：

- `prepare.py`、`sources.json`、两个官方归档及 `*-tree.json`、`download.log`：固定来源导出与 wheel 下载。
- `calibrate.py`、`calibration-v1/`：完整原版校准、逐节点 contract、pytest 证据、XML、准备／运行资源及清理。
- `references/TK-M01/`、`references/TK-M02/`：互不累计的控制端私有参考；`wrong/` 是负对照，均不在正式 seed。
- `validation-library/`：单仓真实 schema2 内容根，可直接传已有 `scripts/validate-project-scenarios.py`；`validation/commands.jsonl` 是全部精确 CLI 命令，结果保存为对应 JSON／log。
- `public-tests-v1/`：新增公开测试的原版失败／参考通过四次独立执行及 XML。
- `parse-evidence.json`：当前目标镜像真实重复键错误、不同非法字符串与合法单键控制，仅供准入校准。
- `answers/` 与 `mock-response-manifest.json`：后续整包 mock 的英文参考答复，含 D01 请求／正常披露最终／unavailable 最终；不计真实模型完成。
- `cleanup.json`：本仓专用命名容器剩余零；各专用容器清理收据另存，产品验证器也按其正常生命周期移除临时验证容器。未清理他仓、旧证据或未知资源。

典型复跑入口（实际完整参数以 commands.jsonl 为准）：

```bash
.deploy/project-iteration-repairs/venv/bin/python scripts/validate-project-scenarios.py --root .deploy/project-catalog-second-pack/tomlkit/validation-library --project tomlkit --task TK-M01 --candidate .deploy/project-catalog-second-pack/tomlkit/references/TK-M01 --image ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1 --with-regression
```

所有通过断言仍须经主会话整包模拟与正式检查后才形成整个四仓交付；本仓原生准入不替代内容集成、真实模型质量或生产部署。

## 独立来源审计与执行位修正补记

整包集成期间，独立来源审计重新读取四仓共1,375个正式来源文件，逐项重算Git blob SHA1、普通字节SHA256、大小、全集和5份许可；全部字节匹配，无来源缺失／额外文件、实际链接或目标实现预修。TOMLKit单列主仓82项、测试子模块1,042项；后者原始mode由已冻结官方tree回应补核。初始原观察保存在 `.deploy/project-catalog-second-pack/source-audit.json`，未覆盖。

该审计发现唯一原始执行位差异：固定子模块 `gen.py` 在官方tree中mode100755、blob `7d7a282ebd64e14700d6d3141a8215f2a60ab331`、5,530字节；导出后为0644，但双SHA均与原始blob完全一致。这是模式保留问题，不是源码字节不符。主会话随后仅将正式源码副本 `seed/library/tests/toml-test/gen.py` 恢复为0755，未改内容；修正收据为 `source-mode-restoration.json`。再次独立重读全部1,375项并核模式后，普通来源文件mode均与上游一致，五个经明确表示的link blob仍以原目标文本普通0644文件保留，实际链接为零。最终观察另存 `source-audit-final.json`；原始admission JSON来源清单未改写。

脚本用途已经实际读源码核对：`gen.py:161` 起构建Go decoder、展开multi／spec语料并生成1.0／1.1版本列表。TOMLKit的 `tests/test_toml_tests.py` 仅读取已冻结列表和TOML／JSON语料，不执行或import该生成工具，因此无需重复完整原生回归。源码仓已真实保留该执行位；运行副本仍遵守既有 `materialize_snapshot` 统一普通文件0644的契约（`orchestrator/project_library.py:172`），该运行行为未改。源码快照摘要只覆盖路径／字节／大小，本次修正前后catalog摘要均为 `600c930ff5d43986c4d841ee1612c4dbd83a318d7bd706b50666f7f8f116139d`；没有把执行位变化冒充字节变化。
