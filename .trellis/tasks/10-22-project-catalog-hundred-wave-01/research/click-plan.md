# Click真实工具命令场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](click-admission.json)为准。

## 来源与范围

固定 `pallets/click@2247b35ea1c47c727d7a06e51fa280e12a863ff6`，完整178文件及BSD-3-Clause许可保留，源码版本8.6.0.dev。已重读异常完整定义、参数来源接口、Path.convert和CliRunner真实结果／invoke接口。当前镜像全原生集合2287项：2262通过、24跳过、1预期失败；沿上游默认排除31000项stress参数组合，不删适用集合。

## 四场景八项独立任务

| 场景 | 任务 | 业务问题／合法结果 | 独立程序事实 |
| --- | --- | --- | --- |
| CK-S01 批处理参数 | CK-U01 理解 | repeated tag、Choice和IntRange如何转换 | CliRunner真实解析tuple、大小写规范值及范围拒绝 |
| CK-S01 | CK-C01 咨询 | 多值选项与变长位置参数如何选 | multiple已有，逗号不自动分割，Argument(nargs=-1)与Option限制不同 |
| CK-S02 配置来源 | CK-U02 理解 | 命令行、环境、default_map和声明默认优先级 | 真实值及ParameterSource逐项核对 |
| CK-S02 | CK-C02 咨询 | 想解释默认来源时是否需要重写解析器 | 已有get_parameter_source适用直接解析；未知invoke来源不能伪称COMMANDLINE |
| CK-S03 输出文件 | CK-C03 咨询 | Path(exists=False)是否禁止覆盖 | 真实已有和未有路径均接受，已有API语义不应错误改写 |
| CK-S03 | CK-P01 方案 | 规划明确的拒绝覆盖与原子发布策略 | 已有路径预检不是排他创建；区分x模式、替换和应用并发合同 |
| CK-S04 可操作错误 | CK-D01 诊断 | 已提供完整add_note复现却只显示主消息 | 当前ClickException.show／UsageError.show没有输出附注，不当解析失败 |
| CK-S04 | CK-M01 修改 | 明确授权在受控错误输出中展示附注 | 原版失败、参考通过、仅修ClickException的反例拒绝及完整回归 |

七项非修改、一项修改，全部requires为空。诊断已有完整材料，无需虚构追问分支。错误场景有normal、diagnose_only和modify_direct，修改入口自足。

## 附注增强合同

仅授权现有 `library/src/click/exceptions.py` 和新增公开回归文件 `library/tests/test_exceptions/test_click_exception.py`。已核原tests/test_exceptions目录及原文件，新增测试不会替代原集合。保留无附注错误的字节、既有usage／help提示、退出码1／2、指定输出流和原色彩策略；不输出traceback。不更改消息格式函数，防止上层使用format_message时意外带附注。

对ClickException和UsageError按add_note顺序在主消息后输出非空附注，每项用一次 `Note: ` 前缀，保留Unicode和内部换行；空字符串附注忽略。Python3.10缺少__notes__时正常原样输出，不能依赖原生add_note方法一定存在。公开测试必须在原版失败、参考通过，完整冻结集合独立保留。

退出1／2、usage出现一次、基础／UsageError两种路径、无附注控制、彩色附注在color=False时按echo策略去色构成独立矩阵。只修父类show不能满足子类覆盖的UsageError路径，错误候选必须被拒绝。当前为设计，未计正式内容。
