# Toolz纯函数数据工作场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](toolz-admission.json)为准。

## 来源与原生边界

固定 `pytoolz/toolz@451af60dec590a6010e2babdbf391ea8f815122f`（实际tag 1.2.0），完整81文件和BSD许可。已读取compose/pipe、curried命名空间、partition/partition_all、memoize完整key调用和闭包缓存、groupby/reduceby以及merge/merge_with真实定义。当前镜像193个完整原生主项为192通过／1上游Python3.14专用跳过，包内测试和夹具冻结，内部原始doctest通过，不把单个doctest父测试的示例另混加成主项。

## 四场景八项独立任务

| 场景 | 任务 | 实际业务与合法结果 |
| --- | --- | --- |
| TZ-S01 组合和分批管道 | TZ-U01 理解 | compose右到左与pipe数据从左到右的真实顺序 |
| TZ-S01 | TZ-C01 咨询 | curried.map依旧惰性，partition缺省丢尾、partition_all保尾，按不丢订单需求选择 |
| TZ-S02 缓存价格计算 | TZ-U02 理解 | memoize默认需可哈希键，key接收(args,kwargs)，显式规范化列表并包含折扣 |
| TZ-S02 | TZ-C02 咨询 | 外部价格变化不会自动清缓存，使用显式cache生命周期或把价格版本纳入纯函数输入 |
| TZ-S03 区域订单统计 | TZ-U03 理解 | groupby按全流收集非连续同键记录，返回完整列表并已耗尽输入 |
| TZ-S03 | TZ-C03 咨询 | 只要总数量时用已有reduceby避免保存各组原记录，内存仍随键和累加器增长 |
| TZ-S04 配置和账单合并 | TZ-U04 理解 | merge后者覆盖且是浅层新字典，嵌套对象仍共享，不当作不可变深拷贝 |
| TZ-S04 | TZ-C04 咨询 | merge覆盖与merge_with(sum)按全部同键值累加的业务区别，保留输入映射 |

全部只读、requires为空，材料自足，无人为披露分支。当前已有key/cache、reduceby和合并接口满足要求，不硬造新增API；缓存仅合成内存字典，不调用外部价格服务。

## 验收

八条实际原生业务观察、完整原生、评审协议和全部产品链任务、页面／API／SQLite及Git／Docker分别留证。无工程目标不制造错误修复参考、公开修复测试或接受代码，不把mock当真实模型质量。
