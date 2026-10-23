# Portion 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./portion-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[AlexandreDecan/portion](https://github.com/AlexandreDecan/portion)和[完整提交](https://github.com/AlexandreDecan/portion/commit/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44)已网页核对。固定`622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/portion/source`工作树干净。pyproject明确LGPL-3.0-or-later，LICENSE.txt保留LGPL3全文及其引用GPL3的说明，保留Alexandre Decan及贡献者归属。运行依赖sortedcontainers另为Apache2；没有将这些源码并入产品，后续发行应保留库许可和对应源码义务。

## 源码、依赖与成本

已读Interval原子表示、端点规范化、合并、交/并/差/包含、replace/apply、抽象离散端点；IntervalDict按相等值归并的SortedDict存储、点/区间查询、run更新、二表combine扫线；iterate与字符串/结构化IO和create_api。

实际跟踪26文件、304067字节；独立测试venv 52657666字节。运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装16.535秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

完整上游默认pytest230通过，11跳过均为pyproject明确--benchmark-skip的独立基准；保留CI的--cov portion并获得98%覆盖（无上游门槛），README doctest由test_doc.py原样执行。 实际230通过、11跳过、0失败、0错误。墙钟3.522秒，pytest XML时间2.544秒，进程峰RSS 74440KiB；容器预算512m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实日程busy=[9,11)|[13,14)，从[9,17)扣除得到[11,13)|[14,17)；重叠写入IntervalDict后9点open、10点meeting、11点恢复open；实际加载/source/portion/__init__.py。观察逐项核对当前API和源码，step0只用islice取有限3项，不启动无界测试。

## 路线真实性与限制

已存在集合代数、replace/apply、AbstractDiscreteInterval、create_api、iterate自定义step/base/reverse、IntervalDict.get补空隙、find、binary combine(missing/pass_interval)、to_data/from_data可配置无穷标记；20步只扩展明确新行为，不重复计这些能力。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。0项实跑问题，其余为显式增强。全部20项为显式增强，未将使用前提或参数校验缺失冒充已承诺缺陷。度量依赖端点协议，周期域不改变普通Interval，近似合并明确增加集合，分区返回序列避免自动归并，性能索引未宣称本轮提速。

- 未执行默认关闭的11个benchmark、ruff和其他平台；完整适用功能集合与README示例已执行
- LGPL库仅作独立研究，不等同于已决定正式分发方式或完成分发许可准备
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/portion`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/portion/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/portion --memory 512m
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/portion/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/portion
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
