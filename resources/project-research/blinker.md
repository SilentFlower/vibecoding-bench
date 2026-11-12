# 候选审查：Blinker

**不计入研究完成数**。Signal/Namespace刻意保持小型收发边界；虽发现嵌套muted上下文提前解除外层静音，但其余多数合理能力已有，未形成20个独立有效交付。

官方来源：[pallets-eco/blinker](https://github.com/pallets-eco/blinker)，固定 [c3364059663df1ddce32799d6b1922af89a345f6](https://github.com/pallets-eco/blinker/tree/c3364059663df1ddce32799d6b1922af89a345f6)。版本：1.10.0.dev。许可证：MIT；已读LICENSE.txt，2010 Jason Kirtland版权。跟踪27文件、261887字节；Python总1227行包括测试/工具，不能当产品行数。

适用范围与实际结果：完整原生pytest，含pytest-asyncio依赖，25通过/0失败/0跳过。 当前日志/XML记录25通过、0失败、0错误、0普通跳过、0预期失败，0.37秒。安装5.00秒、独立venv 50585916字节；安装/测试子进程共同观测峰值RSS 75724 KiB。环境Python3.12、Linux、无业务祖先的临时检出及隔离HOME。

已读Signal.connect/send/send_async、弱引用清理、set_class与muted；原生已有发送者过滤、连接上下文、同步/异步包装桥接、可替换有序set及连接/断开信号。实际合成事件返回HELLO，断开后无接收者。nested_mute_seen记录外层尚未退出即收到了事件，保留为单个BUG线索，不拆成嵌套层数步骤。核心无第三方运行依赖；测试pytest/pytest-asyncio。

证据：`.deploy/github-100-research/cli-config/blinker/`。固定来源/commit、install与精确依赖、原生baseline日志/XML/命令/资源、原生observe.py/observations-result.json、review-result.json及SHA256摘要均保留。没有20步路线，未实施、冻结验收或接入。

重跑：clone官方仓库，detached checkout上述commit，独立venv用test-requirements.txt准备精确依赖后安装本地检出；在checkout以隔离HOME/PATH运行 `<venv>/bin/python -m pytest -q -ra`。原生场景另运行 `<venv>/bin/python <evidence>/observe.py`。未验证的其他Python/OS、发布、文档和风格/类型检查保留未验证。

未改上游源码、业务、账号、系统shell或生产数据；未创建task、提交/推送/部署、向上游发消息或进行平台评测模型调用。
