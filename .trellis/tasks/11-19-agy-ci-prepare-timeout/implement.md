# 实施与验证计划

1. [x] 取得Brief有效批准并启动任务，按implement route载入实际探针、监督器及相关规范。
2. [x] 对失败路径补齐有界白名单证据与故障注入测试，保留原首错及清理。
3. [ ] 按阶段证据区分传输、worker、共享映像、观察器、原生监听及资源，完成可区分原因的本地/CI复验。
4. [ ] 根因确定后最小修复，补定向回归；原权限、业务和模型预算边界保持。
5. [ ] Check-All → Spec → 精确Git计划；推送后按最终SHA核验实际正式CI两种退出及候选交付。
6. [ ] 候选通过后恢复v1.19.0发行预览，按原SOP进入签名发布。

## 验证

Python使用/root/project/vibecoding-bench/.venv/bin/python；PYTHONPATH=services/orchestrator:deploy/flower2api。新增故障测试覆盖采集失败、敏感字段排除、预算及原始错误传播；回归test_agy_images、test_system_workflow及受影响AGY运行时用例。实际Docker保持断网、只读根、UID1001、原内存及权限约束，模型预算0。正式CI结果与隔离夹具分开记录。复用上一任务当前有效的287项部署与相关编排测试证据，源码变化后只补必要覆盖。

## 当前里程碑与推进

- 诊断阶段：只读失败摘要、首错/清理及既有成功路径已本地验证；独立检查该增量。
- 中间推送：按精确Git计划交付诊断代码和任务记录，task_progress仅写partial并保持in_progress。当前不执行完成态或Close。
- 外部CI：以该诊断源码取得正式宿主的失败分类和阶段证据，继续第3—6步；根因未定期间保持原预算及权限。

## 本地验证记录

- 部署目录discover：退出码0，291项，跳过1项；随后新增清理分支的定向回归为16项通过。
- 最终源文件SHA256：a48621b400d00b2e254a925fdf3c7c73c3bbe527a80b0d99632ae9e61bfd7046。
- research/verify_probe_diagnostics.py的fault/normal/crash三个模式在同一最终源码下均退出0；固定隔离镜像flower2api-ci-artifact-account:v3-package-check，断网、UID1001、原权限和资源限制，零模型。
- 故障模式保留原worker_start_failed分类、容器及OOM摘要；正常/异常模式仍有两代凭据、单次解码和terminated=true。
- 实际日志与结果存于gitignored的.trellis/.runtime/agy-ci-prepare-timeout/；正式CI根因及完整镜像验收保持待完成。
