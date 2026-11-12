# Wrapt 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./wrapt-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[GrahamDumpleton/wrapt](https://github.com/GrahamDumpleton/wrapt)和[完整提交](https://github.com/GrahamDumpleton/wrapt/commit/6b4e844950213118b19e613248d2bc9469eb731e)已网页核对。固定`6b4e844950213118b19e613248d2bc9469eb731e`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/wrapt/source`工作树干净。BSD二条款，保留LICENSE中的Graham Dumpleton2013-2026归属。已扫描核心Python/C源码与tests，未见额外复制库许可；mypy/typeshed等构建测试依赖分别保留其通知。

## 源码、依赖与成本

已读四参数通用装饰器、descriptor绑定、with_signature的纯内省契约、C/Python ObjectProxy复制限制、Auto/Lazy proxy、线程与async同步/调用约定桥、实例LRU缓存与类方法缓存绑定、wrapper chain与自有类属性安装/恢复。只研究本地普通计算和维护能力，未研究网络/账户目标。

实际跟踪223文件、1849151字节；独立测试venv 119190299字节。运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装19.977秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

完整上游tests及37个mypy成对输出例：C模式1412主项通过、43子项通过、6skip；纯Python1410主项通过、43子项通过、8skip。6skip需Python3.14注解，纯Python另2个C专用不适用。baseline的passed已仅含主项，junit_passed/junit_tests保留XML聚合值，raw文件保留原结果。 实际1412通过、6跳过、0失败、0错误。墙钟28.283秒，pytest XML时间26.876秒，进程峰RSS 54492KiB；容器预算768m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实Price.total(3)经通用decorator返回7，绑定签名(quantity:int)->int保持；加载/source/src/wrapt，BaseObjectProxy来自C backend _wrappers。另实跑类方法缓存Base/Derived串绑定，及slots、普通cache返回协程等原版行为；后两者按增强而非无依据缺陷处理。

## 路线真实性与限制

已支持with_signature/with_doc、adapter factory、自动descriptor/async dunder、LazyObjectProxy同步首次初始化、async synchronized、mark_as_sync/async、sync/async桥、实例LRU缓存、wrapper_chain/find/unwrap/单目标scope和类型stubs；不重复列作新增。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。1项实跑问题，其余为显式增强。1项类方法缓存绑定实证修复与19项独立普通增强。已有37个类型例补齐后执行通过；缓存策略、生成器生命周期、参数适配、组合管线和只读诊断均有不同可见行为。

- 首次缺mypy两模式各37软skip及warning保留without-mypy-*，补齐CI固定1.20.1后的最终集合已实际通过，不拿初次skip冒充适用成功
- 最终C原始XML聚合1455 passed=1412主项+43子项；纯Python1453=1410+43；pytest进程RSS不含全部mypy子进程累计峰值
- 未另跑无扩展构建安装模式、其余Python/PyPy/OS、文档构建与独立性能基准；当前已安装C并明确禁用的模式运行通过
- 首次安装19.977秒；后来补装类型工具耗时未单列，安装报告和精确freeze已保存
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/wrapt`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/wrapt/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/wrapt --memory 768m --tests tests
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/wrapt/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/wrapt
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
