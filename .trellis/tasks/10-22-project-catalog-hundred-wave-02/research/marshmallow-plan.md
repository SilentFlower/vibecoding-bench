# Marshmallow场景任务表

固定提交b762ea2d59ca52fe5df76b90de14bed7e5ec5607、MIT、完整103个Git文件。已读Schema构造、load／dump／_deserialize／_do_load／validate、Field反序列化、Integer及Date／公共时间路径、ValidationError定义和相关原测试。当前目标镜像完整1192项通过，无skip；使用候选src源码及冻结Simplejson测试依赖，不安装另一份Marshmallow。

| 任务 | 业务事实与价值 | 授权及验收 |
| --- | --- | --- |
| MM-U01 理解 | 外部键、内部属性和输入／输出投影 | 合成凭证值；只读；精确映射与dump_only输入拒绝 |
| MM-U02 理解 | dump成功不表示load校验通过 | 同一负数订单；只读；序列化与输入拒绝对照 |
| MM-C01 咨询 | 未知字段必须选择政策 | RAISE／EXCLUDE／INCLUDE实测；只读；不把透传当校验 |
| MM-C02 咨询 | partial只放过缺失，不放过已有非法值 | 完整五个控制；只读；PATCH完整状态由应用负责 |
| MM-P01 方案 | 失败批次valid_data只是部分诊断 | 精确行索引／原始值；只读；完整验收后发布 |
| MM-D01 诊断 | 日期结果含时间要先核实际Python类型 | 按请求披露／无材料收口；不提前授权修改 |
| MM-M01 修改 | Date明确拒绝datetime而非截断 | 仅fields.py与公开测试；日期身份／子类／字符串／空值／其他字段保持，原版／参考／反例及全回归另验 |

五场景七任务、六项非修改，没有虚假answer或code依赖。日期拒绝是本场景明确合同，不声称原API早已拒绝时间。当前草稿及原生基线不代表产品链和交付准入；正式状态以后续admission为准。
