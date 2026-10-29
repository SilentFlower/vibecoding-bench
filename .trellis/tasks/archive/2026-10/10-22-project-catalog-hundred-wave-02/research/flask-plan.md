# Flask场景任务表

固定d086db856be187255b8ec61ef409357393020f32，完整236文件，BSD-3-Clause。已读Flask构造／test_client、会话和g上下文、flash／get_flashed_messages、DefaultJSONProvider、Config.from_prefixed_env及add_url_rule副作用顺序；真实WSGI客户端沿上游测试使用，不监听业务端口。

当前目标完整默认pytest494通过，无skip；真实async及dotenv依赖保留。固定源码绑定提供规范化3.2.0.dev0元数据和原声明的私有flask命令，不安装另一份Flask。五条业务256MB／30秒全部通过。

| 任务 | 业务价值 | 独立验收与授权 |
| --- | --- | --- |
| FL-U01 理解 | cookie会话与局部状态 | 客户端1／2／另一客户端1，局部g各1；只读 |
| FL-U02 理解 | 类别展示与队列消费 | 后续请求warning已消费，同请求缓存仍可分别展示 |
| FL-C01 咨询 | 审计日期精度和金融类型 | HTTP秒日期丢微秒、Decimal字符串，明确现有provider定制 |
| FL-C02 咨询 | 环境JSON和嵌套现有能力 | int／bool／带零字符串／原串回退，不重复发明加载器 |
| FL-P01 方案 | 完整配置验证后发布 | 数字父键冲突前已写A_FIRST／DATABASE，不能假定回滚 |
| FL-D01 诊断 | 注册异常后的错派 | 完整endpoint／view／map证据后定位，或无材料收口 |

五场景六任务均只读。只使用合成secret与空环境，不用真实账户、服务或生产配置；调用方方案不冒充库修复。产品链／页面／正式交付另核。
