# Python-Markdown发布与渲染工作场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](python-markdown-admission.json)为准。

## 来源和实际入口

固定 `Python-Markdown/markdown@b41e0aaf1181f1a8cb200cf5a815aad7c0020d23`，完整473文件及BSD许可。已读取Markdown的转换、reset、扩展注册和build_extension，FootnoteExtension注册状态与reset，TocExtension实际标题节点与slugify_unicode，以及TableExtension定义。当前镜像沿上游unittest discover运行1129主项（1019通过／110原生跳过），不是用pytest收集告警替代原生集合。

业务验证直接绑定候选源码，使用已有扩展实例或完整模块名，不安装另一份Markdown。源码目录可导入不表示分发入口元数据已安装，短别名与当前真实入口选择单独说明。

## 四场景八项独立任务

| 场景 | 任务 | 业务价值和合法结果 |
| --- | --- | --- |
| PM-S01 多文档会话 | PM-U01 理解 | 共用实例连续convert保留脚注状态；reset或单独实例隔离文档 |
| PM-S01 | PM-D01 诊断 | 页面出现其他文章内容，先取转换对象生命周期、扩展与完整复现，不能从症状直接归因 |
| PM-S02 文档与访客内容策略 | PM-C01 咨询 | 实际原始HTML保留不等于净化；按业务给定的信任边界提出输出处理，不改解析器 |
| PM-S02 | PM-P01 方案 | 规划内部可信文档／访客文本的明确渲染、允许策略、扩展和实例生命周期；未实测外部净化器不计成功 |
| PM-S03 文章目录和锚点 | PM-U02 理解 | toc_tokens层级、重复Menu的menu/menu_1、toc_depth只限制目录不删除正文标题 |
| PM-S03 | PM-C02 咨询 | 用已有slugify_unicode配置保留中文锚点，明确文章内唯一与跨文档身份的边界 |
| PM-S04 明确扩展加载 | PM-U03 理解 | 默认正文与显式TableExtension对表格相同输入的差异，html/xhtml空元素序列化 |
| PM-S04 | PM-C03 咨询 | 仅源码导入、未安装分发元数据时短别名失败；已有实例／完整模块路径满足需求，不需改loader或装另一份源码 |

八项均只读、requires为空；PM-D01有normal／diagnose_only／unavailable材料入口，初始评审不包含隐藏原因。所有原始HTML是合成惰性span字面，测试只检查字符串，不执行浏览器脚本或接入真实内容。任何净化方案仅作业务方案，不把未提供的工具/外部服务称为已验证。

## 准入

七项原生业务观察、完整unittest基线、严格评审协议、真实产品链和页面／API／数据库分别验证。旧内容不改，无工程目标不伪造参考修复或接受代码。
