# python-docx场景任务表

固定提交e45454602b53e8e572b179ccf1c91093ec9f4ed7、MIT、完整625个Git文件及真实DOCX／图像原件。已读Document公开入口及代理、Paragraph／Run文本与格式、Table／Cell合并和网格、StoryChild.part、核心日期读写／W3CDTF解析、批注创建与保存；不以字段名猜实现。

当前目标镜像完整pytest1609通过，无skip；另实际官方Behave完整67features／650场景通过，步骤单列，不冒充测试／任务数量。pytest8.4.2／pyparsing3.2.3按原声明及真实兼容结果固定，未改原测试或warnings=error。不运行Word／LibreOffice、分页／重算或真实文件发布。本仓全部只读，额外BDD原版证据不冒充修改候选回归。

| 任务 | 独立业务价值 | 授权与验收 |
| --- | --- | --- |
| DX-U01 理解 | Paragraph.text与Run.text格式作用域 | 保存重开及XML、段落样式和独立bold控制；只读 |
| DX-U02 理解 | 顶层段落／表格顺序 | 现有iter_inner_content与分离列表对照；不虚报缺失API |
| DX-C01 咨询 | 合并格的布局槽和唯一内容 | 实际grid_span／底层身份／XMLcell数量；不假设矩形 |
| DX-C02 咨询 | 日期wall clock标签与真实instant | aware直接写入和显式UTC控制；不默许丢时区 |
| DX-P01 方案 | 批注文档归属和关系闭合 | 合成外文档run问题与本地控制；验收后发布归应用 |
| DX-D01 诊断 | 空日期、缺失与非空非法值 | 按请求披露精确属性／XML或无材料收口；不自动修库 |

四场景六项非修改。调用方已有API、解释、明确政策或方案足以构成本批价值，不把每个历史缺口强制转为改库工程。正式产品链和Git／Docker准入另核，以后续admission为准。
