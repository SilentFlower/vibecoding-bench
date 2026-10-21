# Docutils独立业务任务计划

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](docutils-admission.json)为准。

固定`3577cb69446ed0c94c15f9b0836571d6d5c46882`的完整2970个monorepo条目，核心源码在`docutils/docutils`。保留docutils/COPYING.rst及各BSD／GPL原文，不把混合许可仓概括为MIT。18个Git链接保留原目标blob并明确存为普通文本；仅私有原生测试树内，把六个已核CSS测试别名从受控实际目标复制为普通文件，不制造源码链接或修改冻结原件。

已读core发布API、Reporter、nodes遍历、Include／Raw及HTML发布原生测试。当前目标镜像标准unittest入口459主项为457通过／2skip，内部1776子项；主项与子项分别冻结。两处skip理由实际保留：HTML4原测试对Pygments>=2.14主动跳过旧高亮预期；外部数学转换器须独立运行。Pygments2.21实际已按profile安装，不能把原测试简写的requires pygments解释成未安装。与历史456／3skip／1775子项的差异不冒称同一次实测。

五场景八项独立只读任务：文档标题提升／输出形态、未解析引用取证／构建失败阈值、投稿raw/include限制／展示方案、显式稳定锚点、带引用及Unicode的CSV表格。正常和反例包括默认与关闭标题提升、bytes／str边界、报告级别与终止级别、真实允许include与禁用控制、改标题后显式ID、逗号字段与多字节内容。

DU-D01初始只取完整原文和设置，不预判隐藏语法或引用错误；缺材料可正常关闭。file_insertion_enabled和raw_enabled只承诺对应指令行为，不声称全文件／网络沙箱或完整HTML清洗。没有工程目标，requires为空；实际业务、模拟和交付另验。
