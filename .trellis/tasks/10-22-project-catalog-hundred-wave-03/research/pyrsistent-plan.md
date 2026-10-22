# Pyrsistent状态快照任务表

固定0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7，MIT及随源码保留的_toolz.py许可，完整71个Git文件；三个上游链接blob保留为普通目标文本。已读PMap/evolver、freeze、PClass构造、create、set、evolver和field真实类型、工厂及不变量实现。

| 任务 | 独立业务问题 | 授权、正常和反例 |
| --- | --- | --- |
| PS-U01 理解 | 外层持久映射与可变嵌套值 | 完整共享列表及freeze对照；只读；pmap不递归冻结，freeze不承诺任意自定义对象不可变 |
| PS-U02 理解 | 编辑草稿与已发布快照 | 同一evolver两次发布；只读；原值及首个快照保持，草稿仍可变 |
| PS-C01 咨询 | 类型检查与显式输入转换 | field与factory=int三控制；只读；字符串默认拒绝，工厂显式转换 |
| PS-C02 咨询 | 兼容未知字段的真实损失 | create严格与ignore_extra；只读；currency被丢弃，输入保持，不冒称保留或验证 |
| PS-P01 方案 | 区间两字段整体更新 | 不变量、set及evolver发布失败/恢复对照；只读方案；完整验证后发布，不承诺数据库事务或并发隔离 |

三场景五任务，无虚假依赖或为凑数增加诊断。业务只验映射/记录并明确Python向量回退；完整主基线独立编译真实pvectorc，638主项中637通过、1项上游跳过。额外官方80 doctest在独立进程通过；不把会被单测reload污染的doctest强行混跑。失败尝试全部保留，后续模拟及交付另验。
