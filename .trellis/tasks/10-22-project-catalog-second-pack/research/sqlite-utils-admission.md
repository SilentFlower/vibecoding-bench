# sqlite-utils 第二批原生准入与集成交接

本轮日期：2026-10-22。本仓正式内容和当前目标镜像原生验收已完成，尚待主会话整包模拟／页面／交付检查；未调用真实模型或OAuth，未执行Git写操作和部署。原规划 `sqlite-utils-plan.md` 保持原样，本报告不把其历史宿主数字当本轮结果。

## 来源和内容

固定 `https://github.com/simonw/sqlite-utils@9c66bafa52ae23d40499c74b0db3b635bcddb876`，Apache-2.0，完整LICENSE SHA256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`。逐个读取真实Git blob导出 **107文件／1,450,898字节** 到 `project_library/projects/sqlite-utils/seed/library/`，没有预修、依赖环境、日志或参考实现；最终按全集逐SHA与导出记录相等。完整路径、Git blob、SHA、大小和模式见同目录 `sqlite-utils-admission.json` 的source.files及本地 `source-files.json`。

4场景／13唯一任务，understand2、consult3、diagnose4、plan2、modify2；11个非修改任务均 `allowed_paths=[]`，全部任务 `requires=[]`。模型首问、指令、披露规则与rubric英文，标题／分类／场景／goal中文。SQ-D01仅有语义评审，通用rubric不带隐藏复现或无条件源码证据，先实际请求材料再披露 `import-evidence`；`unavailable` 入口可合法结束为 `insufficient_information`，不交付正常故障材料。只读任务没有要求不存在candidate_files的flag。

场景顺序与研究一致：S01 U01/C01/P01，S02 D01/D02/C02，S03 U02/C03/D03/M01，S04 P02/D04/M02。S02另有unavailable，S03/S04各有diagnose_only／modify_direct；S04 diagnose_only仅D04。两个修改不同场景，完整公开复现和边界自足，直接入口从对应原版开始，不继承另一修复。

## 当前镜像、离线环境与完整合同

实际镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1`，固定RepoDigest `sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216`；当前 **Python3.12.15／SQLite3.40.1**。环境包含14个公开真实wheel，精确requirements与每个wheel的SHA／大小均在正式 `environments/sqlite-utils-py312/profile/profile.json`，不安装上游sqlite-utils发行包代替候选。Hypothesis 6.170.5真实pytest11入口 `_hypothesis_pytestplugin` 已由主会话显式加入可信suite；autoload关闭后仍完整启用该插件。

本仓 `verification/native_regression.py` 与当时共享可信runner逐字节相同，SHA256 **`b3e75e056b684fa6d5a6a4871bf8793b8422d373460562110207612c97ba65c3`**。当前完整上游校准真实收集 **1513节点＝1497通过＋16跳过，0失败／错误／未执行**；JUnit1513元素逐节点对账。16项为3个缺编译ext.c、1个缺pandas/numpy、12个缺SpatiaLite；逐nodeid及实际reason在正式合同对应校准summary和本报告JSON，不按历史固定skip数猜测。33个上游警告保留原日志，未删节点、测试或修改期待值。

校准使用UID1000、network=none、只读根、只读baseline／offline／runner，512MiB／PID64，业务与回归隔离。pytest21.59秒，含冻结工具收集／对账22.63秒，离线准备10.01秒，合计32.89秒；子进程峰值292300KiB，因此完整回归不能宣称在business256MiB预算内通过。正式profile为business256MiB／30秒／PID64、regression512MiB／180秒／PID64，是实测通过的上限而非最优资源估计，不增加账号预算。

## 独立业务、参考与反例

所有正式业务验证调用现有 `scripts/validate-project-scenarios.py` 的真实ProjectVerifier，在目标镜像离线安装、核实际候选import，输出真实SQLite结果。CLI／独立标准库文件读取／新进程重开／memory反例、重复upsert保留memo、首批类型推断、可运行唯一NULL示例、FTS生命周期及原版故障、选择性output／WHERE方案、回调故障均已留原生日志。引用源码窗口已逐一对应真实定义。

