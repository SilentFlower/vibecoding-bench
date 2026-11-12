# packaging 单仓研究

研究日期：2026-10-21。固定来源、许可、原生基线、离线依赖筛选场景和[20项路线](./packaging-roadmap-20.md)已研究。路线未实施，未冻结独立验收、接入正式平台或部署。

## 来源与许可归属

官方[pypa/packaging](https://github.com/pypa/packaging)与[真实提交](https://github.com/pypa/packaging/commit/1a62a26afe0f4881593e31bed4f7753bd1c8fe27)均已网页核对；固定commit `1a62a26afe0f4881593e31bed4f7753bd1c8fe27`，真实检出`/root/project/vibecoding-bench/.deploy/github-100-research/data-tools/packaging/source`且工作树干净。主仓许可是Apache-2.0 **或** BSD-2-Clause，保留`LICENSE`、`LICENSE.APACHE`、`LICENSE.BSD`和Donald Stufft及贡献者归属。`licenses/__init__.py`改编自hatch解析器，文件头另含2017-present Ofek Lev的**完整MIT许可**，必须一起保留，不能只写主仓双许可。`_spdx.py`为SPDX3.27.0标识与deprecated事实表，生成来源见`tasks/licenses.py`和[SPDX数据说明](https://github.com/spdx/license-list-data/blob/v3.27.0/README.md)，不包含各许可全文；表中列出的GPL等是被识别的数据，不是本仓授权条件。测试的虚构包Metadata含各种License值，是解析负载；未另行下载这些示例包。原始ELF样本及编译脚本保留，不运行归档内的二进制。

## 真实源码与运行成本

跟踪140文件、1630219字节；补齐依赖后测试venv 56966208字节。生产不依赖第三方运行包。已读Version及parts/replace与比较键、Requirement表示和替换、Marker解析/求值/组合与私有树、utils文件名、tags目标与排名、Metadata字段校验和RFC822写入、dependency_groups包含解析、Pylock选择、ranges公开集合运算、SPDX表达式解析和表生成来源。上游当前功能很多，未把已实现能力冒充新路线。

依赖准备宿主Python3.12.3，测试容器Python3.12.15（镜像ID及sys.version见runtime-verification.json）；复用原始固定检出并复制既有venv后只补缺少的上游声明测试依赖coverage、hypothesis、pretend、tomli_w；初装有4.505秒实测，补齐阶段未单独计时，此项成本限制保留。精确版本与pip报告在本地证据。无需服务、云账号、HTTP调用或数据库。完整原生测试的资源需求明显高于普通API：256MiB在15.452秒OOM，日志与exit137结果保存在`256m-baseline-*`；768MiB原样完整通过，最大RSS 551868KiB。普通业务场景0.492秒、256MiB通过。轻量判断应区分无依赖库运行和较大的原生测试预算。

## 原生集合与实际场景

原生`pytest -q -ra -p no:cacheprovider --junitxml=/tmp/results.xml tests`，保留pyproject默认`-m not property`。完整默认集合**63335 passed、3 skipped、434 deselected、0失败错误，exit=0**，墙钟61.574秒，JUnit时间58.33秒。3项跳过均因copy.replace需Python3.13；434项property为上游显式opt-in集合，本次未跑，不能把默认基线称为所有可选property也通过。无warning。离线只读容器、UID/GID1000、768MiB无额外swap、pids128，无OOM且临时容器已删除。未跑其他Python/PyPy/平台、coverage门槛、docs/doctest、lint、bench和下游消费者集成。

本次实跑Requirement筛选1.0/1.5并排除2.0，Marker目标Python判断、Metadata读取demo1.5和依赖组dev包含test得到pytest/ruff；加载`/source/src/packaging/__init__.py`。另外20项观察保存当前规范化版本、环境回填、历史描述、文件名歧义与公开入口缺口。全部路线标为**增强**，历史兼容或标准待决定行为不直接称缺陷。

## 20项路线边界

逐项具有来源/实际场景、原版和替代方式、交付、真实模块、兼容边界、正常/异常验收、原生回归和实际依赖。AST公开、部分求值和extras集合是独立用户行为；RECORD模型可供wheel本地归档API复用；依赖组来源与Pylock选择原因分别解释不同处理阶段。没有拆同一缺陷的多个测试维度。新模块只为离线普通包元数据/本地归档研究，不包含网络或账号机制。

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/packaging`。`baseline-tests.log/xml`、`baseline-result.json`、`256m-baseline-*`、`observations.log`、`observations-result.json`、`observe.py`、`requirements-frozen.txt`、`size.json`、各安装报告、`official-source-verification.json`、`research.json`、`roadmap-20.json`、`review-result.json`和`evidence-sha256.json`可以对账。原始来源见`reused-evidence.json`，目录不纳入Git，跨机器必须重新检出和准备依赖。

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/packaging/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/packaging
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/packaging/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/packaging --memory 768m --tests tests
```

没有修改正式内容库、实施路线、提交推送或部署。
