# 技术设计

## 默认策略

复用resource_budget.py的unlimited哨兵，不引入第二种无限语义。统一AccountRuntime首次画像、重画像缺字段、Compose、example.env和manage.py的默认值及空值处理。显式有限部署配置沿现有公式。默认sender CPU在cpu_resources.default_cpu_limits、Compose及示例中同步为1.5核，持久账号CPU策略沿原优先级。

## 既有环境迁移

仅当前部署明确采用unlimited策略时，已有有限内存成为待应用的资源变化。沿AccountRuntime账号锁、环境锁及原容量/活动检查处理，复用原空闲重建和代次发布。CLI准备仍按prepare_sender=False保留已生效发送布局；资源迁移是独立的显式部署策略应用，不从目标native293推导资源许可。忙时保留旧配置并延后迁移，原作业继续使用原现场。后台startup_prewarm继续禁止重建；停止环境不由扫描自动唤醒。

在删除旧角色前核对job/API、串行评审、内核维护和凭据交接；失败保留原画像或明确对账状态。新角色前更新同一冻结内存配置；原生配置与fingerprint.native_sender_memory始终一致。新sender生成memory_mib=0，CLI和API职责继续分开。原env ID、HOME、system/computer profile、CPU持久策略和账号绑定保持。孤儿及部分创建沿既有恢复处理。

## 部署预检

取消全局unlimited的禁止分支。无限不作为零资源需求，继续执行正整数活跃账号数、宿主余量和显式最低可用RAM检查。已登记有限账号继续核验真实RAM/swap；全局无限时不得用0与有限账号预算比较而错误拒绝或跳过。无限账户不人为预留额外swap额度，显式有限账户继续swap容量与Docker支持检查。

## 上线衔接

任务release.md记录当前15个环境的迁移边界，本部署现有V3_ACCOUNT_MEMORY=1536m显式值需改为unlimited，V3_ACCOUNT_SENDER_CPUS的部署缺省为1.5。CPU保存策略优先。本次按用户追加指令正式发布v1.7.0；安装留给后续指令；安装前冻结精确env及镜像来源，沿系统更新门禁排空并备份配置。已有停止环境保持停止，运行环境在空闲生命周期应用新内存。检查11-14原work/session与1/600历史事实。

## 风险及恢复

所有无限账号直接共享本机RAM和swap。物理耗尽仍受宿主约束。保留宿主余量检查及原CPU/PID/并发约束。迁移失败沿原环境对账恢复；恢复有限配置须空闲重建且容纳实际资源，不能只修改数据库。项目身份与已提交业务事实保持原归属。
