# Bidict 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./bidict-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[jab/bidict](https://github.com/jab/bidict)和[完整提交](https://github.com/jab/bidict/commit/299fedc89f1d70d5d41cf7922564b376d3e2d435)已网页核对。固定`299fedc89f1d70d5d41cf7922564b376d3e2d435`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/bidict/source`工作树干净。MPL-2.0，保留LICENSE与各源文件Joshua Bronson2009-2026通知。MPL按覆盖文件规定源码义务，未把本仓代码或未来改进并入产品；sortedcollections/sortedcontainers仅为测试配方依赖，分别保留其许可。

## 源码、依赖与成本

已读正反backing映射、懒创建/弱引用inverse、动态inverse class、去重策略、逐写unwrites回滚、single put与bulk路径、hashable frozenbidict、OrderedBidict环形节点/版本化迭代、views及custom mapping配方。

实际跟踪88文件、1027009字节；独立测试venv 88910473字节。Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装21.777秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

完整默认pytest1236通过0skip，包含docs/module doctest和原Hypothesis less-examples=200/100步stateful profile，warning按上游转error；仅把xdist auto限制为2workers、缓存放/tmp。上游tox先执行的ty检查已另在正式镜像用锁定0.0.84通过。 实际1236通过、0跳过、0失败、0错误。墙钟17.013秒，pytest XML时间15.07秒，进程峰RSS 57004KiB；容器预算768m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实商品标签T1->tea/C1->coffee，从inverse把coffee对应SKU改为C2，正表同步变T1/C2，两个方向迭代一致且inverse.inverse为同一对象。实际加载/source/bidict。原版循环重分配按现有逐项唯一规则拒绝并可靠回滚，列为新策略增强；20项观察均是实际API/行为核对。

## 路线真实性与限制

已支持OnDup三动作、可逐调用策略、原子putall/异常回滚、union、frozenbidict、可逆views、有序move_to_end/popitem、自定义backing mapping、Weakref和SortedBidict配方、动态inverse与pickle，不重复计为新增。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。0项实跑问题，其余为显式增强。20项全部为显式业务增强，未声称当前有实证产品缺陷。事务区别于已有putall；最终状态循环重分配保持现有putall不变；只读代理区别于已有frozen快照；有序整体重排区别于已有SortedBidict配方。

- 初次使用latest ty0.0.90出现4个__reversed__ override诊断；latest-ty-typecheck.log/result完整保留；对齐uv.lock的0.0.84后All checks passed，精确freeze和独立安装报告已刷新
- 未执行单独benchmark/Callgrind、coverage专用环境、Sphinx HTML和lint；pytest本身无skip/fail，报告峰RSS为pytest父进程而非全部worker累计
- 工具对齐额外安装未单独计时，installation-result原21.777秒只代表首次依赖准备
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/bidict`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/bidict/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/bidict --memory 768m
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/bidict/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/bidict
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
