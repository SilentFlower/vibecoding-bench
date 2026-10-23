# Arrow 单仓研究

研究日期：2026-10-21。真实来源、固定源码、完整原生测试及覆盖率门槛、业务场景与[20项路线](./arrow-roadmap-20.md)研究完成；未实施路线、冻结新增验收或正式接入。

## 来源与许可

官方[arrow-py/arrow](https://github.com/arrow-py/arrow)与[完整提交](https://github.com/arrow-py/arrow/commit/2224255c4acc594d734cef0bbc83360452a67983)已网页核对。固定`2224255c4acc594d734cef0bbc83360452a67983`，真实检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/arrow/source`且工作树干净，项目版本1.4.0。Apache-2.0许可，保留根LICENSE和Chris Smith及维护者/贡献者归属；arrow/tests扫描未见另列vendor/样本许可。dateutil/tzdata等依赖各自保持许可，不套用Arrow主仓授权。此轮只研究普通日期处理、展示、本地转换与发展步骤。

## 源码与成本

实际跟踪50文件、781828字节，测试venv 61355478字节。已读Arrow.shift/span/ceil/range/span_range/humanize/dehumanize、DateTimeParser模式生成/Match/token/datetime构建、TzinfoParser、ArrowFactory.get、Formatter和Locale分解/语言模板。运行依赖python-dateutil>=2.7及CPython3.9+的tzdata；当前已支持ZoneInfo，未重复提案。测试安装dateparser、pytest/pytest-cov/pytest-mock、pytz2025.2和simplejson，精确锁在requirements-frozen.txt。安装宿主Python3.12.3，耗时18.709秒；**测试容器Python3.12.15**，sys.version与镜像ID在runtime-verification.json。无需服务或云凭据。

## 原生基线与场景

上游pytest默认包含分支coverage与99%门槛。此次保留该门槛，仅设COVERAGE_FILE=/tmp/.coverage并把coverage XML/JUnit报告写到/tmp，避免只读源码上的输出错误。实际命令参数见baseline-result.json的pytest_arguments；完整tests **1904 passed、0skip/xfail、0失败错误**，覆盖率**99.93%**达到原生要求。墙钟55.391秒，pytest XML时间52.408秒，最大RSS 175140KiB；无warning。离线只读容器、UID/GID1000、512MiB无额外swap、pids128，无OOM且容器已删除。完整coverage XML已经拷出保存，不把报告重定向当作取消coverage。

真实业务场景：1月31日09:00+01:00按月shift到2月28日同一当地时间，转UTC为08:00，ISO字符串往返相等；加载路径`/source/arrow/__init__.py`。观察exit0、0.64秒、256MiB，容器已删除。逐项实跑数值dehumanize、偏移尾随、账期缝隙、日历分量、午夜DST、数字weekday、严格/匹配/展示选项等原版行为。原生通过只证明原版基线，不等于已完成路线。

## 20项真实性与边界

5项实证问题和15项增强，每项有来源/场景、原版/替代、交付、真实模块、兼容、正常/异常验收、原生回归与依赖。把dehumanize小数和负号视为同一数值语法交付。humanize日历分解与elapsed运算是显式新策略，保留近似和Python wall-time既有行为。CLDR为可选离线数据provider、GPS转换要求明确冻结闰秒表，均未声称当前支持；不做在线数据请求。未跑其他Python/平台、lint/mypy/docs和所有语言的人工语法审核。

## 证据与复跑

本地`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/arrow`保留baseline-tests.log/xml、baseline-coverage.xml、baseline-result.json、observe.py与观察日志/JSON、安装报告与依赖锁、size.json、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。复跑：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/arrow/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/arrow
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/arrow/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/arrow --memory 512m --tests tests
```

脚本保留原生99%门槛和安全临时输出位置。证据目录非跨机器发行包。没有实施路线、修改正式内容库、提交推送或部署。
