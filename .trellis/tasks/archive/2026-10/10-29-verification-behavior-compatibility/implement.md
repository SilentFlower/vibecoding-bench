# 实施计划

## 顺序

1. 固定 `research/inventory.json` 与 Docutils 线上证据，补齐待复核规则的公开来源和结论；检查任务创建前的既有未跟踪目录，不纳入本任务提交。
2. 在实施前进入 `trellis-route(target=implement)`，随后按 `trellis-before-dev` 载入本任务材料及后端约定；当前方案未请求子代理。
3. 为原生子测试/跳过记录实现共用语义比较和有界差异事实，补元数据重排、地址变动的正例与完整性反例。
4. 接入冻结回归器的精确来源适配，保留原始字节与结果；同步受影响未来副本，检查既有 Python、重复身份、SQLGlot、Arrow 适配仍可组合。
5. 修正 Palette、Bibtexparser、Click 的已核实非必要限制；完成其他静态命中分支的语义归因，只有证据和反例齐全的条目才改规则。
6. 通过真实业务观察器验证原版、参考、合理替代和真实错误四组案例；不得只检查新 helper 或源码替换文字。
7. 用原冻结 Docutils 候选及 more-itertools、pyparsing、wrapt 的固定原生输入进行真实禁网验证；记录实际执行摘要、计数与返回码，不改任何历史通过状态。
8. 进入 `trellis-route(target=check)` 做适当深度 Check-All，修复本任务发现的问题；更新审计报告与验证证据，再按规范评估 → 精确 Push 计划交付。

## 实施结果

- 已实现共用多重集合比较、45 条已核默认 repr 地址归一化，以及 20 个未来回归副本的精确片段同步。冻结合同和原种子未改。
- 已修复 Palette、Bibtexparser、Click 和续查发现的 Liquid 观察器，四个目标各自的原版、参考、合理替代、错误实现共 16 个真实禁网场景全部符合期望。
- 原 Docutils 候选重建摘要与线上完全一致，经过原冻结控制器适配的真实业务及完整回归均通过；more-itertools、pyparsing、wrapt 完整回归通过。
- more-itertools 的完整结果超过原 2 MiB 预算导致准备标记被轮转，已补按冻结规模计算的有限结果/日志预算及回归测试。
- 106 项相关单元回归执行成功，其中 1 项已有跳过；证据汇总在 `research/isolated-verification.json`。
- 71 个异常分支目标和 39 个私有访问目标已逐项记录处置依据；其中 24 个异常子类/表示线索尚需完整等价候选动态证明，明确保留在 `research/signal-disposition.json`，未计为已确认问题或已修复。

## 验证命令与检查项

- `PYTHONPATH=orchestrator .venv/bin/python -B -m unittest test_project_native_regression test_project_native_verifier test_projects_runtime_resilience test_project_duplicate_adapter test_project_contract_observers test_project_evaluation test_projects_verification_review`
- 新增针对本次元数据语义和受信观察器的测试模块，按最终真实文件名加入上述命令；检查现有 `_same_json` 对布尔协议、数值容差和业务数组顺序的语义不变。
- `python3 scripts/validate-project-library.py` 和 `python3 scripts/validate-development-content.py --help`：前者按实际 CLI 参数核内容结构；后者先核参数，再只跑本轮受影响目标，不能误触全量 600 项昂贵验证。
- 使用 `scripts/validate-project-scenarios.py` 或现有真实 `ProjectVerifier.verify_native` 调用模式，固定镜像、离线环境、候选和旧合同；隔离、UID、禁网、只读来源及有限资源沿用产品要求。
- 所有 100 个合同入口和 600 个目标入口仍可解析，新增/修改来源摘要与适配表对应，原合同文件字节不变。

## 必要反例

- 元数据：少一条、多一条、重复次数变化、改父测试、改业务上下文、通过变跳过/失败、伪造阶段、遗漏节点、真实业务顺序错误。
- 表示：默认 repr 地址变化可兼容；字符串内十六进制字面量、对象类型、函数身份及参数值改变仍失败。
- 观察器：Palette 的可变输入/输出别名和全局污染；非法版本被忽略；软链接被实际写入；原异常被吞掉或替换。
- 来源：已核旧/新脚本均可执行，未知源码、非唯一替换片段、参数路径错配、伪造 expected 或控制端依赖摘要异常均拒绝。

## 风险点与回滚

- 改全局 JSON 比较会影响业务输出顺序：禁止借此修复元数据顺序，新增规则只接入原生证据比较。
- 简单去重或全局地址替换会漏检：保留多重计数、稳定上下文和邻近错误反例。
- 冻结控制器存在 45 个版本：只修改经过核验的精确来源片段，不统一覆盖为当前总模板。
- 原候选离线通过后仍需正常独立评审和正式发布证据；生产切换不包含在规划阶段，最终按项目 SOP 的既有评审门禁推进。
