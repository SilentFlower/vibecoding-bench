# WTForms商品表单任务表

固定af18fd6a7595d374aa707ff97b73df0dcc462ec2，BSD-3-Clause，完整153个Git文件；34份历史实际编译MO另附逐PO、构建和SHA来源。当前镜像完整537项原生通过，仅保留WebOb导入cgi的精确历史弃用警告过滤，其余warnings=error保持。

已读Form/BaseForm/Field、DefaultMeta、Integer/Boolean/String字段和DataRequired/InputRequired/Optional/NumberRange真实实现。所有输入为自有getlist多值协议合成对象。

| 任务 | 独立用户问题 | 只读授权与验收 |
| --- | --- | --- |
| WF-U01 理解 | 库存0为何被必填拒绝 | DataRequired检查转换后真假，InputRequired检查实际原始提交，预填3不等于提交 |
| WF-U02 理解 | 未勾选为何覆盖原对象true | 无formdata初始显示与空提交不同；BooleanField缺少值变false |
| WF-C01 咨询 | 普通字典不能当多值输入 | 精确TypeError与getlist对照；JSON适配和data预填须分清 |
| WF-C02 咨询 | 预填负数为何绕过Optional后规则 | raw_data=None与提交-1对照；尊重当前输入源规则，不冒称覆盖全部对象验证 |
| WF-P01 方案 | 对象写入能否整体回退 | 通过表单验证后第二setter仍失败，第一属性已写；规划应用暂存/发布和错误策略，不宣称populate_obj事务 |
| WF-D01 诊断 | 共享额外规则导致跨次重复 | 追问完整列表复用与钩子，披露后定位浅拷贝内层列表append；只读建议每次独立列表，不混成授权修复；资料不足正常收口 |

四场景六项，问答均无代码依赖。业务五条独立期望、产品模拟、页面/API/SQLite和完整交付分别验收。
