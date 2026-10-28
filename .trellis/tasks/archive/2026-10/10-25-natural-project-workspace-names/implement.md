# 实施计划

## 实施前

- [x] 完整展示最终任务摘要并按首次实施评审规则取得确认。
- [x] `task.py start` 后进入 `trellis-route(target=implement)`，沿缺省主会话执行，不派发子代理。
- [x] 复用已读类定义与匹配规范，按 `trellis-before-dev` 补齐尚未读取的实现规范。

## 实现

1. 为两种模式的新建工作区增加以项目标识为主体的版本化名称，明确验证项目 key、轮次和命名版本。
2. 优先接续同身份合法旧注册；为冲突、双注册、未知目录、非法版本和路径篡改保留拒绝行为。
3. 调整注册解析与清理，覆盖新旧混合、多账号、多空间、多个轮次和清理中断。
4. 检查原生终端的实际 cwd、PYTHONPATH、native 会话目录、状态栏和原会话恢复仍使用同一选定工作区。
5. 同步用户说明与可执行规范，不改冻结内容或现有工程记录。

## 验证

```bash
PYTHONPATH=orchestrator .venv/bin/python -m unittest orchestrator.test_projects_workspace orchestrator.test_projects_cycles orchestrator.test_projects_terminal
PYTHONPATH=orchestrator .venv/bin/python -m unittest orchestrator.test_projects_agent orchestrator.test_projects_single_objective
git diff --check
```

- 首组验证自然命名、同项目接续、旧注册和旧输入原样接续、两个空间及 seed/轮次隔离、非法注册与链接拒绝、未知目录保护、清理故障重入。
- 在终端替身中核对旧 work/session 的 cwd 和 native 位置保持，新 work 使用自然路径；不将替身通过宣称为真实 Claude 运行验证。
- 第二组核对原工作优先、累计预算和同代次单目标规则；若实际变更不涉及相关行为，可由 Check-All 按影响范围裁剪。
- 补充主动构造的后缀冲突、双注册、跨空间未知目录等负向断言，证明不会覆盖源码或扩大清理范围。

## 收尾

- [x] 实现完成后返回工作流 Pre-Check 与 `trellis-route(target=check)`，完成适当深度的质量检查。
- [ ] 按检查结果同步代码规范和任务进度，再进入提交流程；不自动推送或部署。
- [ ] 如出现身份或路径证据无法唯一核对，停止受影响操作并保留现场；不迁移、清空或重新生成旧会话。
