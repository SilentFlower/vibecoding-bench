# 第二批内容包集成进度

完整Brief已展示并获用户“确认”，`task.py start`成功，任务in_progress。实施路由实际命中inline／route-prefs；主会话承担共享工具和集成，分仓内容按隔离文件所有权并行制作。

## 已有实证

- `.deploy/project-catalog-second-pack/baseline.json`保存旧六仓／六环境的1,448个工作区文件（含既有缓存）、原277个无关dirty的SHA，以及当前镜像实测；旧六仓内容逐SHA保持。最终catalog为v4-en的10／45／107，digest `600c930ff5d43986c4d841ee1612c4dbd83a318d7bd706b50666f7f8f116139d`。
- 当前目标镜像RepoDigest／imageId为 `sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216`，Python3.12.15、x86_64、SQLite3.40.1。历史宿主SQLite3.45.1不作为本轮环境结果。
- 共享可信runner新增四SUITES、dotenv独占venv的受控CLI／源码绑定与清理、Tenacity仅新套件的完整子测试合同；sqlite-utils明确加载实际Hypothesis插件。最终当前SHA `b3e75e056b684fa6d5a6a4871bf8793b8422d373460562110207612c97ba65c3`，旧六仓私有runner未改。
- 共享回归11项定向单测及相关内容／评测／场景／verifier共52项通过，完整日志 `.deploy/project-catalog-second-pack/focused-tests.log`。
- 四仓当前镜像原版完整校准已实际通过：dotenv288／288、TOMLKit1203／1203、sqlite-utils1513节点（1497通过／16有明确可选依赖原因的skip）、Tenacity185主项与15子测试全部通过。Tenacity实际XML185个testcase、suite汇总200，未重复计数。
- dotenv两独立参考各通过完整288项，TOMLKit各1203项，sqlite-utils各1513节点精确匹配原版通过／skip；原版目标失败、公开测试原版失败／参考通过及错误候选拒绝均有逐仓报告。Tenacity两独立参考也分别通过185主项／15子测试完整合同；其17个真实产品验证案例及公开目标测试的原版失败／参考通过均完成，详见逐仓admission。

- 独立来源审计重读1,375个上游文件及5份许可，Git blob SHA1／SHA256／大小与全集全部匹配。TOML子模块gen.py遗漏的执行位已按固定官方tree恢复0755，字节及catalog摘要不变；原mode差异证据保留。现有运行快照统一0644契约保持，该语料生成工具不在pytest执行链。

## 已识别的事实与校正

- dotenv上游四个文档link blob、Tenacity的README.rst link blob按原目标文本保存为普通文件，逐Git blob字节不变、来源mode及实际表示单列；没有创建不被内容快照允许的symlink，运行源码／测试／根许可不变。
- dotenv首轮oracle把目标Binding前缀空白误作非目标记录，SQLite首轮Falsey oracle混入TEXT亲和性转换；已按各研究的既有业务边界修正探针并定向实测，原失败证据保留，没有改seed或用错误预期放行。
- 第一版runner已校准dotenv／TOMLKit；第二版仅加sqlite-utils插件，其他套件行为不变。两仓最终参考在第二版完整回归通过，各报告明确初次校准与最终工具身份，不把第一版原始证据改写。
- 整包支架补充每review原始package字节和非敏感隔离观测。Docker的Mounts.Source为宿主路径，私有根先由控制容器data换算到宿主data，再双向检查父子挂载重叠；不比较两个命名空间的路径后误报隔离通过。凭据只归档key名，不归档值。

## 正在推进

四仓内容、环境、私有参考已准入并统一集成。正式fixtures无partial运行：50配方、58协议case、4项真实材料消费及12项缺材料反例均通过；暂停创建实测三stage为50／33／31条selected路径，150metadata，16次预期代码接受，runs=0。新旧发布共存、故障库历史200／新建503验证通过。临时Git索引与正式Docker忽略／COPY导出3,070内容文件全集及SHA一致，旧1,448工作区文件不变、真实索引不变。

`run-001`三stage50／33／31共114路径全部通过，16次代码接受／8唯一修改，98非修改路径零checkpoint，业务attempt全部1。真实现场UI1943检查／60图通过；独立快照3126检查通过，7056文件逐SHA相同。首审并发区间误口径及修正证据保留，实际工作窗口最大2，不宣称完整holder事件时间线已留证。harness已退出0并清理本次容器／网络／runtime／token，最终归档独立比较3126检查全通过：7056文件无增删，仅预期browser状态及逻辑27表完全相同的SQLite备份头变化，其他7054文件SHA相同。完整交付汇总见integration-report.md；正式Check-All已full通过，CHK／FBK均0，低风险DOC三组状态漂移已同步；Update-Spec已最小更新现有project-iterations.md并反查源码／空白通过，用户已确认精确Git计划，1,631个业务文件已提交并推送，任务完成记录随独立提交交付。

真实模型、OAuth、生产写入和部署均为零。授权业务Git交付已完成，原277个计划外dirty保持；提交期间另有24项计划外工作流变更出现，未纳入本任务。母任务继续深化43～93项独立任务；本记录不替代已通过的正式Check-All。
