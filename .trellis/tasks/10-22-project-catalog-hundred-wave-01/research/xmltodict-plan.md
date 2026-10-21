# xmltodict真实订单交换任务设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](xmltodict-admission.json)为准。

## 来源与已核事实

固定 `martinblech/xmltodict@6e29fba282e68631034dd2722a413b4e35276584`，MIT许可，完整22个Git文件与原始AGENTS／README保留。已完整读取657行实际模块、parse／unparse签名、SAX数据处理、流式回调、命名空间及输出规则；当前Python3.12.15镜像原生tests134项通过。额外依赖defusedexpat的示例doctest不属于本次适用基线，不冒称其已通过。

## 五场景与十一项独立任务

| 场景 | 任务 | 类型 | 用户问题与合法结果 | 实际程序事实或验收 |
| --- | --- | --- | --- | --- |
| XD-S01 订单结构 | XD-U01 | 理解 | 属性、文本及单／多子元素为何得到不同Python结构 | 实际解析订单，属性保留@、qty默认为字符串，force_list统一形状 |
| XD-S01 | XD-C01 | 咨询 | 用已有force_list统一单订单和多订单，是否需要改库 | tuple／callable已有能力及路径选择，不强制所有节点变列表 |
| XD-S01 | XD-P01 | 方案 | 规划订单业务字段验证和导入边界 | XML解析与数量／ID等应用校验分层，不声称库自动做业务schema或数字转换 |
| XD-S02 命名空间证据 | XD-D01 | 诊断 | KeyError症状不足，先取实际XML、parse参数和访问路径 | 按实际请求披露完整命名空间复现；不可提供入口可正常insufficient_information |
| XD-S02 | XD-C02 | 咨询 | 用已有URI映射稳定业务键，保留必要命名空间语义 | 实测process_namespaces及URI→短名／None映射，不保证任意前缀词法往返 |
| XD-S03 输出与保真 | XD-U02 | 理解 | 空列表、None与显式空元素为什么输出不同 | 真正写XML并由ElementTree独立检查空节点是否存在 |
| XD-S03 | XD-C03 | 咨询 | 混合内容、空白及前缀是否能逐字节往返 | 实测混合内容顺序差异，解释便利dict模型的既有边界，建议保真场景选合适工具 |
| XD-S04 分块输入 | XD-D02 | 诊断 | 普通list_iterator为何失败而generator可用 | 完整正常分块复现；这是尚未承诺的输入增强，不将其包装为所有解析路径缺陷 |
| XD-S04 | XD-M01 | 修改 | 支持同步普通chunk Iterator，保留原输入与回调语义 | 原版失败、参考通过、错误拼接候选拒绝及完整134项上游回归 |
| XD-S05 流式订单 | XD-C04 | 咨询 | 分块输入是否就意味着按订单输出、回调如何停止 | 实测item_depth／callback、正常None返回和ParsingInterrupted，不声称返回惰性订单迭代器 |
| XD-S05 | XD-P02 | 方案 | 规划有界逐条校验和可中止本地导入 | 真实回调消费与错误中止，区分文档原子提交、已提交前缀和单项内存 |

五场景／十一任务，十项非修改、一项修改。各场景从独立原版开始，全部requires为空，不因任务顺序制造answer或code依赖。

## 材料和入口

XD-D01初始只给缺字段症状，不给隐藏XML、具体URI或解析选项。normal／diagnose_only均允许按实际需求披露完整复现；unavailable说明无法提供材料，不能无条件披露或提前在rubric断言根因。后续独立咨询任务明确给出所需完整公开材料。

分块场景提供normal、diagnose_only与modify_direct。修改公开材料自足，只授权 `library/xmltodict.py` 和 `library/tests/test_xmltodict.py`；无需先诊断或承接其他场景代码。原始源码、英文说明、中文展示与业务中文值分别保留。

## XD-M01的精确兼容合同

- 新增支持同步Iterator中的文本／字节chunks，包括list_iterator、map和自定义__iter__／__next__对象；不把普通list容器、异步源或全新增量Parser接口一并列入目标。
- str、bytes、bytearray、memoryview保持整份文档语义；已有可读文件优先走read，既有generator和parse参数保持。不得通过全量join／list把输入先缓冲到内存。
- 合法字节分块跨UTF-8边界可正常解析；非法chunk保持TypeError，源迭代异常保持传播，截断XML在最终解析阶段失败。混合类型只按原generator／Expat既有行为，不额外伪称全部组合有效。
- item_depth与callback照常；回调拒绝时ParsingInterrupted立即向外传播，不能继续耗尽后续输入。保持默认实体禁用、命名空间和其他现有选项。
- 有意义的公开新增测试须在原版失败／参考通过；可信回归使用原版完整134节点，候选新增测试不替代它。错误的先join候选必须被提前中止／源消费边界反例拒绝。

## 独立程序与状态

只读任务核实际parse结构、文件／ElementTree输出、命名空间和回调，不匹配答案文字；D01仅按实际消费对话评审。修改直接调用多种真实输入、异常和停止边界，不限定修复实现方式。当前仅完成原生基线校准，新业务、工程参考和mock尚未通过前不计正式准入。
