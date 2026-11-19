# 实施与验证计划

1. [x] 取得Brief有效批准并启动任务，按implement route载入实际探针、监督器及相关规范。
2. [x] 对失败路径补齐有界白名单证据与故障注入测试，保留原首错及清理。
3. [x] 按阶段证据区分传输、worker、共享映像、观察器、原生监听及资源，完成可区分原因的本地/CI复验。
4. [x] 根因确定后最小修复，补定向回归；原权限、业务和模型预算边界保持。
5. [x] Check-All → Spec → 精确Git计划；推送后按最终SHA核验实际正式CI两种退出及候选交付。
6. [x] 候选通过后恢复v1.19.0发行预览，进入原SOP的签名发布确认点。

## 验证

Python使用/root/project/vibecoding-bench/.venv/bin/python；PYTHONPATH=services/orchestrator:deploy/flower2api。新增故障测试覆盖采集失败、敏感字段排除、预算及原始错误传播；回归test_agy_images、test_system_workflow及受影响AGY运行时用例。实际Docker保持断网、只读根、UID1001、原内存及权限约束，模型预算0。正式CI结果与隔离夹具分开记录。复用上一任务当前有效的287项部署与相关编排测试证据，源码变化后只补必要覆盖。

## 诊断中间交付记录

- 诊断阶段：只读失败摘要、首错/清理及既有成功路径已本地验证；独立检查该增量。
- 中间推送：按精确Git计划交付诊断代码和任务记录，task_progress仅写partial并保持in_progress。当前不执行完成态或Close。
- 外部CI：以该诊断源码取得正式宿主的失败分类和阶段证据，继续第3—6步；根因未定期间保持原预算及权限。

## 本地验证记录

- 部署目录discover：退出码0，291项，跳过1项；随后新增清理分支的定向回归为16项通过。
- 诊断阶段源文件SHA256：a48621b400d00b2e254a925fdf3c7c73c3bbe527a80b0d99632ae9e61bfd7046。
- research/verify_probe_diagnostics.py的fault/normal/crash三个模式在同一最终源码下均退出0；固定隔离镜像flower2api-ci-artifact-account:v3-package-check，断网、UID1001、原权限和资源限制，零模型。
- 故障模式保留原worker_start_failed分类、容器及OOM摘要；正常/异常模式仍有两代凭据、单次解码和terminated=true。
- 实际日志与结果存于gitignored的.trellis/.runtime/agy-ci-prepare-timeout/；正式CI根因及完整镜像验收保持待完成。

## 根因修复验证

- 37项定向、64项全部AGY回归通过；部署目录294项通过，跳过1项；数据库扫描仍为bench5/gateway6，diff格式通过。
- 新账号隔离镜像flower2api-ci-budget-account:v3-deadline-check的正常/异常退出通过，两代准备、单次共享解码及零模型保持；每代准备约8—9秒。
- 固定原失败源码1435bb2a的45秒探针在慢退役夹具下仍拒绝；修复后的截止护栏在退役耗尽截止后保持零新进程，直接报告request_deadline_exceeded。
- 同一修复镜像、相同约45.4秒退役下，当前120秒探针通过；准备耗时约8.6秒、53.4秒，单次共享解码、物理退出及零模型通过。原型对照与最终对照分别记录。
- CI入口补齐test_agy_supervisor/test_agy_artifact/test_agy_images，原三组并行与宿主root保持。
- 精确推送后先等待同源码正式CI；通过后再登记完成态和Close、推送任务记录，并核对最终候选CI与v1.19.0完整预览。失败时按实际结果写partial，继续保持in_progress。

## 正式CI入口跟进

- 根因修复提交4b4266da已推送；运行44475828322在host测试导入阶段失败。sudo清除PYTHONPATH后，新测试先导入agy_auth，尚未设置编排源码路径；镜像步骤保持未执行。
- 本地预设PYTHONPATH的验证未覆盖该入口。后续按源码布局合同初始化测试导入路径，并通过原三组正式入口验证。AC3、AC4及任务保持进行中。

- 导入增量已沿既有source_path模式修复。清除PYTHONPATH后的独立探针测试7项通过；原verify_release_tests.py三组实际入口全部通过：host143项（跳过1项）、orchestrator25项、publication86项。正式新源码CI待精确推送后核对。

- 导入修复c462479a的正式运行44476665812通过合同、处理产物、两个镜像构建及两代prepared/job_finalized；正常退出在15秒物理观察窗口失败。现场supervisor/kernel/observer/native仍存活，OOM为0。当前转向退出窗口与真实收尾流程，任务保持进行中。

## 退出观察增量验证

- 25秒虚拟进程回归先复现旧15秒窗口失败；修复后7项独立测试通过。原三组入口通过：host143项（跳过1项）、orchestrator25项、publication86项。
- 镜像自带源码正常/异常退出通过，物理退出耗时0.727/0.405秒，两代准备、单次解码和零模型通过。
- 独立源码慢退出夹具的旧15秒失败摘要与正式运行44476665812完全一致；90秒窗口在45.795秒确认全部目标PID退出，原生退役45.438秒，模型入口0。夹具和镜像自身证据分开记录于research/root-validation.json。
- 新源码正式完整镜像CI待精确提交后验收；成功后完成任务记录并恢复v1.19.0完整预览，失败时继续保留partial。

## 正式验收完成

- 运行44479235691、源码166ccdc1全部成功。正常准备耗时8.004/52.822秒，正常退出45.198秒；异常模式准备8.005/52.852秒，异常退出0.277秒。两种模式均从镜像自带包执行，两代准备、单次解码、物理退出及零模型通过。
- 可信候选归档、必要成功步骤、仓库与源码归属通过原candidate_artifact合同，构建清单通过validate_candidate_manifest。原处理产物固定身份已核对。
- v1.19.0完整说明已按新候选重新展示。任务记录提交后继续核对最终源码候选，签名发行由原SOP的独立确认点承接。
