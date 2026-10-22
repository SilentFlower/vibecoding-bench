# mdit-py-plugins场景任务表

固定提交519953da0a394a92534bc27580f4e7415462df44，完整135文件。根AGENTS、原生tox配置及相关plugin公开函数、front_matter规则、anchors作用域、tasklists控件、footnote引用和GFM组合均已读。第三方markdown-it-py4.2.0实际公开parse／renderer签名亦核精确wheel。MIT、移植插件MIT／tasklists ISC、Djot MIT、GFM/CommonMark派生示例CC BY-SA归属分别保留，见补充许可证明。

当前镜像完整pytest511通过，无skip；五条业务均通过。元数据业务最初误把隐藏块前的合法换行视为失败，原件保留；诊断原件显示token／map／raw／YAML／env均正确，仅HTML首部多换行。最终按实际业务的正文与元数据分离要求核首尾空白以外的正文，保留同一布尔期望；调试额外字段随后移出严格生产结果，不修改插件、材料或原测试。

| 任务 | 独立业务价值 | 授权与验收 |
| --- | --- | --- |
| MD-U01 理解 | 一次parse同时取得raw元数据及HTML | hidden token／map、显式YAML、同tokens渲染，无新API |
| MD-U02 理解 | 多章节锚点作用域 | same／same-1、默认级别1..2、下一parse重置；现有slug配置 |
| MD-C01 咨询 | 可交互控件与持久状态 | enabled=True已有能力，checked／disabled独立HTML解析 |
| MD-C02 咨询 | 引用脚注和完整定义归档 | 两引用一note两backlinks、unused省略、inline开关现状 |
| MD-P01 方案 | 作者HTML与生成控件政策 | GFM不等于tag过滤，html=False转义作者script但保留生成控件 |
| MD-D01 诊断 | front matter源位置合同 | 首行／首字符证据后定位，或材料不足收口，不自动改库 |

五场景六任务均只读，无代码接受和虚构前置依赖。额外核心旧版本矩阵、tox外包装、typing／lint／文档构建未声称通过；本轮完整适用原生集合和真实产品链分别验收，正式准入以后续admission为准。
