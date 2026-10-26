# 第二批整包机制独立审计

当前状态：**run-001 gate独立快照与清理后最终归档均通过：3126检查／0失败，完整快照对照通过**。四仓50任务／19场景／8修改的最终内容及fixtures已由主会话冻结，目录为v4-en／`600c930ff5d43986c4d841ee1612c4dbd83a318d7bd706b50666f7f8f116139d`；静态三stage期望已独立推导，不代表实际运行或整包审计通过。

## 所有权与执行边界

本轮审计只读正式内容、产品、三件套及原始运行证据。仅写忽略目录中的 `audit_mechanism.py`、审计报告／独立快照，以及本报告；不启动业务／容器，不调用模型或OAuth，不执行Git写操作，不自行清理运行资源。正式Check-All仍由主会话负责，独立数据审计不替代它。

## 已准备的取证

脚本：`.deploy/project-catalog-second-pack/audit_mechanism.py`。沿首批原始SQLite／原生日志／冻结对象的方法，调整为python-dotenv、TOMLKit、sqlite-utils、Tenacity四仓，路径与接受分母动态读取阶段配置和正式manifest。

- 只用 `mode=ro&immutable=1` 加 `query_only` 读取封存SQLite，逐表比对JSON导出，并补读真实deliveries。
- 核每个candidate／review的source、严格释放、精确原生日志byte boundary与input_key／response_key，独立重算回答、对话和rubric摘要，逐文件核候选manifest／对象SHA及实际差异／授权。
- 实际材料必须有披露意图、后续consumed候选投递、真实用户日志正文与明确source；逐路径与配方核对，正常披露不增业务attempt。unavailable必须得到信息不足的合法结果，非修改零接受代码。
- 八修改从独立原版library开始；TK-P01的唯一answer依赖另核同场景、已接受TK-D02答案与原生session前缀实际保留，不把它伪装为代码父链。
- 每个已接受修改核真实business、完整主节点／结果摘要、JUnit元素及冻结合同；Tenacity另核15个真实子项的父节点、顺序、上下文和结果，不把200的XML汇总当200主节点。
- 原生日志按session/message去重重算token各字段，保留未知覆盖；按role／kind核API及详情。逐boot／monotonic原生计时文件与持久worksegment对账，重算任务、冻结回答及逻辑评审尝试三层预算，按实际boot内原生单调工作区间核并发上限，逐监督进程核严格退出；source创建／收账区间仅保留为诊断，不冒充holder精确区间。
- 按主会话新增实际观测schema逐review复核 `private-review-observations.json` 和原始 `private-review-packages/`。核每个source／run／job身份、包原字节SHA、同模型、UID／只读／cap／netns、输入不可见、PID命名空间分离；独立将runtime私有路径映射到宿主路径，与候选mounts按父子两个方向检查。凭据只检查导出的key名，不读取或归档令牌值。
- 全集证据审计前后SHA不变。浏览器gate时先独立复制完整snapshot，逐文件源／副本SHA和清单相等，拒绝链接／特殊文件及复制期间变化。清理后再次审计最终归档，并与快照比较；只有实际仅browser_status改变的result和逻辑全部表相同的SQLite备份头变化可解释，其余差异须失败或调查。

## 当前静态验证

AST语法解析和CLI帮助通过。只读重放首批已有原始证据，核148条输入位置和148个计时文件，共296个解析兼容检查，0失败；这是审计解析器兼容验证，不是本批模拟验证，没有启动任何业务。记录位于 `audit-static-check.json`。

已定向读取DE／TK／SQ的D01首问、分支和完整rubric，未发现将实际隐藏复现值或确定原因提前纳入通用规则；DE的源码引用为公开通用API政策。三仓只读规则无空静态证据却强制candidate_files的不可满足配置，也无将disclosure／私有reference路径直接作为无条件证据的情况。TN-D01最终首问、分支、rubric也已定向读取，未提前夹带实际JSON异常或特定predicate等隐藏事实；Tenacity冻结合同为185主节点／15子项，实际四次修改接受已在末节逐项核对。

## 最终fixtures静态预检

已独立从四仓manifest逐场景选择实际entry，核 `selected_task_keys` 顺序、kind分组、完整metadata行数及接受期望，与最终 `stages.json` 全相等：

