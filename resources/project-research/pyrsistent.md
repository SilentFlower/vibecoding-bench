# Pyrsistent 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./pyrsistent-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[tobgu/pyrsistent](https://github.com/tobgu/pyrsistent)和[完整提交](https://github.com/tobgu/pyrsistent/commit/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7)已网页核对。固定`0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pyrsistent/source`工作树干净。主仓MIT，LICENSE.mit载Tobias Gustafsson2023归属；内嵌_toolz.py明确从toolz复制并保留Matthew Rocklin2013的BSD三条款全文，不能仅按MIT处理。

## 源码、依赖与成本

已读PMap桶/evolver/update、PythonPVector树与evolver及C接口声明、PDeque双列表/切片/容量、PBag计数、CheckedMap/Vector/Set构造校验、字段类型缓存、PClass/PRecord的factory/initial/serialize及transform/get_in/freeze/thaw。Python/C两条向量路径由上游fixture原样覆盖，实跑确认默认向量来自pvectorc。

实际跟踪71文件、509834字节；独立测试venv 56738207字节。运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装12.69秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

完整原生tests含Hypothesis和Python/C向量参数：637通过、1跳过（Python分支不适用的C引用检查）；独立上游模块doctest另80通过。Hypothesis缓存仅重定向/tmp；未改源码/测试。 实际637通过、1跳过、0失败、0错误。墙钟10.91秒，pytest XML时间9.614秒，进程峰RSS 72688KiB；容器预算512m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实订单快照包含tea数量2，transform后新快照为3，旧快照仍2，thaw得到预期普通嵌套对象；实际加载/source/pyrsistent。另逐项运行5类问题、原子区间更新失败、pair更新、现有API签名与缺失入口；全部观察退出0。

## 路线真实性与限制

已存在get_in、PMap.__or__、pmap的pairs构造、两参transform匹配器、字段/全局不变量、PRecord/PClass多字段set和多重集运算，不重复计作新能力。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。5项实跑问题，其余为显式增强。5项实证修复和15项普通增强；字段缓存/pickle、原子变换、注解适配等需要独立设计和回归，不拆成测试/文档凑数。扩展为候选开发方向，不宣称上游承诺。

- 未运行tox的独立memory_profiler/性能基准、纯Python专用coverage环境、lint和完整Sphinx构建
- 模块doctest命名目标为3.13，此次只在实际3.12.15运行80项通过，不声称3.13已验证
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pyrsistent`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pyrsistent/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pyrsistent --memory 512m --tests tests
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pyrsistent/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/pyrsistent
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
