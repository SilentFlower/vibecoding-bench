# AnyTree场景任务表

固定2e0版本的完整Git来源（精确提交见source-index.json及逐文件来源证明），Apache-2.0，129个跟踪文件。已读NodeMixin父子关系守卫、Node、PreOrderIter、Resolver、DictImporter／DictExporter及JsonExporter真实定义。当前目标原生集合234通过、1项上游Graphviz跳过，包含72项doctest；完整节点身份和独立结果已冻结。

| 任务 | 业务价值与独立验收 |
| --- | --- |
| AN-U01 理解 | 循环／重复拒绝保留被测树；合法迁移保留身份并追加到新父节点 |
| AN-U02 理解 | 隐藏节点与裁剪子树分别选择，根算第一层 |
| AN-C01 咨询 | 同名兄弟get取首项，glob保留多项，业务身份需明确 |
| AN-C02 咨询 | 输入、节点和输出共享嵌套payload，顶层复制不是深快照 |
| AN-P01 方案 | JsonExporter会改写传入字典导出器深度，预览／完整导出各自持有配置 |
| AN-D01 诊断 | 完整slots／mixin／异常证据后核__dict__表示，或无材料收口 |

四场景六任务均只读。五条原生业务独立期望256MB／30秒通过，不运行Graphviz、不写库、不作发布。产品链与正式Git／Docker交付另核。
