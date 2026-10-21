# CLI Helpers真实数据导出场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](cli-helpers-admission.json)为准。

## 来源和事实

固定 `dbcli/cli_helpers@e2538b1d338ead4ed803ec0017017bf6779a380b`，完整59文件和BSD-3-Clause许可保留。已完整读取输出注册／format_output／类型扫描、JSONL、CSV、tabulate适配以及缺值和字节预处理定义。当前镜像原生96项：92通过、4跳过；真实依赖包含tabulate 0.10.0而非本阶段另仓的开发版。

## 四场景八任务

| 场景 | 任务 | 问题和合法结果 | 实际程序事实 |
| --- | --- | --- | --- |
| CH-S01 导出介质 | CH-U01 理解 | 显示表、CSV、JSONL对中文、逗号和None的表达 | 实际消费输出迭代器，标准csv/json独立解析 |
| CH-S01 | CH-C01 咨询 | 人读报表与机器导出如何选 | 已有格式与消费方式；漂亮表格不能当无损交换 |
| CH-S01 | CH-P01 方案 | 规划明确列、缺值、类型和写入的导出合同 | 显式字段与标准序列化验证，不声称所有适配惰性常量内存 |
| CH-S02 JSON业务边界 | CH-D01 诊断 | 完整复现中两个id列为什么只剩一个 | dict(zip(...))同名覆盖，Decimal转float并非精确保真 |
| CH-S02 | CH-C02 咨询 | 无需改库时如何满足唯一列与小数字面保真 | 应用预校验唯一列、需要时显式预格式化Decimal字符串 |
| CH-S03 选项隔离 | CH-D02 诊断 | 前次missing_value影响新实例的默认输出 | class注册的formatter_args被update修改 |
| CH-S03 | CH-M01 修改 | 调用覆盖只影响本次，不污染注册／调用方默认 | 原版失败、参考通过、仅修内置格式反例拒绝及完整96节点回归 |
| CH-S04 一次性行输入 | CH-C03 咨询 | 行生成器被类型扫描耗尽时的兼容办法 | 真实generator-of-generator缺数据，有限输入先固定每行可正常输出 |

七项非修改、一项修改，全部requires为空；诊断材料完整，不制造无意义取证分支。选项场景含normal、diagnose_only与modify_direct。

## 修改合同

只授权现有 `library/cli_helpers/tabular_output/output_formatter.py` 和 `library/tests/tabular_output/test_output_formatter.py`。每次调用从注册默认构造独立的顶层选项映射，再应用本次kwargs；覆盖优先级保持，内置和自定义注册格式同样适用，跨实例／重复调用／延迟消费不串。注册者传入的默认字典不被format_output修改，其他格式默认不受影响。

这是顶层kwargs覆盖隔离，不是递归深复制任意样式对象或约束第三方handler内部修改嵌套对象。保留返回迭代器、预处理顺序、公开签名和现有依赖；不顺便修颜色全局状态、Decimal策略或一次性行输入。公开测试须在原版失败、参考成功；原版96节点独立保留。

当前为逐仓设计，原生业务／参考和真实产品链通过前不计正式准入。
