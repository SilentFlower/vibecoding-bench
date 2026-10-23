# Python Statemachine：真实 GitHub 项目研究

来源许可、固定源码、完整适用原生收集及真实本地订单场景已核对，形成[20项路线](./python-statemachine-roadmap-20.md)。**仅研究，未实施路线，未冻结新增验收，未接入正式库。**

## 来源与规模

官方 [fgmacedo/python-statemachine](https://github.com/fgmacedo/python-statemachine)，完整commit `ec5d8173f740b37941818df13727db9d64ef498d`。主仓[LICENSE](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/LICENSE)为MIT，保留Fernando Macedo版权。读取真实StateChart/StateMachine/State/Transition/Configuration定义、engine队列/微步及invoke/timeout实现，核对factory图验证、IO格式中间模型与已有Mermaid伪态渲染；不是按包名猜功能。

跟踪718文件、3238081字节，274个Python文件共44248行，独立环境180654742字节（初始量测），初轮安装28.019秒。依赖冻结与后续补齐Sphinx的日志/制品保留，含pytest、benchmark、asyncio、Django、pydot、PyYAML、jsonschema等。安装与业务观察使用宿主Python3.12.3，原生镜像为实际已验证的Python3.12.15；运行时证据引用同完整镜像的sys.version，不混写。

## 原生基线与边界

复用上游默认完整收集，包含模块与Markdown doctest及原生benchmark：**2810主项通过、189普通skip、126xfail、0xpass，退出0**；212.823秒，最大RSS240028KiB，768MiB离线只读容器/临时可写源码副本。未重复已经通过的长测，原源码和测试未改。原JUnit的315个skipped节点已拆为189普通skip与126xfail，逐例类型/原因封存native-conditional-cases.json，原XML/log未动。

初轮缺依赖收集失败保留dependency-first-attempt，补齐Sphinx后原默认集合通过。本轮结果不代表条件跳过或UML语义xfail通过；路线中的completion、活动时序、deferral、junction/choice/join、entry/exit、terminate和call事件正对应当前原生已标注的限制。空xfail原因也保留原例名，不补造说明。未来交付必须实际固定状态和动作轨迹，不能只移除xfail。

observe.py真实同步订单返回quantity=2并到done；异步订单返回quantity=3并终止；复合编辑配置实际为editing+draft。20条原版观察保存observations-result.json。多目标fork使用各区域唯一状态值复现billing_complete不可达；早期同名子态夹具会合并存储身份，不用于最终缺陷结论。

## 路线真实性与依赖

1项修复是图验证只遍历多目标迁移首目标。其余19项明确是增强：快照/模型存储、状态数据与继承组合，以及官方普通状态流程研究中的UML节点/生命周期语义。现有SCXML/JSON/YAML、深浅历史、初始迁移、eventless/done.state、invoke/timeout、延迟/取消、参数注入、async Future、pickle和图输出全部排除新增；尤其普通send返回值已经实际验证，call-event只提额外调用/回复协议。

每项包含真实模块、原观察、正常/边界验收、原生回归及实际依赖。完成/活动/deferral、图复制/嵌入/运行时区域、junction/choice/join/连接点等有真实功能前置，已逐条列ID，没有虚构为完全独立。各项是单独可验收能力，不把代码/测试/文档或一次报错拆步。已有图模型可渲染部分choice/join外观，不算这些运行语义已经实现。

## 证据与重跑

证据根.deploy/github-100-research/resume-main/python-statemachine含来源/commit/issue、许可源码、安装及补依赖/冻结制品、完整原生log/JUnit/result、条件例清单、运行时、20观察和20步JSON、review与SHA。项目根可运行本地业务观察：

```bash
PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-main/python-statemachine/venv/bin/python .deploy/github-100-research/resume-main/python-statemachine/observe.py
```

跨机器先检出官方同commit、按最终冻结依赖重建环境、核对导入路径；本机路径不保证可移植。若未来复跑run_native.py，先归档旧log/XML/result并清理当轮XML，失败不得误读旧JUnit；未来冻结还需离线制品。tracked源码干净；未改正式库、实施路线、提交推送部署或发上游消息。
