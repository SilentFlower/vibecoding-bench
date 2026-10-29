# Mistletoe场景任务表

固定提交ebf9ae4e9279f3d8c79b7cf2710f7e73ea6438a7、完整91个Git文件。已读Document／Heading、完整Token及traverse、BaseRenderer、HtmlRenderer选项与link／heading输出、MarkdownRenderer构造／render／RawText及完整TocRenderer；保留MIT与CommonMark／原Markdown／jQuery样本各自许可及真实归属。原始源码不修改。

当前目标镜像完整原生349主项通过、1上游skip、另3个subtest通过（JUnit353）；另外实际官方python -m test.specification --ignore-known完整652例通过，KNOWN为空。额外官方入口只证明完整固定原版，不替代可修改候选回归；本仓场景全为非修改。Pygments2.16.0按上游要求冻结，不改原测试或约束。

| 任务 | 独立业务价值 | 验收与授权 |
| --- | --- | --- |
| MT-U01 理解 | 标题字段的共享状态与节点真实文本 | 两标题content／children／HTML对照；只读 |
| MT-U02 理解 | BFS、深度过滤和已存在父关系 | 根／兄弟／Strong与depth1控制；不虚构缺失API |
| MT-C01 咨询 | 原HTML选项和链接政策 | 实际文本输出，不执行危险目标；不冒称sanitizer |
| MT-U03 理解 | Markdown回写可能改变语义 | 数字实体字面值前后HTML及反斜杠既有保护对照；不批量改写 |
| MT-D01 诊断 | 空目录与过滤选项 | 按请求披露title-only复现或无材料收口；不自动修库 |

四场景五项非修改。固定原版的缺口可以支持解释、咨询或诊断，不能借此默认为修改授权。原生、业务、产品链与交付分别核实；正式状态以后续admission为准。

首次业务输入混淆反斜杠转义和实体解码，MT-U03未通过；已按原render_escape_sequence与历史实际复现校正为数字hash实体，并保留反斜杠成功对照。失败控制输入和结果留存，仅重跑受影响业务，不改原生测试或独立期望。
