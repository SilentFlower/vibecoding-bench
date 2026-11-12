# normality 候选：依赖准备未通过

官方 [pudo/normality](https://github.com/pudo/normality)，固定 `29333c9b1de4bc40489edeaa124112b0cfaaa316`。版本3.1.0/Python>=3.10，实际LICENSE为MIT，保留Friedrich Lindenberg/Gregor Aisch署名。27个跟踪文件、58707字节，Python产品1394行；pyproject Repository与官方网页/实际git一致，REST限流响应保留。

实际pyproject强制依赖banal、PyICU>=2.10、chardet、charset-normalizer；transliteration.py在import时直接创建ICU Transliterator，旧模块说明中的“有则使用”不再代表当前可选依赖契约。隔离venv的真实pip安装在PyICU构建阶段失败：宿主无可用pkg-config/ICU开发环境。日志和installation-result.json完整保留，没有改系统库、读取业务环境或假装存在纯Pythonfallback。

本仓未运行原生pytest或原生使用场景，未建立绿基线，没有20步路线，**不计入100**。后续若重新评估，应先提供固定ICU工具链/镜像及真实构建成本，再跑源码测试与转写/编码/slug场景；不能把每种字符集或测试维度各算一步。

证据根 `.deploy/github-100-research/data-tools/normality/`：固定source/revision、size、metadata请求结果、install.log/installation-result及review-result.json。未修改源码、生产平台或总进度，未推送/部署/上游发消息。
