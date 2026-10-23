# 候选审查：Argcomplete

**不计入研究完成数**。原生完整套件要求真实bash/zsh交互及临时包安装，当前无zsh；核心选择性测试通过不能替代完整shell套件，不将默认pytest误收或部分结果计为研究完成。

官方来源：[kislyuk/argcomplete](https://github.com/kislyuk/argcomplete)，固定 [61c629239551fb3af1d59b0bf51852b2b3f7b61d](https://github.com/kislyuk/argcomplete/tree/61c629239551fb3af1d59b0bf51852b2b3f7b61d)。版本：读取依赖冻结和完整commit。许可证：Apache-2.0；许可证保留在原生LICENSE.rst。跟踪49文件、239978字节；Python总3915行包括测试/工具，不能当产品行数。

适用范围与实际结果：显式选择TestArgcomplete/TestArgcompleteREPL/TestSplitLine/TestCheckModule/Warn五个实际unittest类，-s运行52通过/1上游xfail。它是核心诊断范围，绝不代表完整原生make test。 当前日志/XML记录52通过、0失败、0错误、0普通跳过、1预期失败，0.68秒。安装21.52秒、独立venv 141720532字节；安装/测试子进程共同观测峰值RSS 34552 KiB。环境Python3.12、Linux、无业务祖先的临时检出及隔离HOME。

已读原生Makefile/CI、测试入口/REPL帮助类、CompletionFinder和io。默认pytest先误收test_package fixture而导入错误；首轮显式pytest受FD捕获影响48失败，保留为pytest-fd-capture-*；关闭捕获后pytest还误收纯mixin TestShellBase而20失败，日志保留pytest-mixin-collection-*；改为原生五个具体unittest类后核心52通过/1xfail。上述runner差异不被当作产品BUG。原生make test为coverage run ./test/test.py，含shell交互、临时pip构建，未以缺环境排除后冒充全套。公开rl_complete原生场景把--color r补成--color red，独立venv/HOME，不写系统shell启动文件。

证据：`.deploy/github-100-research/cli-config/argcomplete/`。固定来源/commit、install与精确依赖、原生baseline日志/XML/命令/资源、原生observe.py/observations-result.json、review-result.json及SHA256摘要均保留。没有20步路线，未实施、冻结验收或接入。

重跑：clone官方仓库，detached checkout上述commit，独立venv用test-requirements.txt准备精确依赖后安装本地检出；在checkout以隔离HOME/PATH运行 `<venv>/bin/python -m pytest -q -ra -s test/test.py::TestArgcomplete test/test.py::TestArgcompleteREPL test/test.py::TestSplitLine test/test.py::TestCheckModule test/test.py::Warn`。原生场景另运行 `<venv>/bin/python <evidence>/observe.py`。未验证的其他Python/OS、发布、文档和风格/类型检查保留未验证。

未改上游源码、业务、账号、系统shell或生产数据；未创建task、提交/推送/部署、向上游发消息或进行平台评测模型调用。
