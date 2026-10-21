# Tabulate真实报表场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](tabulate-admission.json)为准。

## 来源和已核事实

固定 `astanin/python-tabulate@268615a5c27dc40e5c22454c07b44d5c50410da0`，完整26文件与MIT许可保留。重新读取真实tabulate签名、数据归一化、类型推断、格式化、宽度展开、HTML与CLI定义。目标Python3.12.15基线为383收集、366通过、17跳过，包含17个doctest；不将开发提交冒称发布版，也不把可选numpy/pandas缺失分支说成通过。

## 五场景九项独立任务

| 场景 | 任务 | 问题和合法结论 | 实际验证 |
| --- | --- | --- | --- |
| TB-S01 商品报表 | TB-U01 理解 | 混合数字形标识符与金额如何被列类型推断改变 | 同列00123和1e3实际显示123和1000，金额用默认g格式 |
| TB-S01 | TB-C01 咨询 | 已有disable_numparse按列保护标识符，同时格式化金额 | 标识符原文保留，金额.2f，输入不变，无需改库 |
| TB-S01 | TB-P01 方案 | 规划报表字段、缺值、金额和机器导出边界 | 显式列顺序、missingval及真实格式；不把漂亮表当可靠CSV交换 |
| TB-S02 数据取证 | TB-D01 诊断 | 标识符显示变化症状不足，先取原值、调用和输出 | 正常按需求披露真实复现；无法提供可insufficient_information |
| TB-S03 序列参数 | TB-D02 诊断 | list正常、tuple失败的排版配置 | 实测rowalign和maxheadercolwidths，定位_expand_iterable的tuple+list |
| TB-S03 | TB-M01 修改 | 两种配置的tuple/list结果一致，保留默认和调用方对象 | 原版失败、参考通过、只修rowalign的反例拒绝，完整383节点回归 |
| TB-S04 输出介质 | TB-U02 理解 | html与unsafehtml对普通标记文字的区别 | 普通<b>商品</b>按文字转义与显式原始标记对照，不构造攻击内容 |
| TB-S04 | TB-C02 咨询 | 中文终端表的单列换行与整表宽度保证 | wcwidth实际显示列宽；maxcolwidths不等于总表预算，使用已有配置并说明限度 |
| TB-S05 本地CLI | TB-U03 理解 | CSV与JSONL的实际读取、表头和输出文件 | 真正执行候选python -m tabulate，核CSV引用逗号、JSONL keys与不支持格式退出码 |

八项非修改、一项修改；全部requires为空。TB-D01不提前提供根因；咨询和理解公开足够材料。序列场景有normal、diagnose_only和modify_direct，其余取证场景有normal、diagnose_only和unavailable。

## 工程目标边界

仅授权 `library/tabulate/__init__.py` 与 `library/test/test_api.py`。在现有序列展开路径支持tuple，保持相同list输出、短序列补齐、现有长序列规则、空tuple与默认值，不修改调用方list/tuple。不新增生成器支持、公开签名、依赖、数值策略或pytest控制。原生参考保留完整原版doctest正文和全部适用节点，新增公开测试另做原版失败／参考成功对照。

候选只在tabulate入口转换rowalign的错误实现会漏掉maxheadercolwidths；独立反例必须拒绝。当前仅冻结设计和实际复现，不计正式准入；真实产品链、页面及交付另验。
