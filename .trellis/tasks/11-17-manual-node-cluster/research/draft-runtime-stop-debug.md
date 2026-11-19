## Bug Analysis: NULL草稿实际停止与无tmux产物恢复

### 1. Root Cause Category
- **Category**: B / D — 跨层合同和替身覆盖缺口。
- **Specific Cause**: 470号真实SSH草稿已完成原tmux启动、原WS输入及授权码一次投递，取消时在`AccountRuntime.restore_execution:1738`触发KeyError。草稿Scope按合同省略正式账号字段；原运行时适配对象只传私有设置，原停止恢复分支使用`account['id']`。该对象需要明确`id=None`。
- 调查同时发现第二个合同差异：`recover_login`保存版本并认领认证检查工作，原登录停止恢复只接受无版本的未启动记录或有精确tmux的授权工作。产物检查需要自己的明确用途与停止恢复标志，保持NULL身份和无tmux事实。

### 2. Why Fixes Failed (if applicable)
1. 初次草稿单测用可观察的`restore_execution`替身返回原job，覆盖了Actor流程，遗漏原运行时对`id`及tmux/版本组合的实际读取。
2. 470号首次实际纵向验证暴露取消合同；修复前静态跟踪原恢复函数，提前识别无tmux产物检查的第二个停止缺口。

### 3. Prevention Mechanisms
| Priority | Mechanism | Specific Action | Status |
|----------|-----------|-----------------|--------|
| P0 | 具体适配 | 运行时草稿对象显式`id=None`，Scope仍独立且省略正式ID | DONE |
| P0 | 持久用途 | 原`recover_login`在保存版本的同一检查点保存`draft-login-recovery` | DONE |
| P0 | 严格停止 | 新标志只允许NULL账号、独立login来源、原模式、无tmux/exec/工作定位，恢复只授予停止能力 | DONE |
| P0 | 真实函数回归 | 草稿Actor替身改用实际`AccountRuntime.restore_execution`，真实临时库另验磁盘恢复和错误角色/正式ID拒绝 | DONE：472号10项4.903秒通过 |
| P1 | 实际SSH | 重建控制镜像后复验取消、保留产物、新SID认证检查和原实际停止 | DONE：474号31.264秒；477号31.944秒；482号完整激活46.541秒 |

### 4. Systematic Expansion
- **Similar Issues**: 共用授权码与PTY回执内的正式Scope构造、恢复时旧SID暂存路径、持久Host借用以及普通正式执行准入均已按草稿独立范围适配并回归。正式账号原停止合同继续单独验证。
- **Design Improvement**: 保持原草稿身份，采用具体运行时对象和明确恢复用途；授权工作与只读认证检查保持不同实际定位。
- **Process Improvement**: 共享底层恢复函数及关键Scope解析器应在Actor测试中直接使用真实实现；Docker替身继续承担真正外部进程边界。

### 5. Knowledge Capture
- [x] 同一任务design.md记录NULL适配及恢复用途。
- [x] 真实运行时与Actor测试覆盖此次合同。
- [ ] 在原任务Update-Spec阶段评估草稿运行时与实际停止规范。
