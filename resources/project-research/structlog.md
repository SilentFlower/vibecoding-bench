# Structlog 单仓研究

研究日期：2026-10-21。来源、适用原生基线和20步路线已研究；路线未实施、独立冻结验收未制作、平台未接入。

## 来源、固定版本与许可

官方仓库：[hynek/structlog](https://github.com/hynek/structlog)；固定[完整提交](https://github.com/hynek/structlog/tree/19c4f21059e853114efa7a93b6e675d93bf7934e)：`19c4f21059e853114efa7a93b6e675d93bf7934e`。仓库网页、pyproject项目链接和真实git origin交叉核对。许可证 MIT OR Apache-2.0，保留 LICENSE-MIT、LICENSE-APACHE、NOTICE、COPYRIGHT 和源码SPDX归属；tracebacks.py 已说明源自 Rich 的实现及贡献链接，不能删掉归属。文档赞助标志不作为运行时素材分发。

用途为结构化日志库，可绑定业务上下文、顺序处理事件并输出JSON/控制台/标准logging。研究只覆盖普通日志字段处理、时间、上下文、易用性和性能诊断。

## 实测规模与成本

跟踪123文件、2197922字节；产品Python源码7354行。Python3.12.3，独立venv安装21.776秒，含测试工具环境90647001字节。运行时Python3.12无强制第三方依赖，测试安装pytest/asyncio/randomly、simplejson、time-machine、Rich与Twisted并精确freeze。Twisted在这里只运行库内测试，不需要外部服务。网络安装成本受缓存影响，不是每次离线运行成本。

已读取BoundLoggerBase、BoundLoggerLazyProxy、Processor/EventDict类型、同步/异步原生wrapper、渲染器、上下文函数、捕获器、输出logger的实际定义。get_logger已支持绑定、ainfo等已有异步快捷方法、JSON自定义serializer、__structlog__、字段排序和按处理器DropEvent均属既有能力，不重复计入路线。

## 实际原生基线与使用场景

原生`pytest -q -ra -p no:cacheprovider --junitxml=/tmp/results.xml tests`，完整上游tests集合，**928通过、21跳过、0失败/错误**，无xfail和subtests。容器执行Python3.12.15，离线容器UID1000、只读根、512MiB预算，不挂业务目录；墙钟4.169秒，pytest 2.632秒，RSS 57148KiB，容器已移除。21项skip逐条见原始日志：12个可选JSON后端参数项；better-exceptions3项、Windows/colorama3项、需要缺失Rich的反向对照1项、缺greenlet1项、Python3.15+懒导入1项。未跑其他Python/平台、typing_tests、多mypy工具链、文档doctest/lint和bench。

真实订单场景把“示例订单”公共batch与单条“结算”组件、quantity=2和完成event合并，实际输出并解析JSON，确认level=info、中文保真及源模块`/source/src/structlog/__init__.py`。原版还实证drop_missing=True错误丢掉显式None、嵌套bytes未解码、Decimal默认repr、Logfmt容器默认str。前者列为文档契约修复，其他为明确可选增强，不把默认选择误报缺陷。

## 路线与证据

[20步路线](./structlog-roadmap-20.md)含1项实证修复与19项本地增强；每项交付包含正常/边界验收、真实模块、原生回归和兼容限制。20步在同一仓累计，功能没有强制的先后依赖，不把相邻编号伪装为业务依赖。尚未实施，原生通过不等同模型完成。

证据根：`.deploy/github-100-research/resume-main/structlog/`，源码为其中`source/`。`repository.json/revision.txt`、`installation.json/install.log/requirements-frozen.txt/test-requirements.txt`、`size.json`、`baseline-tests.log/xml/baseline-result.json`、`observe.py/observations-result.json`、`roadmap-20.json/review-result.json/evidence-sha256.json`保存实际来源与结果。

可重建：从官方仓clone后checkout上述完整SHA，用Python3.12新建venv并安装固定test-requirements与原生源码；在checkout中执行上述pytest命令。当前机复跑容器证据：

```bash
.deploy/github-100-research/resume-main/control/bin/python .deploy/github-100-research/run_python_baseline.py baseline .deploy/github-100-research/resume-main/structlog --memory 512m --tests tests
.deploy/github-100-research/resume-main/control/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/resume-main/structlog --memory 512m
```

证据/venv是本机可重建资源，不是跨机器源码或依赖发行物；离线依赖准备、平台原生加载适配与独立冻结验收仍待后续实施。正式项目库未修改，未提交/推送/部署。
