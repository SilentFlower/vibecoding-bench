# 实施计划

- [x] 1. Brief确认后启动任务，按inline路由读取运行时和日志规范及实际类型。
- [x] 2. 新增统一白名单诊断模块，完成阶段、异常/errno、CRIU受控分类及有界私有落盘。
- [x] 3. 接入controller模板/恢复清理前诊断与supervisor内部首错摘要，维持原错误、取消和清理语义。
- [x] 4. 注入CRIU非零退出、空报告、文件/管道、namespace和校验异常；验证隐私、权限、轮换和诊断自身失败。
- [x] 5. 同步export/package与镜像分发输入和source-manifest，核对打包画像完整性。
- [x] 6. 跑Python恢复/构建回归、隔离成功及故障链路，检查资源回收和原普通启动回退。
- [x] 7. Check-All后更新权威规范，再按精确Push计划同步代码及任务记录。

## 验证命令

- python3 -m unittest discover -s services/runtime/native/criu -p 'test_*.py'
- python3 -m unittest discover -s services/runtime/scripts/criu -p 'test_*.py'
- export_bundle.py导出全新私有目录并与images/v3/criu逐文件核对。
- 隔离环境执行supervisor故障摘要与controller清理链路；使用合成输入验证真实恢复/回退及零额外POST。
- 根据最终改动范围运行必要的gateway/runtime回归；计时合同保持原有实现。
- git diff --check。

## 边界与恢复

保留397项既有脏基线。失败摘要取证本身失败时继续原异常与finally；权限或脱敏验证失败先修复本地实现。生产只读证据来自本会话私有runtime，任务中只保留脱敏事实。发布和线上部署按后续明确授权执行。
