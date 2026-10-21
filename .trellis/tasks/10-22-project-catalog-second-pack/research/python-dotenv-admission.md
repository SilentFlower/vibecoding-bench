# python-dotenv 当前镜像准入实证

本仓正式内容为5场景／12任务：理解2、咨询2、诊断4、方案2、修改2。仅两个修改接受代码；十个非修改不创建代码检查点。当前状态是内容与真实原生验收就绪，整包mock、页面和Git交付由主会话统一处理；真实模型、OAuth和生产操作均为零。

## 来源与字节边界

- 上游 `https://github.com/theskumar/python-dotenv`，完整提交 `0b2880591780a426b0551436f47a17e7a76d954f`，源码版本1.2.4，BSD-3-Clause；根 `seed/library/LICENSE` 原样保留。
- 通过实际 `git ls-tree -r` 和 `git cat-file blob` 导出47个Git blobs，逐项SHA、大小和上游mode见同目录 `python-dotenv-admission.json` 的 `source.files`；所有运行源码和测试均原版，未预修seed。
- 43项上游mode100644；另外4项 `docs/changelog.md`、`docs/contributing.md`、`docs/index.md`、`docs/license.md` 是上游mode120000的文档链接。内容快照禁止实际symlink，故将其**原始link blob目标文本**保存为普通文件，并记录目标及mode，不宣称保留其原文件类型。根完整文档／许可原件仍保留；运行源码和测试没有链接。
- seed摘要为 `7adb719502909d3fd4bdfbec74b9445fb6c735dfd4df52bd559e5f37407439f7`。没有 `.git`、venv、真实.env、账号或参考答案进入seed。

## 场景、入口与材料

| 场景 | 稳定任务 | 入口 |
| --- | --- | --- |
| DE-S01 接入本地应用 | DE-U01／DE-C01／DE-P01 | normal |
| DE-S02 旧值与空值分诊 | DE-D01／DE-C02 | normal；unavailable仅D01 |
| DE-S03 插值和兼容政策 | DE-U02／DE-D02／DE-P02 | normal |
| DE-S04 非目标记录保真 | DE-D03／DE-M01 | normal；diagnose_only；modify_direct |
| DE-S05 表单跨行键 | DE-D04／DE-M02 | normal；diagnose_only；modify_direct |

全部任务 `requires=[]`；两修改属于不同场景、独立原版，直接修改入口材料完整。默认诊断在前仅是业务顺序，不制造answer／code依赖。两修改只允许 `library/src/dotenv/main.py` 与 `library/tests/test_main.py`。

`DE-D01` 是唯一材料披露：初始只给症状和固定版本，`incident-evidence` 合法请求后一次披露显式路径调用、合成文件、进程状态、观察和完整调用上下文；unavailable只说明资料无法提供，合法结束为 `insufficient_information`。通用rubric不含隐藏APP_MODE具体事实，也不引用disclosure文件；它只用已消费对话与公共源码要求有证据的判断。初始任务不挂会提前执行隐藏复现的native；另有**仅准入用、披露后**的三路真实API见证，默认保留deployment、override改为local、无进程键时加载local均已验证。

页面title／goal中文；首问、分支、指令和rubric英文；固定代码／业务值保持原样。12份rubric均通过实际 `load_rubric`／`source_evidence` 读取公共源码及公开材料，隐藏资料零提前引用；只读规则没有不适用的candidate证据强制flag。程序观察验证事实或可行性，不替代实际回答的语义评审。

## 当前镜像、离线依赖与完整回归

