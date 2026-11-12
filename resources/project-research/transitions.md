# Transitions：真实 GitHub 项目研究

来源、许可、固定源码、适用完整原生集合与本地订单流程已核对，形成[20项独立路线](./transitions-roadmap-20.md)。**仅研究，未实施路线，未冻结新增验收，未接入正式库。**

## 来源、许可与规模

官方 [pytransitions/transitions](https://github.com/pytransitions/transitions)，完整commit `bd42b38f3627e6bca7274fb4d9af2e105f75da7c`。主仓[LICENSE](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/LICENSE)为MIT，保留Tal Yarkoni/Alexander Neumann版权。读取真实State/Condition/Transition/EventData/Event/Machine定义与执行、队列、模型绑定、Markup和experimental代码生成实现；核对Async回调/队列、Timeout/Retry、层级状态与图输出入口，未按包名猜能力。

跟踪82文件、2139911字节，39个Python文件共12562行。独立venv51086121字节，初始安装12.467秒；实际依赖版本及下载制品见requirements-frozen.txt/installation.json。Graphviz本地研究镜像构建62.75秒，镜像总319564725字节（不是新增层大小），成本与Dockerfile/日志保留resume-main/runtime-graphviz；未发布或部署镜像。

## 实际原生基线及限制

复用已通过的原样完整tests收集：**2923主项通过、291普通条件skip、0xfail、0xpass、退出0**；50.91秒，最大RSS65672KiB，512MiB离线只读容器/临时可写源码副本。完整当轮log/JUnit保留，前期依赖不齐失败也保留；没有重复已经通过的长测。该镜像实际Python3.12.15另行读取sys.version确认，宿主安装/业务观察Python3.12.3分开记录。

291项skip全部核对原XML为pytest.skip：pygraphviz不可用112项，NestedGraph需要pygraphviz91项，Graph需要pygraphviz86项，mypy缺少2项。**pygraphviz可选后端与mypy检查未通过本轮验证，不能宣称所有可选环境全过。**Graphviz和Mermaid适用集合实际执行，原测试未删除/筛除。未来相应后端路线需准备该可选依赖再冻结验收。

本地合成订单实际从draft经packed到done，AsyncMachine成功迁移，Mermaid真实生成当前/上一状态图；没有远程流程或真实业务系统。observe.py对20条路线实际记录原版返回/状态/异常及签名，结果见observations-result.json。

## 真实缺口与兼容

3项修复实际复现：Markup全局after导出误用before；remove_transition的State对象列表不删除；Markup/生成器就地pop调用者models配置。17项增强覆盖条件诊断/无副作用结构预览、队列结果/容量/控制、多模型结果、配置静态诊断/原子应用、状态快照/升级映射、历史、可控时钟、异步同任务模式、参数选择、声明异常路径、解绑生命周期和累计图覆盖。

原queued返回True、may执行prepare、remove_model保留方法、异常后不回滚均是明确现有约定，只提opt-in增强，未冒称BUG。Timeout/Retry、pickle/Markup、层级/并行、异步/锁、图形/代码生成已有且排除新增。新API名称为拟议契约；每项包含真实路径、原版观察、正常/边界验收、原生回归和实际依赖，20项都未实施。

## 证据与重跑

证据根.deploy/github-100-research/resume-main/transitions含官方仓库/commit/issue、许可源码、安装/冻结依赖、原生当轮及失败历史、runtime版本、20观察和20步JSON、review及SHA清单。项目根重跑业务观察：

```bash
PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-main/transitions/venv/bin/python .deploy/github-100-research/resume-main/transitions/observe.py
```

异机先从官方URL检出同commit，重建冻结环境及所需本地Graphviz制品，核对真实导入路径。本机路径与本地镜像tag不代表可移植交付。run_native.py保留实际原生执行机制；若未来复跑，必须先保留旧log/XML/result并清理当轮XML，失败不得误读旧JUnit。tracked源码干净，无正式库变更、路线实现、提交推送部署或上游消息。
