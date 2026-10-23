# 候选审查：filelock

状态：**不计入研究完成数**。完整适用pytest超过180秒预算，未得到完整收口结果；尚无20步有效路线，因此不准入。

官方来源：[tox-dev/filelock](https://github.com/tox-dev/filelock)，固定 [22f0776dd499690d71d2e6d2f95e1662a76db75d](https://github.com/tox-dev/filelock/tree/22f0776dd499690d71d2e6d2f95e1662a76db75d)。元数据与检出远端确认 canonical 为 tox-dev/filelock；pyproject 源链接中的 py-filelock 是旧配置，不能据此改仓库归属。纯Python、MIT；冻结22f0776dd499690d71d2e6d2f95e1662a76db75d，版本4.2.4。已读真实导出、BaseFileLock构造／获取释放和测试依赖；当前已有同步／异步、读写锁、软锁、owner marker、租约等大批能力，不重复提出旧功能。实际临时锁竞争：持有时另一锁失败，释放后可重新获得，结束无持锁。未跑Windows／FreeBSD／NetBSD。完整集合超时不是产品失败判定，不能从日志前缀数通过数；独占venv前缀进程清理检查无残留。

使用无业务祖先的临时检出、独立HOME和venv；安装 19.68 秒、环境 62407831 字节（含测试依赖）。没有挂账号、真实.env或secret；使用场景仅为合成临时数据。未执行正式账号镜像、全平台矩阵、类型／风格／文档检查。本轮未给出20步有效路线，未实施、冻结验收或平台接入。

证据根：`.deploy/github-100-research/cli-config/filelock/`。repository.json／issues.json／revision.txt、source-path.txt、size.json、installation.json／install.log／requirements-frozen.txt／test-requirements.txt，及baseline-tests.log、observe.py／observations-result.json和review-result.json均保留。filelock另有timeout-result.json；未把失败日志替换成成功叙述。

重跑：clone上述官方仓库，detached checkout完整commit，建立独立venv，用`<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>`准备依赖，再在checkout运行`<venv>/bin/python -m pytest -q -ra`。filelock须按预算有界运行，超时不得算通过。原生使用场景另运行`<venv>/bin/python <evidence>/observe.py`。

未改上游源码、正式库、账号或生产数据，未创建task、提交／推送／部署、发上游消息或进行平台评测模型调用。
