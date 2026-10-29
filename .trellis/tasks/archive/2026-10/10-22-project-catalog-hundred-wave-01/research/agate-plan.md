# Agate独立业务任务计划

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](agate-admission.json)为准。

固定`202796ada63357c275a2a5f8685a983e37bad9bf`完整250文件及COPYING。已读Table构造、from_csv、TypeTester、Text／Number、where／order_by／compute／join、Table／TableSet.aggregate、Sum／Count和Formula定义。当前镜像原生396项全部通过；只验证实际Linux依赖，没有宣称PyICU或多平台矩阵。

四场景九项只读任务：标识／空值推断与有限样本、派生表及两阶段计算、维表重复匹配取证和准入方案、区域金额及完整率。AG-D01缺完整左右表和join参数时只取证，不预写隐藏根因；披露后才解释重复匹配放大。正常／反例包括前导零／NA保真、采样后的非数值、同时计算依赖不存在、重复维表键和未匹配主表键、空金额与真实零值。

所有方案使用已有API，不把不可变表、require_match或推断采样误称流式、唯一约束或事务。requires全部为空，工程目标0。业务脚本、产品链、页面和交付结果另行产生。
