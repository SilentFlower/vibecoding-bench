## Bug Analysis: SSH配置收口的持久运行时借用与回执边界

### 1. Root Cause Category

- **Category**: B / D / E，跨层合同、测试覆盖缺口与隐含假设。
- **Specific Cause**: 新quiesce操作把正Gateway ID与空配置传给`NodeExecution._runtime`。真实`NodeRuntimeHost.acquire`经`_NodeGatewayConfigurations.adopt`要求正Gateway ID同时具有原bench身份。该请求在实际停止前被拒绝。停止动作应沿原inspect的`_GatewaySnapshot(0,{})`只读借用，保留现有配置和额度来源。实际授权请求继续携带正Gateway ID、精确环境及有限配置lease。
- 独立发现的回执缺口：`SshNode._execute_environment`要求顶层`protocol/node_key`。新停止回执曾只在request中包含node_key，静态核对后补齐该字段。
- 定位前的假设权重：范围/环境检查40%，真实持久Host借用40%，实际Docker/活动工作20%。448的真实Node栈明确落在`adopt:33`，将定位收敛到持久Host的身份合同。449增加真实Host回归，451实际Gateway/SSH完整通过。

### 2. Why Fixes Failed (if applicable)

1. 436暴露合成中央服务缺quiesce回调，同时发现生产原回调仅操作本机。补齐所属节点路径后，仍需实际持久Host验证。
2. 原停止单测把`executor._runtime`替换为受限Mock。测试验证了空闲、期限和Docker事实，真实Host的adopt身份检查未进入该测试路径。
3. 修复顶层node_key只处理回执合同。447的Node内部拒绝仍需进一步定位。
4. 448加入实际控制进程的受控错误类型及栈位置。该证据直接指向持久Host，随后修复借用方式。

### 3. Prevention Mechanisms

| Priority | Mechanism | Specific Action | Status |
|----------|-----------|-----------------|--------|
| P0 | 真实适配回归 | `test_real_host_borrow_preserves_existing_gateway_projection_and_scope`通过真实Host借用，并核对既有账号配置对象保持 | DONE |
| P0 | 跨层验证 | 实际Rust配置事务→原产品quiesce→固定SSH/UDS→Node实际停止→双方停用后重授权与未知恢复，451通过46.536秒 | DONE |
| P0 | 边界保持 | 原中央未收口账本、登录预留、Node实际作业/程序/评审/发送连接、旧绑定/代次及过期证明继续拒绝 | DONE |
| P1 | 诊断证据 | 合成纵向夹具在配置回调失败时收集Node固定错误类型和栈位置 | DONE |
| P1 | 规范评估 | 将借用语义、私有回执顶层身份和实际适配验证带入后续Update-Spec | TODO |

### 4. Systematic Expansion

- **Similar Issues**: 后续远程解绑、配置维护、退休及备份消费者需要先确定是否发布新配置。纯停止/观察应保持既有投影，不能用空配置替代已有来源。
- **Design Improvement**: 当前采用原只读借用方式复用既有运行时。新的通用运行时抽象保持按实际消费者需求评估。
- **Process Improvement**: 新私有操作同时阅读调用方、轻量SSH客户端、Agent分派、真实Host和底层消费者。Mock运行时验证与真实Host验证分别保留。实际SSH结果承担最终跨层验证。

### 5. Knowledge Capture

- [x] 记录实际命令、失败栈、修复与451证据。
- [x] 在`design.md`补充配置quiesce按所属Node执行及有限门禁合同。
- [ ] 随任务后续Spec评估由`trellis-update-spec`决定最小规范写入。
- [x] native293同场景452通过52.434秒。
