# XlsxWriter场景任务表

固定提交5d4606d89a955226d2d0825a0f44309043ae7251、BSD-2-Clause、完整3003个Git文件。已读Workbook构造／add_worksheet／close、Worksheet通用分派、write_string／write_formula／数组转发、add_table、维度检查与最终cell XML写入。全部源和真实Excel参照包保留，当前目标镜像完整1787项通过、无skip；不运行Excel／LibreOffice或远程链接。

| 任务 | 独立业务价值 | 授权与验收 |
| --- | --- | --- |
| XW-U01 理解 | 公式、缓存值与重算责任 | 实际ZIP内f／v对照；只读，不虚报计算 |
| XW-C01 咨询 | 标识字符串与表达式外观文本 | 00123转换政策、write_string与实际XML；无需改库 |
| XW-U02 理解 | 常量内存要求正向行序 | 返回码与最终单元格对账；只读 |
| XW-C02 咨询 | 表格和内存模式选择 | add_table实际-3／warning／无部件，in_memory覆盖；只读 |
| XW-P01 方案 | 完整关闭验收后发布 | 关闭前后真实ZIP有效性；不把close说成文件事务 |
| XW-M01 修改 | 禁用公式转换覆盖数组外观文本 | 仅worksheet.py与公开测试；默认／显式API保留，原版／参考／反例及完整回归另验 |

四场景六任务，五项非修改。全部输入已完整给出，不制造追问或假依赖；验收观察最终包副作用。原生和业务成功仍须产品链、页面与交付证据，正式状态以后续admission为准。
