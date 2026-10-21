# 首批内容包模拟机制独立只读审计

## 当前状态

- 审计脚本：`.deploy/project-catalog-pilot-pack/audit_mechanism.py`。
- 本审计不属于正式 Check-All，不执行模型／原生任务，不调用业务写接口，不修改数据库，也不改变浏览器等待门禁。
- `run-002` 是已失败的旧试跑，仅用于核对真实快照结构和验证审计器不会把未完成产物判为通过；其结果保存在 `mechanism-audit-run-002.json`。
- `run-004` 在真实 `browser-ready` 后完成快照审计，最终归档后又按同一脚本复核：`mechanism-audit-run-004-snapshot.json` 与 `mechanism-audit-run-004.json` 均为 `passed`，各 1,074 项核对、零失败。最终归档的 `browser_status=passed`；浏览器自己的 790 项核验和 35 张截图由观察代理执行，独立机制审计不冒充页面检查。
- 完整只读备份在 `.deploy/project-catalog-pilot-pack/audit-snapshot-run004/`。`copy-receipt.json` 证明 3,856 个文件、1,469 个目录、零符号链接的复制前源、复制后源与备份逐路径／字节 SHA 一致；来源未修改。该备份消除了最终浏览器完成后自动清理 live root 的竞态。

## 已核对的真实契约

1. `project_scenario_tasks.result_json` 保存实际 `decision/outcome/feedback_codes`；任务定义的 `outcomes` 不是运行结论。只读任务通过后 `accepted_checkpoint_digest` 必须为空。
2. `project_evaluation_jobs.evidence_json` 实际保存 `parent_code_job_id/parent_code_digest/input_checkpoint_digest`；审计逐作业沿真实同场景接受来源核对，不仅查看任务声明的 `requires`。
3. 代码交接文件为 `project-artifacts/task-inputs/<id>/code-dependency.json`，包括 `dependencies` 作业 ID 到摘要映射和 `base_checkpoint_job_id/base_checkpoint_digest`。Jinja M02 必须指向同场景已通过且真实已接受的 M01。
4. `disclosure:<branch>` 投递行表示披露意图，本身可以保持 `pending`。实际消费需要匹配随后同任务、同 prompt 的 `candidate:*` 行，再通过 `consumed_source_id` 和原生日志精确字节区间证明。
5. `database-facts.json` 不包含 `project_task_deliveries`。审计仅对已保存的 `private-synthetic.sqlite` 使用 URI `mode=ro&immutable=1` 查询该表，不访问活动库。
6. 候选和评审计量按 `project_execution_sources.evidence_start_json/evidence_end_json`、固定 session 的精确原生范围独立重算，以 session/message ID 去重。未知字段保留 `null`，不会用零回填。
7. 预算从 `project_work_segments` 重算 confirmed、尚未结算的 reserved 与 policy 剩余额度，并分别核对任务累计、冻结回答评审累计和逻辑评审尝试上限。
8. 工程接受还核冻结业务验收、完整原生回归、节点数／集合摘要／合同摘要，冻结文件清单与每个内容对象的 SHA；计量完整不等同于模型质量可信。

## 回放支架审查及已报告事项

- 已发现并向主代理报告两项确定阻断：最终 SQL 误将全部 85 行与 66 条 selected 路径比较；单项目阶段固定 `concurrency=2` 超过实际合法容量 1。均由主代理修正，审计代理未改共享支架或产品。
- 已报告并由主代理修正三项证据／时序问题：首批防重放只查第一个实例；相同项目的跨批次用量截图覆盖；切换同名项目实例时只等待标题导致旧 DOM 竞态。
- 最新配置把原五个阶段按不同项目合并为三个阶段，独立从正式 manifest 的实际入口推导得到 `37 / 15 / 14`。总计仍为 66 条选中路径、37 项唯一任务、85 行任务记录、7 个项目实例、六个唯一工程目标及 10 次修改接受目标；没有减少业务路径。
- 已只读核对最新支架保留容量 2、私有会话隔离、同实际模型和每路径一次业务尝试断言。旧 `TY-M01` 超时分支在本内容包不可达，不能作为本轮超时恢复证据。

## 本轮实际结果

| 项目 | 实测结果 |
| --- | --- |
| 阶段与任务数量 | 37／15／14，共 66 条选中路径，37 项唯一任务；85 行任务元数据中 19 行未选，不计业务任务 |
| 类型 | 理解 5、咨询 9、诊断 11、方案 6、修改 6，均按唯一任务统计 |
| 工程接受 | 10 次实际代码接受对应六个唯一目标；56 条只读路径没有接受代码检查点 |
| 必要材料 | 八次披露全部经实际 candidate 投递和精确原生日志证明消费，覆盖五个不同分支；逐路径核对所需分支及材料片段 |
| 信息不足 | task 41 `JI-D01`、task 53 `TD-D01` 实际 `result_json.outcome` 均为 `insufficient_information` |
| Jinja 接受来源 | M02 评测作业 28 的真实父作业为 15，M02 作业 51 的真实父作业为 46；均为同场景已接受 M01，交接映射、源身份、父摘要、输入摘要和对象字节相符 |
| 独立场景 | TinyDB／schedule 的全部输入源码与各自 seed 的 `library/` 一致，且没有继承代码父作业 |
| 上游原生合同 | 十个接受路径全部有实际业务及完整冻结集合通过证据；TinyDB 228、Jinja 911、schedule 81 节点，集合及合同摘要均吻合 |
| 候选／评审计量 | 各 74 个来源和 74 次已知响应，覆盖完整；各输入 518、输出 814、缓存读／写 0／0，均为 mock 原生日志数值 |
| 预算 | 任务累计 confirmed／reserved／remaining、冻结回答评审累计、逻辑评审尝试上限全部对账通过，未知字段未补零 |
| 运行身份 | 148 个 Run 全为 mock；真实模型推理与 OAuth 调用均为零 |
| 内容对象 | 9 份冻结清单、213 个去重内容对象核对原始字节 SHA 通过；十张表的 JSON 事实与保存 SQLite 完全一致 |

Jinja 质疑路径的实际披露顺序为 `certainty-challenge` 再 `incident-evidence`，所有 66 条路径的业务尝试均为一次。候选及评审回答还从冻结 `response_key` 的原生字节位置回读，分别核对回答摘要、评审依据摘要及真实作业归属；没有只看任务配置就宣称父链成立。

## 最终归档复核与清理收据

最终浏览器结束且 `run-004/evidence` 归档完成后，已对归档重新执行相同只读审计：

```bash
python3 .deploy/project-catalog-pilot-pack/audit_mechanism.py \
  --run .deploy/project-catalog-pilot-pack/run-004 \
  --output .deploy/project-catalog-pilot-pack/mechanism-audit-run-004.json
```

- 最终报告 `snapshot=archived`、`status=passed`、`browser_status=passed`；1,074 项核对零失败。
- 归档与清理前独立备份的任务／路径统计、角色用量、Jinja 实际接受父链完全一致。
- 实际 `run-004/cleanup.json` 为 `passed`：本次归属容器剩余零，临时 runtime 与服务令牌已删除，`production_touched=false`、`real_model_calls=0`。清理由原支架完成，审计代理仅读取该收据。
- 审计全过程没有修改 gate、数据库、任务定义或产品，没有发起业务写请求。模拟回答、评审和 token 值不能用于真实质量或成本结论。
