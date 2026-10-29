# cssselect场景任务表

固定3069b6da75e1adf27939ca541dcc9fb9b961abc6，完整27文件，BSD-3-Clause与AUTHORS保留。已读Selector／parse相关分支、GenericTranslator两个入口与XPath prefix、命名空间name-test、HTMLTranslator模式及checked、has相对选择和scope限制。真实lxml公开调用沿上游测试核对。

当前目标完整cssselect／tests／docs的pytest+Sybil入口34主项通过，76原生子项另列，无跳过；不能沿用历史JUnit聚合110当本轮主项数。五条独立业务在256MB／30秒实际通过。未跑独立typing／lint／Sphinx发布或全浏览器CSS矩阵。

| 任务 | 业务价值 | 独立验收与授权 |
| --- | --- | --- |
| CS-U01 理解 | 局部选择的self与类词边界 | root／a／b真实XPath结果；只读 |
| CS-U02 理解 | 命名空间URI查询 | d映射默认URI、o映射另一URI、裸名与缺映射反例 |
| CS-C01 咨询 | 与解析树一致的名称大小写 | HTML／XML、类值Notice大小写、xhtml模式 |
| CS-C02 咨询 | 静态表单快照 | checked checkbox／selected option、text input与generic对照 |
| CS-P01 方案 | 查询能力准入与失败语义 | 支持has直接子项、scope嵌套语法错误，不当零匹配 |
| CS-D01 诊断 | 两个伪元素转换入口差异 | 精确入口／选项后定位或无材料收口，无生成内容虚报 |

五场景六任务均无修改与依赖；公开查询参数、完整合成树和错误分开供应。产品链、页面及正式交付另核，以后续admission为准。
