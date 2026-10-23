# 候选审查：Decorator

**不计入研究完成数**。签名保留和装饰器生成的专门边界内尚不足20个合理新交付；不将Python参数类型或测试矩阵逐个拆步。

官方来源：[micheles/decorator](https://github.com/micheles/decorator)，固定 [956b6396c7369aab4acc7a44851572fcb92fb34a](https://github.com/micheles/decorator/tree/956b6396c7369aab4acc7a44851572fcb92fb34a)。版本：读取原生__version__与依赖冻结（SCM源码固定）。许可证：BSD-2-Clause；已读LICENSE.txt，2005–2026 Michele Simionato版权。跟踪19文件、181683字节；Python总3377行包括测试/工具，不能当产品行数。

适用范围与实际结果：显式执行完整原生tests/test.py中的28个unittest，包括DocumentationTestCase内doctest；默认pytest未收集该文件的0项/exit5保存在default-auto-collection-*。 当前日志/XML记录28通过、0失败、0错误、0普通跳过、0预期失败，6.14秒。安装5.63秒、独立venv 50136202字节；安装/测试子进程共同观测峰值RSS 35688 KiB。环境Python3.12、Linux、无业务祖先的临时检出及隔离HOME。

已读decorate/fix/decorator/decoratorx、FunctionMaker、ContextManager及dispatch_on。已有普通/生成器/coroutine caller分派、functools.partial、签名/default/annotations/__wrapped__保留、contextmanager与多参数dispatch。原生使用场景以位置专用和关键字专用参数包装计算，结果11、inspect.signature保持。仅标准库运行，pytest为研究runner；不宣称Python3.15延迟注解问题已复现。

证据：`.deploy/github-100-research/cli-config/decorator/`。固定来源/commit、install与精确依赖、原生baseline日志/XML/命令/资源、原生observe.py/observations-result.json、review-result.json及SHA256摘要均保留。没有20步路线，未实施、冻结验收或接入。

重跑：clone官方仓库，detached checkout上述commit，独立venv用test-requirements.txt准备精确依赖后安装本地检出；在checkout以隔离HOME/PATH运行 `<venv>/bin/python -m pytest -q -ra tests/test.py`。原生场景另运行 `<venv>/bin/python <evidence>/observe.py`。未验证的其他Python/OS、发布、文档和风格/类型检查保留未验证。

未改上游源码、业务、账号、系统shell或生产数据；未创建task、提交/推送/部署、向上游发消息或进行平台评测模型调用。
