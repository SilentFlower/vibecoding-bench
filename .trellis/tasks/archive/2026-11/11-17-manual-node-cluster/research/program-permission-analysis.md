## Bug Analysis: 节点隔离验收读取私有冻结脚本失败

### 1. Root Cause Category
- **Category**: E - Implicit Assumption。
- **Specific Cause**: NodeVerifications将离线包复制为UID1000可读副本，同时把原冻结项目的verification和seed直接交给ProjectVerifier挂载。314号真实SSH程序返回脚本路径Permission denied。实际冻结脚本父目录允许0700，隔离容器使用UID1000；验证器输入根中已chmod的脚本被嵌套verification挂载覆盖。
- 次要分类为B跨层合同和D测试覆盖缺口：固定资产的root私有权限与隔离UID读取边界没有整体闭合，原mock验证器未实际打开挂载脚本。

### 2. Why Fixes Failed (if applicable)
1. 早前离线制品权限修复仅覆盖/offline副本，verification与baseline继续引用原冻结目录。
2. 314前的节点程序单测验证对象、原合同和回执，实际Pod第一次读取完整挂载组合时暴露父目录权限。
3. 将输入根的脚本设为0644仍会被原verification嵌套挂载遮盖，需要核对最终容器路径对应的真实来源。

### 3. Prevention Mechanisms
| Priority | Mechanism | Specific Action | Status |
|----------|-----------|-----------------|--------|
| P0 | 本次只读合同副本 | 按原快照对象完整恢复项目合同，核对复制前后摘要；目录0755、文件0644，只挂载该副本的verification与seed | DONE |
| P0 | 保留冻结原件 | 原库0700/0600保持；容量预检计入合同对象和物化副本 | DONE |
| P0 | 真实文件回归 | 077下核对verification脚本、合同JSON、基线及离线包副本可读，原目录与文件保持私有 | DONE |
| P1 | 实际挂载验收 | 318独立真实SSH/UID1000程序→私有Review→严格释放→业务接受，331.639秒通过 | DONE |
| P1 | 规范评估 | 完成阶段由trellis-update-spec评估隔离UID与嵌套挂载合同 | TODO |

### 4. Systematic Expansion
- **Similar Issues**: 已核对ProjectVerifier的/source、/request-data、/request-data/verification、/baseline、/offline及helper挂载；候选与合同由原materialize_snapshot恢复，辅助文件显式0644，离线副本显式0755/0644。
- **Design Improvement**: 消费者通过本次私有目录中的可读只读副本接受资产；资产原件的私有权限属于独立合同。
- **Process Improvement**: 对挂载权限同时核对最终覆盖顺序、目录遍历和文件读取，使用实际UID/POD验证完整路径。

### 5. Knowledge Capture
- [x] 更新任务design中的合同/基线副本与容量边界。
- [x] 保存314号真实失败与本次修复依据。
- [x] 318号实际Docker复验通过，331.639秒。
- [ ] 在收尾Spec阶段评估规范更新。
