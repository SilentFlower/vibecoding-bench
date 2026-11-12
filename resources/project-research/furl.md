# 候选审查：Furl

**不计入研究完成数**。Python3.12完整原生基线75通过、2失败，IPv6地址预期与当前urllib.parse/ipaddress验证冲突未解决，不准入。

官方来源：[gruns/furl](https://github.com/gruns/furl)，固定 [bb77c48c6735929b469954ab6e54b33e17ac5121](https://github.com/gruns/furl/tree/bb77c48c6735929b469954ab6e54b33e17ac5121)。版本：读取furl/__version__.py与依赖冻结。许可证：Unlicense；已读LICENSE.md中的公共领域声明和免责声明。跟踪24文件、230528字节；Python总4947行包括测试/工具，不能当产品行数。

适用范围与实际结果：完整原生tests在pytest runner执行77个unittest；75通过，test_hosts和test_netloc失败，未删改/排除。 当前日志/XML记录75通过、2失败、0错误、0普通跳过、0预期失败，6.14秒。安装9.86秒、独立venv 51830451字节；安装/测试子进程共同观测峰值RSS 75180 KiB。环境Python3.12、Linux、无业务祖先的临时检出及隔离HOME。

实际读取Path/Query/Fragment/furl入口、URL splitting/validators，以及失败栈。独立安装根据真实setup.py对setuptools.command.test的旧导入，build-constraints.txt约束setuptools<72，未改产品源码；核心依赖six/orderedmultidict冻结。真实场景构建Unicode路径与page参数成功，无网络请求。官方tox用nose2，本轮未声称nose2/多版本矩阵通过。

证据：`.deploy/github-100-research/cli-config/furl/`。固定来源/commit、install与精确依赖、原生baseline日志/XML/命令/资源、原生observe.py/observations-result.json、review-result.json及SHA256摘要均保留。没有20步路线，未实施、冻结验收或接入。

重跑：clone官方仓库，detached checkout上述commit，独立venv用test-requirements.txt准备精确依赖后安装本地检出；在checkout以隔离HOME/PATH运行 `<venv>/bin/python -m pytest -q -ra`。原生场景另运行 `<venv>/bin/python <evidence>/observe.py`。未验证的其他Python/OS、发布、文档和风格/类型检查保留未验证。

未改上游源码、业务、账号、系统shell或生产数据；未创建task、提交/推送/部署、向上游发消息或进行平台评测模型调用。
