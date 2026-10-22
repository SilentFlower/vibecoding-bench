# Loguru日志业务任务表

固定bce5dfd3b435b1d1658507d7e095ad7a9919bf1c，MIT，完整313个Git文件。已读Logger.add／opt／bind／contextualize／catch／complete／configure及_log与sink分派定义。完整当前镜像原生尚在校准，失败与资源根因见native-adapter-contract.md；不把历史1679通过直接当本轮成功。

| 任务 | 独立业务事实与目标 | 材料、授权与验收 |
| --- | --- | --- |
| LG-U01 理解 | 同名结构化字段来自不同配置层 | 全局extra、context、bind、调用kwargs完整样本，作用域退出复原，真实record快照；只读 |
| LG-U02 理解 | sink过滤并不让昂贵lazy值免于执行 | DEBUG低于全局最低级别未调用，INFO虽被filter拒绝仍先调用，副作用计数而非时间性能承诺；只读 |
| LG-C01 咨询 | 叠加opt会重置先前capture设置 | captureFalse后opt(raw=True)恢复默认captureTrue，单次列全选项保留预期；只读 |
| LG-C02 咨询 | 已记录异常不代表失败信号继续上抛 | 默认catch返回None、明确default和reraise控制，业务成功/失败合同由调用者选择；只读 |
| LG-P01 方案 | 异步sink任务不能只调用complete就假定完成 | 真实事件门禁、同loop等待的awaitable，规划停止投递/等待/移除顺序及所有者，不保证跨loop或外部持久化；只读方案 |
| LG-D01 诊断 | 多sink配置失败后旧输出消失且只剩部分新输出 | 首问缺配置／顺序／异常，追问披露完整configure两项、第二无效和真实旧/新输出；顺序替换不是事务，保留现场并规划调用者恢复，不授权修库；无材料正常收口 |

四场景六任务，无人为依赖；本地StringIO／record与受控事件，不接外部日志平台或真实敏感配置。宿主观察见loguru-host-observation-001.json，当前原生、业务、产品与交付准入分别记录。
