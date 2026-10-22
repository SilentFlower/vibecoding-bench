# Feedparser本地订阅验收任务表

固定a22c5521cbb109871f1a2318948581901bd47e26，BSD-2-Clause，2362个Git文件完整保留。已读parse/_open_resource/strict-loose-JSON路径、FeedParserDict真实存储与历史访问器、JSONParser字段映射、日期与相对HTML资源设置。当前目标完整4305原生通过，精确可选chardet5.2.0不替换为另一个实现版本。

| 任务 | 独立问题及正常/反例 | 授权 |
| --- | --- | --- |
| FP-U01 理解 | bozo有条目与无bozo空输入均存在 | 只读，容错结果、语法异常和业务完整性分开 |
| FP-U02 理解 | UTC日期tuple与published/updated历史访问器 | 只读，9点+02变7点UTC；updated成员不存在但访问fallback并警告 |
| FP-C01 咨询 | 默认HTML处理会改输出 | 只读，脚本移除与禁用处理对照，保留明确下游呈现政策 |
| FP-C02 咨询 | 本地输入的相对HTML资源基准 | 只读，BytesIO+content-location与关闭重写对照，不下载资源 |
| FP-P01 方案 | 跨RSS/JSON结构统一需要适配 | 只读方案，JSON原存content字典/category列表/enclosures字段与旧访问器冲突，明确逐格式规范化及原件 |
| FP-D01 诊断 | JSON修改日期为何缺失 | 追问完整原输入和访问方式，披露后识别date_updated/date_modified条件不一致；只读，不授权修复；缺材料正常不足收口 |

四场景六任务，所有数据用显式BytesIO，避免字符串触发文件/网络访问。首个宿主探针把raw category误当tags的KeyError原件保留；核实际字典及访问器后才冻结任务。独立业务、产品链和交付另验。