- **SQ-M01**：原版按预期失败；独立参考业务矩阵全部通过，包括FTS4/5、list/tuple/iterator/generator、触发器开关、初始命中、后续INSERT、空表、含空格标识符、porter、replace同配置无DDL／写入及变化配置生效。FTS5另核真实UPDATE／DELETE。FTS4原有UPDATE触发器异常作为明确排除边界保留，没有捆绑第三个修复。参考完整1513节点与冻结结果精确相等（1497通过／16相同skip）。
- **SQ-M02**：原版按预期失败；独立参考通过bound dict.get／partial／callable object／同名函数／lambda、同表与跨表、同对象重复调用、output和bound WHERE保留原值、Falsey、multi、回调异常事务及公开默认注册边界。参考完整1513节点与冻结结果精确相等。内部修复不改公共 `register_function(replace=False)`；显式replace=True仍替换。
- **公开新增回归**：M01新增4参数测试，原版4失败、参考4通过；M02当前回调和公开默认2项，原版1失败／1通过、参考2通过。直接测试运行额外核实际 `sqlite_utils.__file__` 分别属于对应原版／参考工作树，未通过site-packages偷换。完整回归另从baseline恢复冻结测试，候选公开tests不能改变私有结论。
- **错误候选**：强制禁用所有FTS触发器、改变公共注册默认为replace=True，均被真实native拒绝；缺--empty-null的候选示例也被实际SQL NULL／类型检查拒绝。无效示例不是靠关键词或打印预期结果放行。
- **披露事实**：当前镜像实际执行CSV当默认JSON，exit1完整stderr为 `Error: Invalid JSON - use --csv for CSV or --tsv for TSV files`，另含原生JSON解析详情；加--csv和合法JSON默认均exit0。完整stderr已原样纳入仅请求后披露材料，不提前进入通用rubric。

参考M01只改 `library/sqlite_utils/db.py`、`library/tests/test_fts.py`；参考M02只改db.py、tests/test_convert.py、tests/test_register_function.py；与固定seed逐文件比较核实，无跨场景修复继承。参考patch／公开测试含中文原创注释与docstring，上游seed原字节不变。

### 保留的首轮失败

`business-attempt-01/` 保存原始全部JSON及business.log。初版Falsey oracle对混合输入自动推断的TEXT列期待整数0，实际SQLite先把0转为字符串，导致P02和M02参考出现oracle不适用失败。已把该兼容探针明确为BLOB亲和性列，隔离“回调是否收到Falsey”与类型推断政策，并对相关业务、原版M02、两参考完整回归重新验证。没有改候选、生产实现或通过期待来掩盖缺陷；P02-final和M02-reference-full现按真实原类型通过。其余已通过且不受影响的业务未重复昂贵执行。

## 主会话交接

本地证据根：`.deploy/project-catalog-second-pack/sqlite-utils/`。

- 正式内容：`project_library/projects/sqlite-utils/`；正式环境：`project_library/environments/sqlite-utils-py312/`。
- 单仓实际可加载catalog：`library/`；最终静态结果见 `static-final.json`，仅证明本仓1项目／4场景／13任务，不是整包v4摘要。
- 独立参考根：`reference-M01/`、`reference-M02/`，均包含候选的library目录。
- 透明mock答复：`mock-answers.json`，含13任务及D01-question／D01-unavailable；C02答复与已真实执行的answer-C02.md一致。模型质量未验证。
- 完整原版：`calibration-01/`（run/summary.json、逐节点、JUnit、原生日志、resources.json、native-contract.json、容器状态与cleanup）。两参考完整结果：`M01-reference-full.json`、`M02-reference-full.json`。
- 错误候选及最终业务：`final-summary.json`与对应JSON；公开回归／披露原生命令：`public-probes/result.json`及完整stdout/stderr；原版首轮JSON另保留。
- 复验入口示例：`.deploy/project-iteration-repairs/venv/bin/python scripts/validate-project-scenarios.py --root .deploy/project-catalog-second-pack/sqlite-utils/library --project sqlite-utils --task SQ-M01 --candidate .deploy/project-catalog-second-pack/sqlite-utils/reference-M01 --image ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1 --with-regression`。M02换对应task与参考；C02增加 `--answer .../answer-C02.md`；原版目标省略candidate并 `--expect failed`。逐JSON记录实际catalog／candidate摘要与期望结果。

正式seed最后全集107文件SHA不变，参考差异和实际候选路径有独立记录。校准和公开探针容器均finally按本次归属删除；ProjectVerifier临时数据根全部清理；`cleanup-final.json`核本仓剩余容器0、临时输入目录0、业务临时根清理。仅保留可审计证据和私有参考。全部native实测不代表真实模型、整包模拟／页面或上线已通过；这些由主会话后续完成。