- 镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1`，实际RepoDigest `sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216`，Python3.12.15、linux-amd64。
- 21个实际wheel和精确requirements冻结于 `environments/python-dotenv-py312`，逐制品SHA／大小在profile。包括Click8.5.0、IPython9.17.1、pytest9.1.1及完整传递依赖；不靠IPython importorskip省略测试。
- 原生业务使用UID1000、network none、只读根／来源、256MiB、PID64、30秒；完整回归512MiB、PID64、90秒。所有源文件／路径均为合成临时路径，无祖先宿主.env。
- 原版在**本轮当前镜像**通过共享可信runner收集并完整执行：**288 collected／288 passed／0 skipped／0 failed／0 error**，3.293秒。离线准备加执行9.163秒，cgroup `memory.peak=173281280`字节。这是实际数据，不是复制旧研究的288；资源是已验证上限，非最优值。
- 校准可信runner SHA为 `e36ec55b5bddb08c791fbb3bf376caa0dd250acb424f2597e782d1fd693d45e9`；主会话仅加入sqlite-utils插件配置后，本仓副本最终同步 `b3e75e056b684fa6d5a6a4871bf8793b8422d373460562110207612c97ba65c3`，两参考使用最终版本再次通过完整288项。合同保持真实原版集合，无删节点。
- 实际可执行 `/work/python/bin/dotenv` 指向 `dotenv.__main__:cli`，受控pure-path绑定到本次测试树src；import证据是该树的 `src/dotenv/__init__.py`。适用上游CLI、IPython、权限、FIFO、symlink和cleanup测试全部执行，没有用安装包替换候选。

## 独立修改正反例

| 目标 | 原版 | 独立参考 | 错误候选与正常对照 |
| --- | --- | --- | --- |
| DE-M01 非目标原文换行 | 原版目标失败 | 12项真实文件矩阵全部通过；完整288项通过 | 保留旁行却把目标改CRLF的错误候选被拒；LF、CRLF、CR、混合、set替换／追加、unset、重复目标、返回值与模式均独立核对 |
| DE-M02 写前拒绝跨行键 | 原版目标失败 | CR／LF／CRLF × 现存／缺失目标全部通过；正常键及多行值通过；完整288项通过 | 静默去换行、进入rewrite后再抛ValueError均被拒；spy核rewrite未进入，文件SHA与目录清单不变，Unicode／点／连字符／下划线及引号反斜杠／多行值保持 |

M01保留“非目标**parsed record**”原字节，目标行继续LF，不改变只读加载的通用换行语义。保留现有追加分隔规则：最后记录不以LF结束时追加一个LF，含既有CR-only末尾的行为；不追加BOM保真或主换行检测要求。M02只拒绝键中的CR／LF，不改变空值默认、普通键政策、值或unset_key。

参考包含实际公开测试，并在隔离容器另行执行：M01参考3／3通过，换原版2失败1通过；M02参考6／6通过，换原版6失败。固定完整回归则恢复可信上游测试，不能靠改候选tests绕过。

首轮私有oracle曾把**目标Binding自身前缀空白**误作非目标记录，导致纯LF对照和M01参考误拒；已将矩阵空白置于明确非目标KEEP记录，保留原失败日志并定向重验，未改上游seed或参考修复。最终正确结果位于 `final-results`，不能用首轮 `business-summary.json` 的failed冒充最终通过，也不能抹除旧失败。

## 可复核证据与重跑

全部原始证据根为 `.deploy/project-catalog-second-pack/python-dotenv/`：

- `source-files.json`：实际Git tree逐blob来源。
- `calibration/`：完整pytest stdout／stderr／JUnit／逐节点、合同、实际容器状态、资源与cleanup。
- `results/`：首轮真实ProjectVerifier原版／参考／错误候选及保留失败；`final-results/`：修正后定向重验、最终两参考业务＋完整回归、披露后三路API见证。
- `public-tests/`：两参考交付测试与换回原版的完整输出／JUnit。
- `references/DE-M01`、`references/DE-M02`：**独立**参考候选根；正式私有补丁为 `verification/reference/DE-M01.patch`、`DE-M02.patch`。不得叠加两个场景的修复。
- `handoff-library/`：单项目最终内容库，供root构包或定向复核；正式catalog由root统一接入，子任务未改共享catalog。
- `cleanup-final.json`：归属本仓证据根的运行容器为零；校准／公开测试临时容器均已删除，验证临时输入目录已清理，证据与私有参考保留。

实际验证脚本为本证据根的 `calibrate.py`、`verify_business.py`、`verify_regression.py`、`verify_final.py`、`verify_public_tests.py`。业务／候选通过产品 `scripts/validate-project-scenarios.py` 的真实 `ProjectVerifier.verify_native` 执行；校准使用同一可信runner与当前镜像。重跑单例命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python scripts/validate-project-scenarios.py --root .deploy/project-catalog-second-pack/python-dotenv/handoff-library --project python-dotenv --task DE-M01 --candidate .deploy/project-catalog-second-pack/python-dotenv/references/DE-M01 --image ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1 --with-regression --output <本轮新结果路径>
```

真实模型回答质量、评分可靠性、实际token成本以及部署均未验证；整包模拟和页面验收不得由本仓原生准入结论替代。
