# 候选审查：tomli-w

状态：**不计入研究完成数**。原生基线和入口通过，但在其有意保持很小的纯写入边界内尚未形成20个独立有效交付，暂留候选，不把格式参数或测试维度硬拆成20步。

官方来源：[hukkin/tomli-w](https://github.com/hukkin/tomli-w)，固定 [1210bb6f5708a4dc084cc3deb4a3a3e3939f4d6d](https://github.com/hukkin/tomli-w/tree/1210bb6f5708a4dc084cc3deb4a3a3e3939f4d6d)。MIT，版本1.2.0，核心src/tomli_w/_writer.py已完整读取；仅dump/dumps两个公开入口，已有indent、多行字符串、Decimal、AoT启发式、Unicode转义。完整原生269通过、2个上游已知极深递归xfail（非普通跳过）。BytesIO写TOML再由标准库tomllib读回中文嵌套配置通过。实测有tzinfo但utcoffset为None的朴素time被误拒，与开放PR84线索一致；单个问题不足20步。不把注释保真编辑／完整parser等另一个项目定位强塞进来。

使用无业务祖先的临时检出、独立HOME和venv；安装 4.95 秒、环境 50135559 字节（含测试依赖）。没有挂账号、真实.env或secret；使用场景仅为合成临时数据。未执行正式账号镜像、全平台矩阵、类型／风格／文档检查。本轮未给出20步有效路线，未实施、冻结验收或平台接入。

证据根：`.deploy/github-100-research/cli-config/tomli-w/`。repository.json／issues.json／revision.txt、source-path.txt、size.json、installation.json／install.log／requirements-frozen.txt／test-requirements.txt，及baseline-tests.log、observe.py／observations-result.json和review-result.json均保留。未把预期失败改成普通通过。

重跑：clone上述官方仓库，detached checkout完整commit，建立独立venv，用`<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>`准备依赖，再在checkout运行`<venv>/bin/python -m pytest -q -ra`。原生使用场景另运行`<venv>/bin/python <evidence>/observe.py`。

未改上游源码、正式库、账号或生产数据，未创建task、提交／推送／部署、发上游消息或进行平台评测模型调用。
