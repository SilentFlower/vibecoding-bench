# 真实项目审查：icalendar（Python）

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[collective/icalendar](https://github.com/collective/icalendar)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[3ecf079acba0e592ea6a40c456514984c8657852](https://github.com/collective/icalendar/tree/3ecf079acba0e592ea6a40c456514984c8657852)。
- 许可证：BSD-2-Clause。实读LICENSE.rst，为Plone Foundation 2012–2013版权及两条再分发条件；pyproject声明BSD-2-Clause且源码仓库URL一致。此项是collective维护的Python包；另名icalendar/icalendar的Ruby仓未纳入此项。
- 用途：解析、生成和编辑RFC5545日历、事件、待办、提醒与时区组件，并支持现版本已有的jCal/xCal交换和LazyCalendar延迟解析。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 783／2812954 |
| 产品 Python 文件／行数 | 313／52752（src/icalendar/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 17.282 秒，venv 60769656 字节（含本轮测试依赖） |
| 原生基线 | 21321 主项通过、0 失败、0 错误、42 普通跳过、597 预期失败、120 警告；JUnit共21960项，聚合skipped639；墙钟 86.612 秒，exit 0 |
| 测试峰值 RSS | 249408 KiB（容器测试进程观测） |

运行依赖python-dateutil、tzdata及本Python版本所需typing-extensions；原生测试另装pytest、Hypothesis、pytz和coverage，不需要外部服务。完整基线512MiB上限峰值249408KiB，墙钟86.612秒；业务场景独立256MiB成功。安装17.282秒，含本轮测试依赖；当前版本源码规模与完整测试成本据实保留，不把21k测试数等同全部业务功能覆盖。

完整遵循pyproject testpaths=src/icalendar/tests及其norecursedirs，未手工裁剪测试；上游原配置排除src/icalendar/tests/hypothesis和build，并忽略DeprecationWarning。597个xfail全属test_docstrings既有文档格式缺口。42skip包含1初始化TODO、16 xCal不适用URI/XML引用控制字符、2既知相等失败、11 pytz/时区生成TODO、6空参数集、4上游pytz-zoneinfo集成跳过及2Windows-only。120为上游GloballyUniqueTZIDGuessed时区猜测警告，完整日志保留。运行pytest集合，未执行tox coverage统计门槛、mypy、Ruff、文档构建或其他Python矩阵。

## 源码与真实场景

实际读取Calendar/Event/Component与Todo/FreeBusy的字段和公开方法、日期锁定setter、attendees参数保留、提醒计算、惰性策略、解析器栈、折行/展开、共享TZP缓存、CLI和相应原生测试。原版已支持jCal、xCal、LazyCalendar、with_uid、深层相等、日期/时长getter与setter、时区缺失补全和提醒时间，均不重计。两个缺陷分别由原版CLI与对象日期语义对照，以及组件错配仍被无诊断接受实证。其余18项明确为业务或维护增强，其中复发窗口查询注明README已推荐现成生态库，不声称原包或生态从未有过。

原版构建中文资料整理日历与明确UTC的一小时归档讨论，validate后写calendar.ics再读回，UID/中文摘要/开始结束一致；to_jcal/from_jcal、to_xcal/from_xcal真实往返成功，LazyCalendar.with_uid亦找到原事件。额外使用合法无DTEND全天事件对比对象duration=1天与CLI的0天；错配END示例真实被接受且errors空。observe.py记录20项公开边界，加载/source/src/icalendar/__init__.py，业务exit0。

完整 [20 步路线](./collective-icalendar-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/collective-icalendar/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/collective-icalendar/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/collective/icalendar.git <checkout>
git -C <checkout> checkout --detach 3ecf079acba0e592ea6a40c456514984c8657852
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

完整基线用run_native.py baseline <evidence> --memory 512m，临时可写副本供原生测试写入；业务用run_python_probe.py <evidence> --memory 256m。使用固定requirements-frozen，原pyproject的testpaths/norecursedirs/filterwarnings保持；不能把未执行coverage/mypy矩阵算作通过。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
