# Feedgen订阅构建任务表

固定97260abb1793eb164c458c10b493690beb413f6d，55个Git跟踪文件完整保留。选择README/setup.py公开允许的BSD-2-Clause分支，原license.bsd及license.lgpl均保留。已读FeedEntry/FeedGenerator字段、构树、链接、日期、内容、条目列表和ensure_format定义，当前镜像56项完整原生通过。

| 任务 | 用户问题和当前事实 | 授权及独立验收 |
| --- | --- | --- |
| FG-U01 理解 | 清单顺序为何倒置 | 完整三ID对照；只读；默认prepend与显式append不同 |
| FG-U02 理解 | RSS为何只显示一个链接/附件 | 两alternate、两enclosure；只读；RSS取末项，Atom保留多个href，不依赖尚未修复的属性 |
| FG-C01 咨询 | 无偏移日期能否默认本地时区 | 完整naive/aware两输入和文本；只读；拒绝缺时区，不猜源时间意义 |
| FG-C02 咨询 | 来源信息的部分更新为何被忽略 | 只读；核source getter/setter实际参数与支持的元数据范围，依公开source-update材料给出兼容调用，不改代码或推断未提供的新字段 |
| FG-P01 方案 | 同资料如何确定性导出 | 显式feed/entry日期、顺序、选项；只读方案；两次实际RSS/Atom一致，不宣称提供新clock API |
| FG-D01 诊断 | 非文本内嵌内容为什么失败 | 追问完整content和异常，披露后识别实际未支持范围及现有src引用；只读；资料不足正常收口 |
| FG-M01 修改 | 条目Atom链接丢失已支持的元数据 | 仅library/feedgen/entry.py及app/test_atom_link.py；一次修复字典被XML元素覆盖的根因，五属性、多链接、Unicode、字符串0、空值及RSS兼容同验；不拆成多个任务 |

五场景七任务，六项非修改；无answer/code依赖。修改原版失败、完整参考、只修rel反例、三项公开回归原版失败/参考通过及完整56项累计原生分别记录。所有URL只序列化，不发网络请求。模拟和完整交付另验，不以原生成功提前准入。
