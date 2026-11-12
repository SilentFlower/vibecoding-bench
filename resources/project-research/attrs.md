# attrs 单仓研究

研究状态：完成逐仓研究，尚未实施20步、冻结独立验收或接入平台。研究只覆盖普通数据类、转换、验证、导出与易用性。

## 来源、冻结与许可

官方仓库：[python-attrs/attrs](https://github.com/python-attrs/attrs)；已通过网页核对归属及[完整提交](https://github.com/python-attrs/attrs/commit/ee66e7274852438cc23d4240a1a9cd632fda8b52)。固定commit：`ee66e7274852438cc23d4240a1a9cd632fda8b52`。真实源码：`/root/project/vibecoding-bench/.deploy/github-100-research/core-utils/attrs/source`；本次以只读方式复用上次checkout/venv和原始基线，原始来源在reused-evidence.json。MIT许可全文位于`source/LICENSE`；版权2015 Hynek Schlawack and attrs contributors，代码与原生测试保留SPDX。已检查src/tests无另列vendor代码；文档赞助商图片不进入未来运行源码快照，商标不作为MIT授权内容。

## 源码与实际规模

跟踪141文件，2076123字节；独立venv 59096879字节。读取`src/attr/_make.py`中Attribute/Factory/Converter/_ClassBuilder/evolve及生成脚本，`_funcs.py`导出递归，`_next_gen.py`公开包装，`validators.py`与`converters.py`组合器、`filters.py`身份匹配、`_config.py`开关。运行时无外部依赖，不需要服务或云凭据。`attrs.Converter(takes_self=True,takes_field=True)`已经提供实例/字段访问，故没有把既有转换器上下文冒充新增步骤。

## 隔离原生基线

依赖准备宿主Python3.12.3；实际容器Python3.12.15（镜像ID及sys.version见runtime-verification.json）；测试依赖与精确版本在`requirements-frozen.txt`、`test-requirements.txt`，pip安装报告原始位置为只读复用目录`/root/project/vibecoding-bench/.deploy/github-100-research/core-utils/attrs/installation.json`；初装18.707秒，补全git历史后重装6.965秒，版本26.1.1.dev81。基线命令为冻结checkout上`pytest -q -ra -p no:cacheprovider --junitxml=/tmp/results.xml tests`，在离线、只读、UID1000、256MiB容器执行；实际16.939秒，pytest 15.161秒，最大RSS 267396KiB（Linux RSS统计与容器cgroup口径不同）。完整运行原生tests：**1401 passed、10 skipped、1 xfailed、0 failure/error，exit=0**。JUnit tests=1412/skipped=11，xfail归入JUnit skipped；没有subtests。skip为Python3.14注解2项、Python3.13功能4项、可选pyright3项、PyPy专属1项；xfail为上游test_slotted_confused。Hypothesis因只读源码使用内存数据库并有1条warning。没有执行其他Python、typing_tests/mypy工具链、文档、lint及bench，不能将本次说成全部CI矩阵通过。

本次新运行真实订单场景：`Item('tea','2')`执行int转换和ge(1)验证，`attrs.asdict`导出，`attrs.evolve(...,quantity='3')`得到数量3；实际加载`/source/src/attrs/__init__.py`。逐项观察exit=0，离线容器已移除。缺陷实证包括额外槽位写入TypeError、astuple遗留嵌套对象、Attribute过滤串类、pickle丢继承dict、optional字符串注解TypeError。其余路线为用户场景与真实源码缺口形成的本地增强提案，不宣称缺陷或上游承诺。

## 二十步与边界

[详细20步路线](attrs-roadmap-20.md)与`roadmap-20.json`逐项对应；各步都有场景、原版现状、真实模块、兼容边界、正常/异常验收、原生回归及真实依赖。第07步路径可供第13/14步复用，其余不强造顺序。没有把测试/文档拆步，没有实施路线或改变冻结源码。

## 原始证据与重跑

证据根：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/attrs`。`baseline-tests.log/xml`、`baseline-result.json`、`observations.log`、`observations-result.json`、`observe.py`、`requirements-frozen.txt`、`size.json`、`official-source-verification.json`、`research.json`、`review-result.json`、`roadmap-20.json`和`evidence-sha256.json`可独立对账。重跑观察：

```bash
/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/attrs/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/attrs
```

重跑原生基线：

```bash
/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/attrs/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/attrs --tests tests
```

这些是本机证据路径，venv及只读引用并非跨机器发布包。正式离线依赖分发、候选加载适配、控制端冻结验收和累计回归尚待另行完成。