| Stage | 选中路径 | metadata | 修改接受期望 | 非修改路径 | unavailable | 披露期望 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 默认 | 50 | 50 | 8 | 42 | 0 | 4 |
| 2 材料不足／只诊断 | 33 | 50 | 0 | 33 | 4 | 0 |
| 3 直接修改 | 31 | 50 | 8 | 23 | 3 | 1 |
| 合计 | 114 | 150 | 16 | 98 | 7 | 5 |

仍只计50唯一任务、8唯一修改；第三stage的TN-D01选diagnose_only，故再次ask／消费loader-evidence，其余三仓D01为unavailable。在没有恢复／重评的前提下，候选来源期望为54／33／32，共119；这是配方静态期望，实际来源数必须逐原生日志和SQLite取证。

完整预检与五份最终fixture文件SHA保存在 `.deploy/project-catalog-second-pack/audit-stage-preflight.json`。审计启动时会核这些冻结SHA、v4身份及所有实例／场景／任务的实际definition。最终private观测产生的28个字段与审计实际使用的28字段逐一静态核对，无缺字段；仅使用最终harness中真实存在的字段，不猜schema。原始package相对路径和SHA、宿主／runtime私有路径映射均已适配。

## 待运行入口

主会话通知真实browser-ready gate后执行，例如：

```bash
python3 .deploy/project-catalog-second-pack/audit_mechanism.py \
  --run .deploy/project-catalog-second-pack/<实际run目录> \
  --snapshot .deploy/project-catalog-second-pack/<新独立snapshot目录> \
  --output .deploy/project-catalog-second-pack/<snapshot审计结果>.json
```

最终运行和清理完成后：

```bash
python3 .deploy/project-catalog-second-pack/audit_mechanism.py \
  --run .deploy/project-catalog-second-pack/<实际run目录> \
  --compare-snapshot .deploy/project-catalog-second-pack/<上述snapshot目录> \
  --output .deploy/project-catalog-second-pack/<最终审计结果>.json
```

以下实际运行记录已从数据库／对象／日志核对检查数、路径、披露、接受、来源和清理后归档一致性。回答和token均为透明mock，审计结论不评价真实模型语义质量、评分可靠性或实际成本，亦不证明生产部署。

## run-001 gate实际快照审计

真实 `connection.json` 同时满足browser-ready文件存在及完整batch_ids=[1,2,3]后才创建独立 `.deploy/project-catalog-second-pack/audit-snapshot-run001/`，未写browser-done。完整快照 **7056个普通文件**，源在复制期间稳定、每个源／副本大小和SHA全相同；收据 `copy-receipt.json` 完整保存。审计期间副本全集SHA不变。

最终gate审计输出 `mechanism-audit-run-001-snapshot-attempt-002.json`：**3126检查，0失败**。原始SQLite逐表和公开投影、50/33/31选择路径、150metadata、36未选择、12实例、3批次均一致。实际114路径覆盖50唯一任务（7理解／11咨询／16诊断／8方案／8修改），98非修改路径接受代码为零；16修改接受对应8唯一修改，真实business及完整冻结回归均通过。TK-P01真实消费同场景已接受TK-D02答案的原生上下文1条；没有伪造code依赖或跨场景继承。

5次材料披露均由实际ask后consumed用户输入核实，覆盖4唯一分支，第三stage TN-D01再次披露；7条unavailable均合法insufficient_information，正常披露不增加业务attempt，全部114路径业务尝试一次。238实际来源＝119候选＋119评审，每条精确input/response字节、回答摘要、对话摘要、rubric依据、冻结对象／差异授权和完整包核对通过；核12个manifest／1270个冻结对象。119条实际private-review观测逐来源对应119原始包，UID／只读／cap／netns、候选无法读取输入、PID分离、宿主路径和mount双向不重叠、凭据key均通过，不归档任何令牌值。

候选和评审各119个已知请求，分别input833／output1309、缓存读写0；逐来源去重、role／kind、budget／worksegment及API／页面数据投影一致。上述token全为mock固定原生日志，不是实际模型成本。四次Tenacity修改接受各185主节点／15真实子项与合同精确相等，未误算为200主节点。

### 首审唯一失败及取证口径纠正

