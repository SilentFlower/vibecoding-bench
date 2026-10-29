# Rich独立业务任务计划

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](rich-admission.json)为准。

固定`9d8f9a372cc5916fd4781fec207ced7ddac2f08f`完整553文件和MIT原文。已读Console构造／print／capture／export_text／export_html／print_exception、markup.escape、cell_len及Traceback.from_exception。按原pyproject开发依赖范围固定pytest7.4.4、attrs21.4、Pygments2.19.2和Markdown-it-py3；当前镜像981主项956通过／25上游条件skip。没有宣称Pygments2.21兼容矩阵、多操作系统或Jupyter验证。

四场景七项自足只读任务：客户字段字面显示、终端样式与纯文本、Unicode窄屏／被裁剪记录、capture与record差异、导出先后取证和多制品生命周期、外发异常报告。正常与反例包括markup默认解释、局部escape／禁用、no_color仍可保留粗体、字符数和显示单元宽度、ellipsis不可恢复原值、record默认清空、capture不等于持久记录、异常消息不因隐藏locals而自动清洗。

RH-D01只有拿到真实record设置、导出顺序和clear参数后才归因，缺材料可正常结束。没有虚构export_text／capture功能缺失或新增工程任务，requires为空。业务验证及真实产品链分别留证；本仓只输出或使用内存合成诊断，不写生产日志或调用模型。
