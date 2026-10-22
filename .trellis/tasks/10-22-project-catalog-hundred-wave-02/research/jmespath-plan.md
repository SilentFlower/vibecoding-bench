# JMESPath场景任务表

固定提交2812594e69d43098ef60f81f4efc404c071b0418，MIT，完整62个Git文件。已读Parser.parse／ParsedResult.search、实际TreeInterpreter、Functions注册／类型检查及相关原生测试。当前镜像完整tests（包含compliance和legacy、无JMESPATH_TEST裁剪）992主项，991通过、1个Python2 long条件跳过。

| 任务 | 实际业务价值与源码事实 | 材料、授权与验收 |
| --- | --- | --- |
| JM-U01 理解 | 投影省略null，map保留行位置，0／false保留 | 完整数据；只读；两个真实API结果精确对照 |
| JM-D01 诊断 | 空发货标识先取查询和字段类型 | 按请求披露，或无材料正常收口；不授权改库 |
| JM-C01 咨询 | 区分truth fallback、null fallback和键存在 | 完整0／false／空串和缺失控制；只读 |
| JM-C02 咨询 | 混合价格先声明转换和无效数据政策 | 原生类型错误与数值转换排序B/A；输入不变 |
| JM-U02 理解 | 可变字面结果会共享缓存中的对象 | 真实compile／search及拥有副本控制；不承诺所有结果复制 |
| JM-P01 方案 | 用显式受信Options隔离仓库业务函数 | 真实函数、类型拒绝、普通调用及builtin控制；不执行不受信Python |
| JM-M01 修改 | 嵌套JSON的布尔类型不能被当成数字比较 | 仅visitor.py与公开测试授权；双向／过滤／深层反例和完整原生回归另验 |

比较目标依据[官方Equality Operators](https://jmespath.org/specification.html#equality-operators)：布尔字面保留自身类型，容器比较遵循其成员的相等规则。固定源码只在最外层排除布尔／数字的Python等价，嵌套容器直接使用Python比较，须用当前原版实际复现后才计缺陷。任务只修比较运算符，不将contains或其他非JSON扩展一并改写。

五场景七任务，无虚假answer／code依赖。当前定义和原生基线不代表业务、产品链、页面／API／SQLite或正式交付通过；以后续同名admission JSON为准。
