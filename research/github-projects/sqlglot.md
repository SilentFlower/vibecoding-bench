# SQLGlot 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./sqlglot-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[tobymao/sqlglot](https://github.com/tobymao/sqlglot)和[完整提交](https://github.com/tobymao/sqlglot/commit/67961afbed7c986dfe26ab82db89a25814c1bdcb)已网页核对。固定`67961afbed7c986dfe26ab82db89a25814c1bdcb`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-app/sqlglot/source`工作树干净。主源码MIT，LICENSE署名Toby Mao2026。tests/fixtures/jsonpath包含jsonpath-compliance-test-suite的独立BSD二条款LICENSE，已单列保存并纳入hash；不把第三方夹具整体称为原创MIT。未取得的sqlglot-integration-tests子模块不在当前研究快照与许可准入范围内。

## 源码、依赖与成本

已读方言Tokenizer/Parser/Generator、Expr树与位置元数据、MappingSchema与类型标注、scope解析、optimizer规则循环/内部journal、列血缘Node与HTML生成、AST dump/load与diff、DDL/查询构建器、占位符替换、sources展开、本地Python executor与Table物化、命令行原生入口及默认unittest/doctest发现机制。只研究普通本地SQL解析、转换和报表。

实际跟踪361文件、16764146字节；独立测试venv 243467786字节。默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装29.392秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

完整主仓默认python -m unittest发现集合，Ran 1500个主项全部通过，另21780个内部subTest成功（unittest_subtests_passed单列），零skip、零失败；包含tests/test_docs.py所加载的模块doctest、所有方言、优化器、本地DuckDB与Python执行器TPC-H/TPC-DS；没有设置SKIP_INTEGRATION。控制端只把ProcessPoolExecutor默认并发改为2，所有原生任务仍运行。主测试与成功subTest分列；控制端XML只有unittest主项汇总属性，不含逐条testcase元素或subTest元素，非上游JUnit插件或pytest执行。原始Ran行为主项依据，成功子项由只增计数的TextTestResult.addSubTest捕获。 实际1500通过、0跳过、0失败、0错误。墙钟105.836秒，原生集合内部运行时间102.361024秒，进程峰RSS 2007184KiB；容器预算2048m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实三行订单用SQLGlot本地Python executor按product聚合并排序得到coffee=1、tea=5；Postgres输入转SQLite后在内存sqlite实际建表/插入/执行，得到相同结果。observations-result.json的real_scenario.cost单列含库导入的场景耗时和进程峰RSS，容器预算256m。另20项原版观察已运行，集合优先级、图渲染变异与空表推断三项有assert复现。

## 路线真实性与限制

已存在：方言读写、parse_one多语句Block、Parser.max_nodes预算、结构化ParseError、Token位置信息、全部输出列血缘lineage(None)/on_node.payload、AST dump/load、AST diff、Optimizer自定义rules、UDF schema类型、DDL rename构建器、replace_tables/replace_placeholders、sources展开、anonymize、Table迭代与执行器LIMIT早停；以上均未重复列作新增。FAQ明确解析宽松且不是数据库validator、格式不完全保真，这些已声明行为不当作缺陷。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。3项实跑问题，其余为显式增强。3项原版实跑缺陷与17项增强；诊断、源映射、逐语句解析、输出描述、影响血缘、重复投影追踪、图序列化、规则追踪、引用迁移、参数提取、语义差异、schema演进、输出契约、查询集依赖、持久指纹、批次执行和本地CLI分别有不同可见交付。新增接口名称均为提案，不暗示现有定义。

- 1024m首次完整集合在107.017秒OOM退出137，原始1024m-baseline-*保留；完整测试成本明显高于普通解析/报表场景，不能据单个轻场景声称全套低于1GB
- sqlglot-integration-tests为上游gitlink 8cbf013a7b0bd1871abce4ebb543560d0e554799，当前未检出；原生loader按目录存在才加载，因此本轮完整的是主仓默认适用集合，未验证该独立外部集合，未修改loader
- 初次2GB完整运行1497主项通过、1导入错误，属于缺少setuptools的环境问题；missing-setuptools-*保留，补装精确报告setuptools-installation.json已保存，补装耗时未单列，不把它伪报成业务缺陷
- 原生日志保留一条上游预期unsupported property提示，以及test_sqlglotc加载setup.py时缺setuptools_scm的可选版本定位诊断；后者走上游明确fallback，并不跳过该模块3项mock构建测试，实际sqlglotc构建与版本pin逻辑没有验证。测试没有Python warning过滤删改
- 默认纯Python模式已测；可选sqlglotc/mypyc、独立mypy/ruff/pre-commit、docs构建、性能基准与其他Python/系统未运行，不能称make check或全CI矩阵通过
- 完整集合的worker默认数经控制端限制为2，并限制BLAS线程；这属于资源适配，未删除测试或修改源码。主进程RSS与子进程RSS均原样记录，不能把单进程峰值当容器总峰值
- 首次观察脚本误选未触发不支持消息的用例导致控制端assert失败，first-probe-*保留；改用上游已有ROW FORMAT用例后的20项观察通过，未改上游工程
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-app/sqlglot`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-app/sqlglot/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-app/sqlglot --memory 2048m
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-app/sqlglot/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-app/sqlglot
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
