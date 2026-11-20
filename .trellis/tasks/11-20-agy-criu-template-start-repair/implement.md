# AGY 模板启动故障实施

1. 以已复现的文件型启动失配作为回归基线。补齐封存 memfd 的对照，核对监听就绪、控制 socket、保存及恢复阶段。
2. 修复已证实的首个失败阶段。补定向回归并验证可信执行体、错误映射、同代模板回收和普通回退。
3. 运行 `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_agy_runtime`，再执行正式镜像布局上的零模型准备与真实 CRIU 保存恢复。在原权限与资源配置下拿到模板和恢复回执。
4. 验证诊断保密、既有应用路径及单次提交语义。交付修复版本后沿原部署流程复核 AGY #14。

## 验证记录

- 普通 UID 的真实 OverlayFS 对照复现旧观察器拒绝。修复后原 AGY 文件路径、封存 memfd 均就绪，同摘要的不同 inode 仍被拒绝。
- 隔离 Linux VM 使用固定 AGY 1.5.9、CRIU 4.2、原监督器和受限业务权限。当前代次模板保存并恢复，同一原生 PID 完成首个合成 TLS 请求。注入恢复失败和凭据换代均走普通启动，各仅一次模型提交。
- AGY 环境、监督器、采集、系统提示词及 Claude Code CRIU 相关回归合计 88 项通过。US #14 待修复版本上线后确认。
