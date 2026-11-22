# 私有评审401后的旧source释放边界核对

## Bug Analysis: 原评审实际释放后的场景证据未通过

### 1. Root Cause Category
- **Category**: 待证据定位，涉及执行收口与中央场景证据交界。
- **Specific Cause**: 350已通过原Scope closed、真实Node当前HOME TLS刷新、Node待办complete与中央维护关闭断言。manager.execution_released后旧source.released_at为空。351通过真实链路取得具体execution_error：driver未给出准确退出计时边界。

### 2. Why Fixes Failed (if applicable)
350断言先检查released_at，遗漏同一行execution_error，诊断证据不足。351补同一持久行错误后复验，确认原driver最终尾段未settled。352新测试漏导入call，已补显式导入；353同范围57项通过。

### 3. Prevention Mechanisms
| Priority | Mechanism | Specific Action | Status |
|----------|-----------|-----------------|--------|
| P0 | 真实跨层边界 | 保持原_scope_停止与预算严格检查，记录原source错误后定位 | 进行中 |
| P1 | 回归覆盖 | 实际401、旧评审停止、真实TLS、同会话/模型/逻辑尝试/预算接续 | 进行中 |

### 4. Systematic Expansion
- **Similar Issues**: 同类主动停止和节点恢复后的私有评审工作边界需对照。
- **Design Improvement**: 等待具体证据。
- **Process Improvement**: 失败应同时携带同一持久行的固定原因，避免只见空状态。

### 5. Knowledge Capture
- [ ] 根因确认后经Update-Spec评估可复用合同。

### 初始假设与区分证据
- H1（45%）：主动停止时原driver尚未写settled尾段。检查execution_error和原Node project-work.json。
- H2（30%）：原生/输入或工作文件镜像边界缺失。检查sync_plan与_observe_input的具体错误。
- H3（25%）：源、环境/代次或文件IO身份异常。检查同原行的错误与冻结回执。
351使H1得到直接支持。原worker写入claude-owner-refresh-required后继续等待profile，控制侧已开始停止作业。Root定向停止可能先于worker的EXIT计时清理，因此原场景正确保留未决预算。改为worker在该标记后正常结束认证失败路径，控制侧有界观察同一真实exec退出，再执行原严格停止。保持原driver最终计时与中央预算核验。353号57项通过20.672秒，包含同exec退出观察、缺失ExitCode拒绝、八秒截止与原worker启动回归。真实链路待355复验。


### 实际复验与第二个原因

355真实链路已确认第一次401的原Node工作片段settled=True，elapsed_sec=2.6242162409762386，旧source通过严格释放，原评测作业review_resume=1、infra_recoveries=1、同一会话/包/逻辑评审尝试重新启动。第二次worker以42退出，整体失败151.849秒。

原detect_claude_auth_error在每个新worker默认since_epoch=0，扫描原生文件末80行，遗漏已有COMPLETION_BASELINE。同一私有会话保留旧401后会再次被误识别。356独立真实bash/Python函数复现：已有字节基线内的旧401加本轮健康响应仍返回认证错误。当前修复沿原完整字节基线seek，只消费本轮追加JSONL，保留原轮内时间边界和TUI规则。测试再追加本轮新401后要求仍被识别，防止压掉真实故障。357正在跑新复现及原worker/私有评审/OAuth入口回归。

根因分类更新为E（Implicit Assumption）：把评审主动停止当作已完成driver退出；把新worker当作全新原生会话。改动继续保留原严格预算核对，并复用原存在的会话字节基线。


### 最终验证证据

357号106项通过44.864秒。358号15项通过6.431秒，含owner占锁时共享恢复循环及时返回。359构建成功。360完整真实401接续通过167.918秒，driver准确尾段、原会话/模型/逻辑评审尝试/预算接续以及严格释放后最终业务接受均通过。根因修正使用原EXIT清理与已有字节基线。Task最终Spec阶段评估可执行合同增量。
