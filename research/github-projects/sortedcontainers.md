# Sorted Containers 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./sortedcontainers-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[grantjenks/python-sortedcontainers](https://github.com/grantjenks/python-sortedcontainers)和[完整提交](https://github.com/grantjenks/python-sortedcontainers/commit/3ac358631f58c1347f1d6d2d92784117db0f38ed)已网页核对。固定`3ac358631f58c1347f1d6d2d92784117db0f38ed`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/sortedcontainers/source`工作树干净。核心Apache-2.0，根LICENSE保留Grant Jenks2014-2024及官方许可链接。tests/sortedcollection.py明确借自Raymond Hettinger的SortedCollection；[原始recipe](https://code.activestate.com/recipes/577197-sortedcollection/)官方侧栏核为MIT，另列third-party-license-verification.json，保留作者和URL。

## 源码、依赖与成本

已读SortedList/SortedKeyList分块、二分、缓存key、排名索引、update拆合、切片/区间；SortedSet的_set/_list同步及集合运算；SortedDict的dict和代理排序列表、写入分支、视图和pickle。核心始终要求元素可比较、hash/key在存储期间稳定，刷新功能属于显式增强。

实际跟踪258文件、10685964字节；独立测试venv 51828899字节。运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装10.425秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

完整上游默认pytest集合366通过0skip，遵循tox.ini的docs/src/tests testpaths、模块doctest与*.rst doctest以及原有benchmark ignore清单；未缩减为自选smoke测试。 实际366通过、0跳过、0失败、0错误。墙钟7.351秒，pytest XML时间6.125秒，进程峰RSS 155012KiB；容器预算512m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实日程SortedDict插入900/1100/1000后区间[930,1100]返回1000和1100，popitem(0)删除最早900并保持顺序；加载/source/src/sortedcontainers。另外实跑不可比较写入后同步缺陷、反向集合运算、同key顺序与现有API签名。

## 路线真实性与限制

已存在MutableSequence继承、SortedDict union、key/bisect_key/irange_key、视图按索引切片删除、set代数、负索引、copy和pickle，不重复列为新能力。反向key下irange遵循排序键顺序，未据旧issue把该设计误称缺陷。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。2项实跑问题，其余为显式增强。2项实证问题和18项普通业务增强；范围删除已承认视图切片替代，SortedValuesView已明确是按键排序；合并优化只列可验证算法目标，未声称本轮有性能提升。

- 未运行独立benchmark竞争库、长时stress.sh、ruff/doc8/Sphinx/build/twine检查；默认pytest可收集的stress测试已原样执行
- 借用recipe的本地副本未附独立MIT全文，正式再分发时需按来源保留MIT条款与作者，当前仅记录研究事实
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/sortedcontainers`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/sortedcontainers/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/sortedcontainers --memory 512m
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/sortedcontainers/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/sortedcontainers
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
