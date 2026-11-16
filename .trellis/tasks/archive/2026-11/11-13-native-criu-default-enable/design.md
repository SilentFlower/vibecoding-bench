# CRIU 默认启用与实际状态展示设计

## 生命周期与默认策略

全局V3_NATIVE_CRIU缺省1、精确0关闭，环境指纹新增可选native_criu_enabled:boolean，缺省true。参考native_capture_policy统一解释历史字段，拒绝非法类型。创建角色前将目标选择纳入sender安全配置和布局一致性判断，普通ensure/系统更新/空闲重建复用同一决策。既有容器不会仅因列表查询而重建。

默认制品切换到已验收beta.6，固定官方来源保持2.1.293。同步native_sender默认版本/分发身份、gateway内置映像身份、Docker校验与相关消费者。持久选择的release/kernel_generation优先于内置版本。核对native_kernel_upgrade.stage_release中拒绝候选SHA等于内置SHA的逻辑，确保已持久选择beta.6的环境在内置升级后继续有效；重复准备当前内置版给出已在使用的可读结果。

## 预算和回退

native_sender.sender_config继续以原普通池公式校验基础可用性，不因默认开启扩大既有账号最低业务内存。恢复分支另核验256+max_workers×(192+ceil(image_bytes/MiB))，当前额外108MiB。额度不足选择普通入口/普通启动并输出固定原因。memory_mib=0表示配置无限，仍受max_workers限制。保持真实退出后释放许可及原接收截止，不通过改并发或资源额度隐藏问题。

## 状态流与合同

Rust NativeReadinessStatus添加可选恢复状态摘要，旧sender缺字段按未知兼容；NativePool按当前身份、部署能力、内核/映像、预算、后台种子/模板/退避及恢复来源提供真实安全枚举。读取不启动模型或恢复。恢复器preflight失败原因保留受控码，避免将CCRB_CRIU=0混同用户关闭。

orchestrator对目标选择、当前容器入口/镜像与sender配置、可信readiness巡检分别建模。旧容器显示需要应用/重建，模板就绪依据实际同代状态，旧版本遥测显示未知。对外新增版本化安全摘要schema_version=1：enabled为账号期望值，platform_enabled为全局选择，state/reason为实际状态和固定原因，checked_at_ms为采样时刻，template_ready表示当前身份可用模板，memory_mib/required_memory_mib分别表示配置与恢复最低额度，memory_mib=0表示无限。state覆盖disabled/not_installed/requires_rebuild/preparing/ready/unavailable/unknown；reason区分平台/账号关闭、旧入口、旧内核、内存不足、控制器不可用、模板失败及旧版本遥测缺失。最近成功worker创建来源可选为exec或criu_restore，表示已观测来源。

GET /api/environments/{environment_id}/criu返回该摘要与generation/revision，列表复用一致快照；POST同一路径接收enabled:boolean、expected_generation:int、expected_revision:string，仅接受已定义字段。Rust NativeReadinessStatus内新增可选恢复摘要，真实模板与运行状态由pool提供，部署期望和容器入口状态由orchestrator合并；新增结构在对应层显式定义并与旧响应兼容。禁止暴露凭据、请求正文或私有快照路径。

## 开关与界面

在固定账号环境卡片展示CRIU加速区，显示开关、实际生效状态、可读回退原因与必要内存数值；支持原生账号显式关闭及再次开启。沿content_capture_settings现有generation/revision、update admission、owner/profile/environment锁、维护租约和空闲重建模式实现专用原子操作，失败恢复原选择或保留对账状态。全局关闭显示平台原因。旧内核仍可普通启动，界面提示需要配套内核。

版本列表与CRIU状态共用同一内核卡片和原升级动作，统一页面字段及状态。

## 兼容与验收边界

缺省配置自动开启，显式0/false持续有效。业务worker仍为UID1001/cap0/NNP1/seccomp2；根控制器只在受控角色启动时使用既有能力集合。线上当前10/12仅满足静态条件，真正恢复须在上线重建后验证；本轮远程仅只读核查。

## 实施中确认的合并范围：版本发现

新增GET /api/environments/{environment_id}/native-kernel/releases?refresh=bool，核对唯一账号绑定及原生内核管理能力；只读取固定GitHub发行API。列表按现有TAG规则筛选已发布非draft条目，要求固定三附件存在，按beta数字降序排列。发现元数据不授信，下载仍由stage_release原签名/SHA合同所有。

使用有界响应、超时和五分钟进程内缓存；显式检查可刷新，失败返回unavailable或带缓存的stale及固定原因。GET环境列表保持零外部版本查询和零模型调用。响应含state、checked_at_ms、latest、versions[{release,published_at}]、reason及当前内置版本，丢弃任意发布正文/未知字段。

前端提供检查更新按钮、新版提示及准备表单的版本select。列表/选项异步回执沿页面与弹窗代次核对，打开表单冻结revision；准备、激活、回滚保持原动作和人工确认。发现失败保留当前内核运行及已准备候选。

## 实施中确认的合并范围：CPU默认值

在cpu_resources.py集中解析V3_ACCOUNT_CLI_CPUS、V3_ACCOUNT_SENDER_CPUS、V3_ACCOUNT_NETWORK_CPUS，缺省为1.5/1/0.5，按Decimal严格校验有限正数及NanoCpus精度。部署预检与隔离角色创建共用解析，非法默认值在创建前拒绝。

旧V3_ACCOUNT_CPUS保留旧布局用途；新三角色直接使用独立默认，之后应用旧评审布局及已保存cpu-resources.json；合法显式策略最高优先。检查project_review_runtime的CLI默认上界和串行评审消费者，按实际/保存额度核验。内存、PID和业务并发沿原合同。
