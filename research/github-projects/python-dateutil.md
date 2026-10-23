# python-dateutil 单仓研究

研究日期：2026-10-21。固定来源、许可、适用完整原生基线、日常日历场景和[20项研究路线](./python-dateutil-roadmap-20.md)已形成；路线未实施、未冻结新增独立验收或接入正式平台。

## 来源与许可

官方[dateutil/dateutil](https://github.com/dateutil/dateutil)和[完整提交](https://github.com/dateutil/dateutil/commit/68994217fbe253835989e7c1e3eeef5c653088d1)已网页核对，固定`68994217fbe253835989e7c1e3eeef5c653088d1`，真实检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-dateutil/source`且工作树干净。**BSD-3-Clause适用于全部代码**；2017-12-01以后及明确重新授权的贡献还可选Apache-2.0，不能说全部历史代码均可任意选Apache。保留`LICENSE`、`AUTHORS.md`及各作者归属；`tz/_common.py`有Alexander Belopolsky tz项目改编来源，也保留。运行依赖tzdata2026.5自身有Apache-2.0许可，IANA版本2026e；其包内LICENSE和LICENSE_APACHE独立保留。源码测试资源的metadata记录2025b，更新脚本保留IANA来源，本轮不下载时区更新或执行归档程序。

## 模块与轻量成本

实际跟踪120文件、1133252字节；测试venv 59556810字节。已读`parser/_parser.py`字段结果和数字时区、`isoparser`周日期及分数、`rrule`构造/过滤/计数/缓存/文本导入、`rruleset`集合、`relativedelta`构造/归一化/相加/乘除、`tzical`组件、`TZPATH`、tzdata导入以及上游测试环境约定。生产依赖six>=1.6和tzdata；没有业务服务、数据库、云凭据或在线日历。独立安装14.738秒，依赖准备宿主Python3.12.3、实际测试容器Python3.12.15（runtime-verification.json保留sys.version及镜像ID），测试依赖来自requirements-dev，精确版本在requirements-frozen.txt。

## 原生基线、环境和场景

按上游tox的路径运行`pytest -q -ra -p no:cacheprovider --junitxml=/tmp/results.xml tests docs`，包含property集合。初次原镜像运行**8 failed / 4853 passed / 264 skip / 17 xfail**，保存在`initial-baseline-*`；五项由只读Hypothesis缓存warning转错误，两个由旧系统tzdb与新源码预期不匹配，一个是UTC本地缩写假设。第二轮配置可写Hypothesis缓存、冻结PYTHONTZPATH与TZ=EST5EDT后，仍有2项libc历史缩写不一致失败，保存在`tzdata-mismatched-libc-baseline-*`。最终用源码支持的环境变量`HYPOTHESIS_STORAGE_DIRECTORY=/tmp/hypothesis`、`PYTHONTZPATH=/dependencies/tzdata/zoneinfo`、`TZDIR=/dependencies/tzdata/zoneinfo`、`TZ=America/New_York`，让libc与dateutil读取相同数据后原样全套通过；没有改源码/测试、过滤warning或跳过失败项。这是冻结2026e数据环境的结论，原镜像旧系统tzdb兼容性仍不声称通过。

最终原生结果：**4861 passed，264 skipped、17 xfailed（JUnit skipped=281），0失败/错误，exit=0**。墙钟55.765秒、pytest XML时间53.217秒、最大RSS 105096KiB。离线、只读、UID/GID1000、512MiB无额外swap、pids128，临时容器已删除，无OOM。Windows、V1 TZif超范围与上游明确known failure等skip以及未实现解析器/规则功能xfail都按原样保留；日志和JUnit可区分，不能把skip称通过。未做其他解释器、Sphinx/docs/linkcheck、coverage阈值、打包和tz数据库最新分支矩阵。

新跑真实场景：巴黎每天09:00三次会议得到1月1/2/3日的+01:00日期，ISO解析偏移一致；1月31日加一个月得到2月28日。原生加载路径`/source/src/dateutil/__init__.py`，观察exit0、0.542秒、256MiB并删除容器。逐项复现HTAB折行、混合BYDAY、非法偏移、DST缺失时刻、无效第53周和X属性拒绝；其余路线为增强。毫秒、期间、严格顺序、精度策略都承认已有手工替代，不冒充当前API。

## 研究边界与证据

20项均有来源/业务场景、原版状态、真实模块、交付、兼容、正常/边界验收、原生回归和实际依赖；相同精度问题合并parse/isoparse、相对/绝对毫秒合并为一项。现有weekday序数、replace、TZPATH、tzfile.key和datetime_exists/resolve_imaginary未重新计为新能力。本轮只研究正常日期处理与发展步骤。

本地证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-dateutil`，包含baseline日志/XML/JSON、initial失败证据、观察脚本/日志/JSON、安装报告与依赖锁、源码规模、官方来源/许可核对、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。复跑：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-dateutil/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-dateutil
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-dateutil/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-dateutil --memory 512m --tests tests docs
```

环境调整已写入本地取证脚本，不修改冻结源码；跨机器仍须准备同一依赖与镜像。没有修改正式内容库、提交推送、部署或实施路线。
