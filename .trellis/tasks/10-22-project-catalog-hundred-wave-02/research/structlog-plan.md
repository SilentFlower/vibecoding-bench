# Structlog场景任务表

固定19c4f21059e853114efa7a93b6e675d93bf7934e，完整123文件，MIT OR Apache-2.0、NOTICE／COPYRIGHT原件保留。已读BoundLoggerBase绑定／事件合并、lazy proxy／configure、get_context、contextvars、JSONRenderer回退、capture_logs和KeyValueRenderer排序器。

当前镜像完整949主项：928通过、21原生skip，跳过原因逐项冻结。上游pytest-randomly按显式seed0可复跑，保留所有节点及插件；不裁剪集合。原生依赖安装不包含另一份Structlog实现。仅私有dist-info按固定源码和真实构建元数据0.1.dev1提供Summary／Author-email／许可与有序Project-URL；首个Documentation不能按字母排序而改变兼容__uri__。标准分发读取器及头注入拒绝测试通过。五条业务全部实际通过。

| 任务 | 业务价值 | 独立验收与授权 |
| --- | --- | --- |
| SL-U01 理解 | 绑定与嵌套对象归属 | 顶层隔离、调用覆盖、payload共享与捕获身份；只读 |
| SL-C01 咨询 | 请求上下文优先级 | contextvars setdefault、bound／call优先、clear边界 |
| SL-C02 咨询 | 领域JSON和金融类型 | __structlog__与default=str替换、Decimal repr／字符串 |
| SL-U02 理解 | 测试捕获的真实覆盖范围 | capture默认绕过全局处理器、显式processors控制及恢复 |
| SL-P01 方案 | 嵌套日志出站 | JSON不会脱敏或递归业务解码，明确schema／归属／发布 |
| SL-D01 诊断 | 显式None丢失 | 精确事件／renderer选项后定位missing哨兵混用，或不足收口 |

五场景六只读任务，无真实远程日志、修改接受或虚构依赖。全平台、typing／文档／性能矩阵和可选未安装后端不冒称通过；真实模型调用为0。
