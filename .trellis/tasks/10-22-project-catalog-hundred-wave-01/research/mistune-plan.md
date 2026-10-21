# Mistune真实文档处理场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](mistune-admission.json)为准。

## 来源与事实

固定 `lepture/mistune@4bbaa04c391d650a2e1219781c9a9acd60571cce`，完整148文件及BSD-3-Clause许可保留。已读取create_markdown／markdown／html入口、完整CLI、Markdown状态创建、MarkdownRenderer核心表示和真实CLI测试。当前镜像原生1324主项、158子项全过，不能只报主项掩盖子项。

## 四场景八任务

| 场景 | 任务 | 业务问题与合法结果 | 实际事实或工程验收 |
| --- | --- | --- | --- |
| MS-S01 文档配置 | MS-U01 理解 | html快捷入口和markdown默认输出为何不同 | 原始HTML转义及table/strikethrough默认插件实际对照 |
| MS-S01 | MS-C01 咨询 | 用已有工厂明确插件与HTML策略 | 显式create_markdown配置，无需改库 |
| MS-S01 | MS-P01 方案 | 规划可复用的本地文档转换配置 | 顺序复用、明确插件／renderer与逐文档状态，不虚构任意并发安全 |
| MS-S02 编辑器AST | MS-U02 理解 | renderer='ast'返回对象还是文本 | 实际list及JSON序列化，HTML与AST用途区分 |
| MS-S02 | MS-C02 咨询 | CLI AST断言失败时已有API如何兼容导出 | 原CLI未序列化list；应用用API和json.dumps输出，不假装已有CLI JSON能力 |
| MS-S03 空文档CLI | MS-D01 诊断 | 空stdin／显式空-m为何报缺输入而空文件成功 | 真值分派与None/空串区别，API空文档合法 |
| MS-S03 | MS-M01 修改 | 区分空文档和交互无输入，保留输出与优先级 | 原版失败、参考通过、直接返回不写文件反例拒绝、完整回归 |
| MS-S04 Markdown重排 | MS-C03 咨询 | 重新渲染是否保留原始标记字节 | __strong__规范化为**strong**，实际HTML含义保持而源文本不同 |

七项非修改、一项修改，所有requires为空；公开材料自足，不制造追问分支。CLI场景有normal、diagnose_only、modify_direct。

## 空文档修复合同

只授权 `library/src/mistune/__main__.py` 和 `library/tests/test_cli.py`。空管道输入和显式 `-m ''` 都是已提供的合法空文档，退出0并经正常输出路径；`-o`必须创建真实空结果文件。显式消息包括空消息均优先于-f；已有非空消息／文件和文本0保持。交互TTY无参数时仍立即提示并非零退出，不阻塞等待输入；缺文件非零退出。不得顺便新增CLI AST JSON、改变默认插件、输出语义或测试控制。

独立程序通过真实候选模块、零字节文件、输出文件、显式空消息加非空文件、缺文件和PTY矩阵核验。错误候选在空串时直接return，会漏掉-o写文件；不能通过。原版1324主项／158子项独立保持，公开新增测试另核原版失败与参考成功。当前仅为设计，业务及整链尚待准入。
