# python-pptx场景任务表

固定提交278b47b1dedd5b46ee84c286e77cdfb0bf4594be，完整798文件、MIT。已读Presentation包入口、TextFrame／Paragraph／Run、SlidePlaceholders、Table／Cell合并拆分、CategoryChartData／Chart.replace_data及RGBColor.from_string完整相关定义；保留模板、测试和二进制原件。

当前镜像完整pytest2700通过，无skip。额外官方Behave54features／973场景／2914步骤通过，步骤不计测试／任务。全部只读，因此额外原版BDD证据不冒充修改候选回归；不运行Office、渲染或公式重算。五条实际业务全部通过。

| 任务 | 业务问题 | 独立验收与授权 |
| --- | --- | --- |
| PP-U01 理解 | 段落与软换行 | 同字符串在框／段落两个setter的保存重开和a:br控制 |
| PP-C01 咨询 | 模板填充格式作用域 | 框替换丢直接bold、run替换保留；继承格式另论 |
| PP-U02 理解 | 有空洞的模板槽位键 | 仅内存构造idx0／7模板，key1失败、key7成功，不修改库原件 |
| PP-C02 咨询 | 合并网格与文本可逆性 | PPTX独立格、is_spanned／origin、split不归还原文本 |
| PP-P01 方案 | 图表交付一致性 | replace_data后缓存与嵌入XLSX均30／40；完整验收再发布 |
| PP-D01 诊断 | 非标准颜色长度的规范化 | 精确字面／调用／结果后核切片与通道范围，或不足收口 |

四场景六任务均只读，没有工程授权、接受检查点和虚构依赖。产品链、UI／API／数据库及Git／Docker正式准入另核；mock不代表真实模型质量。
