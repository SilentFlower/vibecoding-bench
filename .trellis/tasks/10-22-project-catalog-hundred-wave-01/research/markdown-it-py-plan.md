# Markdown-it-py编辑预览和引用工作场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](markdown-it-py-admission.json)为准。

## 来源和入口

固定 `executablebooks/markdown-it-py@6f586542653a56d2ee8549a0dccfaa6ba5ebe14a`，完整181文件、MIT许可和原AGENTS保留。已读MarkdownIt构造／预设／启用规则／注册渲染器／parse/render、Token真实字段、RendererHTML.renderToken和原生references测试。当前镜像使用tox中相同的tests/原生集合，1032项全过，包含CommonMark语料和实际flit sdist测试；不称运行了tox多版本、外部plugins仓库、benchmark或文档检查。

## 四场景八项独立任务

| 场景 | 任务 | 用户价值和实际验收 |
| --- | --- | --- |
| IT-S01 编辑器token映射 | IT-U01 理解 | 块opening／inline／closing与inline.children，map是半开行区间 |
| IT-S01 | IT-C01 咨询 | 编辑器定位现有map的能力和界限，不虚构逐字符offset或简单靠HTML反推 |
| IT-S02 URL预览规则 | IT-D01 诊断 | linkify打开却无链接，先取预设、激活规则、依赖和实际输出再判断 |
| IT-S02 | IT-C02 咨询 | 完整明确复现下，options值与core规则激活是两个条件，已有enable即可满足 |
| IT-S03 链接渲染定制 | IT-U02 理解 | add_render_rule名称必须是实际token type，任意名字回调不会被调用 |
| IT-S03 | IT-P01 方案 | 用实际link_open回调和Token.attrSet／renderToken保持原链接和属性转义，无需改解析核心 |
| IT-S04 引用元数据边界 | IT-U03 理解 | 同文档重复定义保留首条并记录duplicate_refs，env是调用方传入的实际可变映射 |
| IT-S04 | IT-C03 咨询 | 复用包含references的env会影响新文档；独立文档新建env，不能把可选共享机制当自动隔离 |

八项均只读、requires为空。IT-D01有normal／diagnose_only／unavailable，初始规则不预填隐藏预设或原因。Linkify依赖已冻结；所有URL只作字符串处理，完全不发网络请求。自定义渲染回调仅在原生合成实验内执行，不改项目文件。

## 验收

七项原生程序事实和诊断实际披露分别评审；默认和材料不足入口进入真实Scheduler／driver／私有评审模拟，页面／API／SQLite、Git／Docker交付全部过后才正式准入。无工程目标不编造修复和代码接受。
