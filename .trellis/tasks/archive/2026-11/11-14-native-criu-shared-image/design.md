# CRIU 共享执行映像设计

## 权威来源

源码在 services/runtime/native/criu/；配方和导出在 services/runtime/scripts/criu/；images/v3/criu/为生成的镜像输入。Rust native_runtime.rs中的NativePool/Worker/RestoreGuard持有映像、模板和容量，native_criu.rs的Template/Process持有IPC和pidfd。Python Controller.Template的users/drained覆盖模板和在途实例。

## 数据流与准入

1. 零业务种子握手完成后沿原协议登记。
2. 控制器在种子身份校验期间打开实际exe，核对固定SHA、大小、四项seals和dev/inode并持有只读FD。
3. 控制器先固化0555读执行权限，再转为root所有并再次固化权限，阻止业务UID改变元数据。首次改权失败发生在改属主之前，属主转换失败仍保留普通exec所需权限。随后dump。
4. 模板持有映像引用。每实例重新open同一inode，获得独立打开文件描述，经固定加载器移交监督进程。
5. CRIU的FD/VMA/exe三条路径引用相同背板，保留匿名内存、私有脏页和映射类型。
6. Rust复核实际外部PID的exe大小、摘要、seals及与缓存映像的dev/inode一致性，继续随机重置、nonce绑定与TLS准备。
7. 失败由RestoreGuard等待实际清理后回退普通exec，全部准入完成后才投递业务。

## CRIU补丁

- 固定4.2归档，更新既有补丁、摘要和工具画像。
- 采用专用ccrb-executable资源键，在memfd inode打开路径统一接入，保留通用inherited_fd原语义。将共享目标绑定唯一执行体inode记录，拒绝同名其他inode。控制IPC保持原白名单。
- 核对继承FD类型、大小、seals、身份和权限，共享路径跳过内容填充、权限重建及重复加seal。
- 上游继承捷径跳过fown和偏移恢复。正式实现保留快照FD的访问模式、偏移、状态和别名语义；不兼容则拒绝恢复。
- FD/VMA/exe三条路径统一准入，允许原有MAP_PRIVATE写入并恢复私有页，共享范围限制为封存执行映像。
- 研究版只补prepare_mm，用作可行性参考，正式补丁补齐上述边界。

## 生命周期与兼容

- 模板源FD覆盖种子退出。各实例单独打开，各层明确成功、异常和取消的关闭责任。
- 撤销模板停止新准入，users/drained收口在途实例后释放模板FD。实例自身exe/VMA引用保持其生命周期。
- 完整池key继续绑定账号、凭据、代理和环境/内核代次，恢复仅使用当前模板。只读代码缓存沿既有同账号策略复用，限制在同一cgroup。
- 共享跟随现有CRIU开关，新工具画像记录共享能力，入口预检核对配套工具。旧工具或实际inode不符时在业务投递前回退普通exec。
- 保持现有256+max_workers×(192+108) MiB预算和物理上限，单独观察新旧代并存峰值。
- 身份失败先撤销模板并重核可信来源，保留SHA、seal、随机画像和唯一提交校验。

## 验证及操作边界

单元层使用合成凭据、memfd与目录。内核层使用关闭网络的隔离容器。CRIU层比较现有恢复、仅继承FD、完整共享三组模式，采集exe/VMA inode、内存和延迟。

真实CC使用固定版本、合成身份与受控接收端，沿原生/TLS验证设施确认四路、流式、工具、连续请求及取消。接入细节在隔离环境验证。

本地WSL快照的seccomp阻塞已有证据。优先使用现有合法隔离环境；环境缺失时对应验收保持未通过。生产写入、部署和真实付费请求属于独立授权边界。私有快照和请求正文留runtime，任务只保存脱敏结果。

## 关联合同

- .trellis/spec/runtime/backend/runtime-contract.md：CRIU热模板协议1。
- .trellis/spec/orchestrator/backend/account-runtime-v3.md：映像池、预算及CRIU设置。
- .trellis/spec/gateway/backend/testing-quality.md：Rust全量验证和敏感数据边界。
