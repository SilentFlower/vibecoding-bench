# 第2阶段实施与验证

## 准备与启动

- [x] 固定本阶段三十仓来源及历史证据，拆为任务内部小批；母任务仍覆盖全部九十仓。
- [x] 由auto-loop prepare核readiness、刷新并展示Brief，仅按runner start_task／run_implement进入实施。
- [x] 进入trellis-route，按实际路由读取before-dev、当前实现及相关定义，明确本阶段真实变更范围。

## 逐仓和小批循环

对 `research/execution-batches.md` 全部小批重复：

1. [x] 核固定检出、commit、许可和实际入口；缺失时按固定来源重建，只用合成业务数据。
2. [x] 在目标镜像重跑原生基线和真实业务，封存精确离线依赖、资源、主／子测试与skip理由。
3. [x] 冻结逐仓场景任务表、材料／授权／合法结果及正反验收，再制作正式内容和必要最小原生适配。
4. [x] 验每个修改的原版失败、参考通过、错误候选拒绝和完整适用回归，问答验证可执行事实。
5. [x] 运行结构与受影响定向回归，真实产品链mock覆盖全部新增默认与必要分支，核UI／API／数据库和角色、材料、预算、用量。
6. [x] 核旧内容与历史读取、Git／Docker完整交付文件及SHA／权限，归档并清理；未通过仓继续保留未完成。

修改planning／handoff前用auto-loop decide声明精确文件并记录依据；其他队列项不改。阶段内全部三十仓完成前不提前结束本阶段，实际项目／场景／任务数按当前catalog重算。

## 验证入口

```bash
python3 scripts/validate-project-library.py
python3 -m unittest discover -s orchestrator -p 'test_project_*.py'
```

按真实改动选择定向集合，不无依据重复昂贵回归。原生业务使用 `scripts/validate-project-scenarios.py` 的真实项目、任务、镜像和证据路径，原版 `--expect failed`、参考 `--with-regression`。产品链沿已有隔离清单／mock入口，冻结实际可复跑命令、节点、镜像和资源，不使用虚构ID或历史计数代替当前结果。

## 检查与交付

- [x] 全部三十仓来源、独立任务、离线、原生、模拟及兼容证据齐全。
- [ ] 按runner action进入trellis-route(target=check)、Check-All及有限修复／重检，再同步新增原生合同规范。
- [ ] 按commit-only精确本地提交，由runner写完成态和Close，同名record成功后立即next。
- [ ] 本阶段结果交母任务最后整体集成，不push／部署，不把mock计为真实模型完成。

## 回退点

来源、候选绑定、原生集合或资源不符先留证并修根因，不删测试、降合同、换提交、增配额。单仓阻塞不从固定全集剔除；按runner有限重试和阻塞契约回写，不把部分成功说成三十仓已完成。

## 已验证事实

本阶段三十仓已全部本地准入，实际134场景／192任务，其中8修改；完整主执行98,924项与204条独立业务／候选路径逐项对账。15批实际产品链覆盖562路径、22次代码接受、8,953项页面检查与480截图。正式v24-en累计70项目／305场景／543任务，摘要6e6206d691130f74396a27a1234f9aaa72494f80cefaa7df0e1c596a101238c9。完整22,623文件在Git导出沿生产受限行尾恢复后与Docker COPY相同，既有11,373文件不变；Dateutil两份原始CRLF检出差异及精确恢复如实记录。实际项目144项、可信原生适配39项、部署30项测试通过；机器收据见research/all-thirty-formal-summary.json与focused-checks-current.json。检查后的规范、提交和确定性Close由runner继续记录；本段不将其提前计为成功。
