# Python Constraint 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./python-constraint-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[python-constraint/python-constraint](https://github.com/python-constraint/python-constraint)和[完整提交](https://github.com/python-constraint/python-constraint/commit/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b)已网页核对。固定`d91ba03d1fd6acc30d64fd9d513dc0523f697b5b`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-constraint/source`工作树干净。BSD二条款，保留LICENSE和源文件Gustavo Niemeyer2005-2014归属；扫描核心和示例未见另列vendor许可。当前pyproject发行名python-constraint2、版本2.7.3，同一官方仓只计一次，非另一个项目。

## 源码、依赖与成本

已读Problem变量域/约束接入、结果格式、_getArgs预处理、Domain隐藏状态栈、基础/优化/递归/最小冲突/并行solver、固定/变量sum与product剪枝、集合约束及parser把正常算式转换为内建约束的路径。研究只围绕小型有限域排班和数值模型，不研究网络或账户机制。

实际跟踪85文件、8035989字节；独立测试venv 52373087字节。运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装66.308秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

遵循上游nox的Python3.12编译扩展配置，完整pytest --no-cov：52通过0skip，包含线程/进程solver、真实examples、3个benchmark及test_doctests中的README和核心模块示例。没有绕过3.12原生coverage门槛：上游本来对C版关闭coverage，80%门槛另属最后3.14纯Python任务。 实际52通过、0跳过、0失败、0错误。墙钟33.945秒，pytest XML时间33.212秒，进程峰RSS 190396KiB；容器预算768m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实排班tea/review取9/10/11、AllDifferent和review>tea，实际解恰好(9,10)/(9,11)/(10,11)；probe确认problem/solvers由/source/constraint下本次构建.so加载，check_if_compiled=True。逐项实跑负系数漏解、重复求解约束累加、单列投影、域生成器行为等。安装重生五个已跟踪C文件，已先保存installation-generated-c.diff，再仅还原本轮编译造成的五文件变更；Python业务源码及测试未改，工作树干净，实际so仍来自本次冻结Python源码构建。

## 路线真实性与限制

已支持字符串普通算式优化、变量目标sum/product、负数域、MinConflicts自定义rand、OrderedList导出和并行线程/进程模式；不把这些现成能力重新计入。带负系数仍有独立实证问题，按统一加权界修复合并。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。4项实跑问题，其余为显式增强。4项实证修复和16项完整工程增强；求解限制、临时假设、表约束、基数/容量调度和最优解有不同可见行为和独立验收。

- 原生有6条warning，关于实验字符串能力或并行solver性能的提示，已保留完整log，不声称无warning
- 未运行nox末项Python3.14纯Python80%coverage任务、ruff及全部Python版本；本轮只认证正式3.12编译扩展集合
- 保留生成C差异作为安装证据；未来累计修改Python实现时需要重新构建扩展并验证候选加载路径
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-constraint`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-constraint/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-constraint --memory 768m --tests tests
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-constraint/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/python-constraint
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
