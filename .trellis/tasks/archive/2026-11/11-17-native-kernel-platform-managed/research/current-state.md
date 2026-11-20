# 当前实现及证据

## 用户决定

内核随Flower2API平台版本自动切换和回退，保留280／293请求匹配和运行诊断。独立管理入口及旧仓库构建依赖一并收口。

## 线上核验

证据位于.deploy/flower-v1.14.0-online-check。inventory.json记录14个新版运行容器、零重启和OOM。kernels.json记录升级后10／12仍选beta.6。用户手动切换后的kernels-after-switch.json和api-after-switch.json确认四账号293／TLS／CRIU ready。signature-proof.json确认一次400同账号重试成功，后续同会话18笔均一次尝试；入口仍有原失效历史，发送前已清理，TLS采集完整。

## 代码入口

- EnvironmentKernel.vue处理独立版本发现和prepare/activate/rollback/recover；RuntimeEnvironments.vue提供入口和快速轮询，runtimeApi.ts定义DTO。
- main.py提供GET /api/environments/{id}/native-kernel/releases及POST /api/environments/{id}/native-kernel。
- native_kernel_releases.API、native_kernel_upgrade.REPOSITORY、native_sender.stage_asset的293回退指向旧仓库。
- native_kernel_upgrade.applied_kernel读取两份runtime/native-kernel-upgrade*.json，account_isolation.create_environment将current恢复至sender。
- account_runtime.ensure按镜像生成目标；prepare_sender=False沿已应用布局；system_updates的重建调用使用此模式。transport使用默认True进行API准备。
- pending_upgrade/recover_interrupted被环境、CPU、内容采集、CRIU、平台更新及并行节点模块引用。
- NativeSenderConfig、NativeRuntimeConfig均deny_unknown_fields，具有release/kernel_generation。runtime_transport.read_config解码；native_runtime.artifact在release存在时读/runtime-releases签名附件。
- 专用切换为native-kernel-probe、prepare-switch和NativeKernelTarget/Preparation。
- prepare-ci-runtime.py和CI composite目前只构建280；manage.stage_asset的293默认取旧仓库beta.7。
- v3.json.native_runtime保存两版身份，平台发行签署同批镜像和联合清单。

## 官方来源

- 280：源SHA256 1e08503dbdf3c2cb0d706d32f3408277388d1c76ef108673e8fe42c1b322925b，文件233709640字节。
- 293：源SHA256 8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978，已验收官方文件252755128字节。
- 官方293 npm tarball：https://registry.npmjs.org/@anthropic-ai/claude-code-linux-x64/-/claude-code-linux-x64-2.1.293.tgz。
- 本轮npm view取得integrity：sha512-tYTbeVuhqD0TW2WJs90Tq+JaKLLnrX5JuxYTLG3pxf4Vr3QMonqsMLu4hZkgVSfEDPZhneFuDDgULQ3/FZzAIw==。
- 当前已接纳分发／映像身份见native_sender.py、Rust固定身份与compact-profile.ts。构建报告作为证据，不自行授信。

## 约束

旧维护PENDING为draining/switching/restoring/finishing/reconcile，到期租约继续维持门禁。迁移核对所有者和活动。旧选择迁移结果须兼容旧平台读取为内置，避免平台回退重新覆盖目标组合。

本地多项并行变更涉及account_runtime.py、account_isolation.py、main.py、runtimeApi.ts、RuntimeEnvironments.vue、Dockerfile及更新器。按本任务行为边界合入，兼容只读调用。

## 用户截图补充：布局迁移延后与养号占用

用户于本轮明确将截图问题纳入任务。截图记录10-30养号作业在北京时间13:49:37—13:56:51运行；13:51附近12次请求在发送前遇到本地503，另一账号同期成功。

代码链路与截图吻合：system_updates.py::environment使用prepare_sender=False重建；AccountRuntime.ensure此时复用_applied_native_sender的旧单版布局。API transport随后使用默认prepare_sender=True，按双版镜像生成目标；布局不一致触发重建，而environment_jobs的作业保护阻止重建。手动独立内核切换仅更新release/kernel_generation，双版登记仍取决于环境布局迁移。

验收要求已加入R6、AC9和AC10：在平台升级维护阶段完成目标安装表迁移与实际就绪核验；以升级后养号占用期间首笔293／280请求验证布局稳定。就绪沿原容量和按需预热策略，历史目标按自身安装能力处理。截图所述后续恢复结果需另行线上核验。
