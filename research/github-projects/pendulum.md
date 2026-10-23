# Pendulum 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./pendulum-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[python-pendulum/pendulum](https://github.com/python-pendulum/pendulum)和[完整提交](https://github.com/python-pendulum/pendulum/commit/e06dacedc4cdea90fa1286b3965d180ab94cf251)已网页核对。固定`e06dacedc4cdea90fa1286b3965d180ab94cf251`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pendulum/source`工作树干净。主仓MIT，保留Sébastien Eustace2015归属。clock明确从Babel/CLDR生成locale翻译与复数表达，不能把这些数据都称为MIT原创；本轮核对poetry.lock的Babel2.18.0原始BSD3代码许可和其locale-data/LICENSE.unicode的Unicode-3.0，全文保存于证据目录。历史各locale缺逐文件生成版本manifest，已记录该溯源限制；正式分发仍保留对应源归属/条款。

## 源码、依赖与成本

已读Duration分量/整数与float分解、DateTime日历/UTC运算、Interval端点/时差/迭代/相等哈希、Time.diff、parse多类型分派、格式token、人类差值、全局locale/week配置、ZoneInfo子类/from_file和Traveller。当前Rust helper来自pendulum._pendulum，纯Python模式按CI显式禁用扩展。

实际跟踪290文件、1118113字节；独立测试venv 52396104字节。运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装53.942秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

完整上游tests在Rust扩展和PENDULUM_EXTENSIONS=0纯Python模式各1871通过/3跳过；1个Windows专用、2个上游明确zoneinfo未来POSIX规则限制；没有自选子集。 实际1871通过、3跳过、0失败、0错误。墙钟8.818秒，pytest XML时间7.065秒，进程峰RSS 54048KiB；容器预算768m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实月末预约2026-01-31巴黎09点加1月到2月28日同一当地时间，转UTC08点，实际加载/source/src/pendulum。已实跑5项问题：跨类型hash契约、大时长微秒、减日历Duration经过DST、倒序成员、pickle/浅copy日历分量丢失；原生通过不等于这些新增目标已完成。

## 路线真实性与限制

已支持区分日历add(days)与实际add(hours)、Interval.range锚点月末恢复、ISO duration解析、ZoneInfo/Timezone.from_file及文件pickle、time-machine旅行、泛型注解；未将这些现成能力重复计入。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。5项实跑问题，其余为显式增强。5项原版实证问题和15项普通日历/排班增强；大时长的精确字段不把float total_seconds假称可无损，范围取点与连续分段语义明确分开。

- 未执行独立CI的mypy、lint、Codspeed基准、全量文档和全部Python/OS矩阵；两种运行实现适用功能集合均已执行
- 当前locale生成器锁定版本已核，但历史各locale的生成数据版本未逐文件记录，不声称全部历史数据都来自Babel2.18.0
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pendulum`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pendulum/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pendulum --memory 768m --tests tests
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pendulum/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pendulum
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
