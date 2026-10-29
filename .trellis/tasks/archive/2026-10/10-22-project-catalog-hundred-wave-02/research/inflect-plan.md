# Inflect场景任务表

固定提交99596854bd296af1557db2015cfa98c8104ec155、完整62个Git文件。已读AGENTS及其指定的完整skeleton文档、原pytest.ini／pyproject，实际engine构造、classical／num、plural_noun／singular_noun、defnoun、a、number_to_words、join及相关模式定义。模型场景只处理有界合成英语，不接远程词典或NLP服务。

原始Git无LICENSE。保留原构建生成MIT原文（其中copyright holders是占位，未伪称原作者署名）和源码Copyright(C)2010 Paul Dyson实际归属，在seed/app独立保存及记录SHA，不修改固定Git文件。当前镜像275通过、16个上游xfail、0普通skip，含10个原生doctest；完整冻结原有预期与资源。

| 任务 | 独立业务价值 | 授权及验收 |
| --- | --- | --- |
| IF-U01 理解 | 持久计数与显式覆盖／重置 | child四个精确控制；只读 |
| IF-C01 咨询 | 冠词规则和计数不自动词形变化 | hour／university／MRI／2 hour；只读 |
| IF-C02 咨询 | 已存在的case preserve自定义规则 | URLs与普通词／新引擎控制；无需新API |
| IF-U02 理解 | 宽松读数不是数值语法验证 | 字符串1e3／abc、数值1000与12.30；只读 |
| IF-U03 理解 | 人工列表标点不是CSV | 三项／逗号／两项／空值；只读 |
| IF-P01 方案 | 独立引擎归属和报表隔离 | count／names状态和独立实例控制；不实现服务 |
| IF-D01 诊断 | 大小写与默认names模式 | 披露完整词及模式，或无材料收口；不猜改库 |
| IF-M01 修改 | 未知模式键不应部分改变状态 | 仅初始化实现、公开测试、指定newsfragment；原版／参考／错误候选／全回归另验 |

五场景八任务，七项非修改。普通调用和方案无虚假代码依赖，变更片段遵守上游骨架流程而不发版。产品链与交付另验，正式状态以后续admission为准。
