# cattrs 单仓研究

研究日期：2026-10-21。来源、固定源码、适用原生基线、JSON订单场景与[20步路线](./cattrs-roadmap-20.md)已研究完成；路线未实施，冻结验收和正式平台接入尚未建立。

## 来源与许可

官方[python-attrs/cattrs](https://github.com/python-attrs/cattrs)与[完整提交](https://github.com/python-attrs/cattrs/commit/57333a234a19903a94e5b181bc0aee6b187ee05c)已网页核对；固定提交`57333a234a19903a94e5b181bc0aee6b187ee05c`，真实检出`/root/project/vibecoding-bench/.deploy/github-100-research/core-utils/cattrs/source`，Git工作树干净。MIT许可，版权2016 Tin Tvrtković，保留`source/LICENSE`全文及归属。已扫描src/tests的版权与license标记，未见另列vendor/样本许可；可选后端是独立依赖包，其许可不能用本仓MIT代替。此轮只研究普通类/数据转换，不涉及网络、账号机制。

## 真实结构与轻量实测

跟踪177文件、1490095字节；独立测试venv 77503989字节。已读`BaseConverter/Converter`初始化、structure/unstructure、工厂注册与缓存，`MultiStrategyDispatch/FunctionDispatch`首匹配语义，`gen`字段覆盖/生成代码，`disambiguators`必需字段算法，`v/errors`异常树与路径，`preconf/json/msgspec`后端规则和递归guard。生产运行依赖`attrs>=25.4.0`、`typing-extensions>=4.14.0`（旧Python另有exceptiongroup）；不需服务、系统数据库或云凭据。为验证可选预配置，实际安装了json标准库以外的ujson/orjson/msgpack/PyYAML/tomlkit/cbor2/pymongo/msgspec/tomli-w；这里安装pymongo只为BSON编解码，没有连接MongoDB。精确版本在`requirements-frozen.txt`，安装29.563秒。测试环境较生产最小依赖大，不能把整个venv大小当作最小运行体积。

## 适用原生基线与业务场景

复用先前真实固定检出和独立venv，并逐项核对commit、干净工作树、日志/XML、依赖及当前源码。原始来源写在`reused-evidence.json`。原生命令`pytest -q -ra -p no:cacheprovider --junitxml=/tmp/results.xml tests`，依赖准备宿主Python3.12.3；实际测试容器Python3.12.15（镜像ID及sys.version见runtime-verification.json），离线只读容器、UID/GID1000、256MiB、无额外swap、pids128。实际墙钟220.013秒，pytest 217.061秒，最大RSS 268884KiB（进程RSS与cgroup内存口径不同），无OOM且临时容器已移除。**1059 passed、15 xfailed、0普通skip、0失败/错误**；JUnit tests=1074/skipped=15，均为上游include_subclasses未启用的预期失败。4条warning：未启用仅Python3.14适用的typing插件导致两项未知配置、parametrize迭代器弃用、Hypothesis只读路径回退内存。未运行3.14类型工具、其他Python/PyPy、文档、lint、coverage发布和bench目录，不声称全部CI矩阵通过。

本次新运行JSON订单：将数量字符串2结构成嵌套Product.quantity整数2，ISO日期成为带UTC的datetime，JSON导出再loads保持对象相等；加载路径`/source/src/cattrs/__init__.py`，观察exit=0，0.471秒，容器已删除。第01步工厂默认值误判和第02步msgspec递归钩子不一致已复现；其余为增强和兼容策略，不称为18个额外BUG。

## 路线真实性与边界

每步含来源/场景、原版结果、已有替代、交付、实际模块、兼容、正常/异常验收、原生回归和依赖。已排除已有的`Annotated[T, override()]`、omit_if_default对attrs converter的默认值转换、PEP695联合alias、具体Path到str、整类use_class_methods能力。字段上下文不同于每次调用context；错误记录不同于根目标类型；联合子集不同于泛型信封路由。schema是受限新模块提案，不能推断任意自定义hook。20项均在同一真实工程累计，不强造无关步骤依赖，也未把测试/文档或同源递归症状拆步。

## 证据与重跑

本地证据：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/cattrs`。包含`baseline-tests.log/xml`、`baseline-result.json`、`observations.log`、`observations-result.json`、`observe.py`、依赖锁、`size.json`、`official-source-verification.json`、`research.json`、`roadmap-20.json`、`review-result.json`和`evidence-sha256.json`。复用证据与新场景结果分开保存；这些是本机路径，并非跨机器依赖分发包。

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/cattrs/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/cattrs
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/cattrs/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/cattrs --tests tests
```

没有实施路线、修改正式内容库、冻结新增验收、提交推送或部署。
