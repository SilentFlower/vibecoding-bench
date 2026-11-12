# 候选审查：diskcache

状态：**不计入研究完成数**。完整适用原生集合仍有未解决失败：默认并行1失败，重跑串行3失败；研究完成=false，不计数。

官方来源：[grantjenks/python-diskcache](https://github.com/grantjenks/python-diskcache)，固定 [ebfa37cd99d7ef716ec452ad8af4b4276a8e2233](https://github.com/grantjenks/python-diskcache/tree/ebfa37cd99d7ef716ec452ad8af4b4276a8e2233)。Apache-2.0，版本5.6.3。Cache使用本地SQLite和文件，无独立数据库服务；本轮Django4.2测试需要本地Django依赖。原生临时Cache写入dict、关闭重开读回再删除通过。默认并行250测试通过、1失败、另12子测试通过；串行248通过、3失败、另12子测试通过，覆盖率98.81%达上游98要求。失败为Django过期、tutorial expire、fanout expire，不能靠去掉这些适用用例宣称全绿，也未擅自修上游。XML计入子测试，baseline-result中260通过为XML用例数，报告不与pytest主测试混淆。

使用无业务祖先的临时检出、独立HOME和venv；安装 15.26 秒、环境 82106796 字节（含测试依赖）。没有挂账号、真实.env或secret；使用场景仅为合成临时数据。未执行正式账号镜像、全平台矩阵、类型／风格／文档检查。本轮未给出20步有效路线，未实施、冻结验收或平台接入。

证据根：`.deploy/github-100-research/cli-config/diskcache/`。repository.json／issues.json／revision.txt、source-path.txt、size.json、installation.json／install.log／requirements-frozen.txt／test-requirements.txt，及baseline-tests.log、observe.py／observations-result.json和review-result.json均保留。diskcache的default-parallel-*保留首轮失败，当前baseline为串行重跑。未把失败日志替换成成功叙述。

重跑：clone上述官方仓库，detached checkout完整commit，建立独立venv，用`<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>`准备依赖，再在checkout运行`<venv>/bin/python -m pytest -q -ra`。diskcache可加`-n 0`复核串行，仍保留上游原测试及覆盖门禁。原生使用场景另运行`<venv>/bin/python <evidence>/observe.py`。

未改上游源码、正式库、账号或生产数据，未创建task、提交／推送／部署、发上游消息或进行平台评测模型调用。