初次输出 `mechanism-audit-run-001-snapshot.json` 原样保留：2888检查中仅“实际来源区间共享容量”失败。首版审计把source.created_at至released_at误当holder区间，推得瞬时3。只读源码和原生进程证明表明：account_runtime.claim在环境锁／登记锁下检查siblings<cli_limit才登记；review claim后才插入source；cleanup先停止进程／私有容器，再release租约／移除holder，main随后释放sem、执行execution_released回调，回调观察输入／计时后最后才写source.released_at。因此source的尾部含holder释放后的取证收账延迟，不能将其重叠直接解释为实际三holder。

两段收账重叠完整保存于新报告capacity_evidence，不删除、不抹零：source52/53/54在1792604226.965515～1792604226.9659534，约0.000438452秒；214/215/216在1792607088.667532～1792607088.9239585，约0.256426573秒。旧review52原生工作结束mono50930.474726，新review54开始50962.007840；旧214结束53867.680716，新216开始53899.594718，未在这些原生工作区间同时执行。对应监督process-result真实cleaned=true／exit0。

修正仅在审计忽略脚本，未改产品／调度／租约、正式内容或实际运行。attempt-002独立按同boot原生单调起止重算 **实际工作并发最大2**；238个监督进程身份／source／PID／start tick／UID完全对应，均cleaned=true、exit0；harness观测共享holder最大2，硬门禁源码顺序、119个实际review隔离观测共同支持容量约束。**没有持久逐holder claim/release事件，无法重建其纳秒区间**，此限制与source收账最大3都明确保留。该修订不是凭采样2否定原始3，而是纠正不等价时间字段的审计假设；完整原失败仍可审查。

主会话实际完成浏览器1943检查／0失败并亲自释放gate后，审计等待真实cleanup.json确认归档及清理，再执行下述最终复核；审计未写browser-done或自行清理。

## 清理后最终归档复核

实际 `run-001/cleanup.json` 为passed，remaining_owned_containers=0、runtime_removed=true、temporary_token_removed=true；仅本次两个容器和内部网络已清理，production_touched=false、real_model_calls=0。在这些真实字段与归档 `evidence/result.json` 完整后执行既定 `--compare-snapshot`，新文件 `mechanism-audit-run-001.json` 返回 **passed／3126检查／0失败**，browser_status=passed。原首审失败和snapshot-attempt-002均未覆盖。

最终归档与独立快照均7056文件，无缺失、无新增、无意外变化；快照收据仍逐SHA精确相等。仅两文件出现有证据的变化：result.json仅增加browser_status=passed，其余字段全部相同；private-synthetic.sqlite文件备份字节变化，但SQLite完整schema及全部27张表的逐行内容相同（含sequence），故核为逻辑完全相同的重新备份。其余7054文件逐SHA不变。最终归档清单摘要 `4b2271e39327fbfe00174bfbbcf2b6dbe05afbb642465690315e91c4ea0b896b`；gate快照清单摘要 `4b48983e0c964ee7f2d3972a43d12493b8d482cdd927d440213f3f5ee068afbb`，差异明确保留。

### 容量证据分层与真实边界

1. **逐源真实运行证据**：238个同boot原生work起止和238个监督process-result逐身份匹配，实际工作区间最大2；每个进程cleaned=true／exit0。它证明实际已运行的工作和清理，不声称等于完整holder生命周期。
2. **本地共享holder与私有隔离观测**：运行harness采样最大holder2，119条实际private review逐来源对应，119个原包完整SHA与数据库／评审输入一致。此次账号 `cc2api_account_id=NULL`，初始化 **gateway=None**，使用本地合成共享holder；这些不是外部网关租约领取／续期／释放的实测，亦不推断真实模型吞吐能力。
3. **实际源码硬门禁及先后关系**：claim在环境锁／登记锁内检查siblings及cli_limit才注册；cleanup确认进程／私有容器退出，再release并移除holder；调度线程之后才写source记账释放。原生工作区间、清理及实际观测与该路径一致。未新增或修改这些产品逻辑。
4. **保留限制**：没有持久逐holder claim/release历史事件，无法重建完整holder纳秒时间线。source.created_at/released_at是含收账延迟的区间，最大3及两段短重叠作为诊断保留，不能冒称真实3holder，也不能用采样2抹去它们。首审错把二者等价的报告原样保存，修正理由可复核。

本次最终结论为**本地合成调度／评审／证据／预算／计量链路及真实原生验收一致**。模型回答与token为mock，真实模型语义质量、评分可靠性、实际token费用、外部网关租约及生产部署均不在本次证明范围。独立审计不是正式Check-All，由主会话继续对应质量收口。
