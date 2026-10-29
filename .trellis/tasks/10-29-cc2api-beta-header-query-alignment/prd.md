# cc2api：beta 请求头与查询参数对齐

## 目标

修复重复beta头丢值和URL beta冲突，使等价请求保留同一有效beta集合，并由子agent实施。

## 来源与证据

- 用户要求R3-02、R3-04修复并派子agent，且先查看原生抓包参数。
- 592条已读取的不同原生Messages只见一个beta=true；280以七份.flow原件复核。293远端连接超时，原件未读，不外推。
- 当前extract_headers把重复beta覆盖；当前URL在beta=false后追加true。固定本地证据和真实函数签名见research/findings.md及native-query-evidence.json。

## 要求

- R1：只对anthropic-beta按同名值插入顺序合并、精确去重，保留有效token，不改变其它头既有单值策略或非法头值处理。
- R2：合并结果继续受账号1M/Fast能力和版本画像约束，保持现有已知token顺序；API/标题/safeguard/后台窄画像不扩大。
- R3：对现有需要beta query的精确路径，归一所有解码后同名beta为唯一beta=true，覆盖false/空/重复/编码同名项；无beta则追加。
- R4：其它query保留原始片段、编码、顺序与重复值，不基于未观测就建立白名单；不把合成synthetic_client_id当真实CLI需删除字段。其它端点和count_tokens专用URL保持现有合同。
- R5：保留R2清理开关、Session、CCH及stream三态；请求体、账号调度与已有特殊画像不得因本次头／URL规范化改变。

## 验收标准

- AC1（R1/R2）：实际Gateway在280/293 CC相同beta集合交换两行时不丢1M；账号禁止仍过滤，重叠/空白/相似日期/大小写头与API/特殊画像回归通过。
- AC2（R3/R4）：实际上游URL只含一个beta=true，其它参数字节片段与次序保留；缺省/空/false/重复/百分号编码、非目标与count_tokens均有覆盖。
- AC3（R5）：CCH、stream、R2清理和Session组合回归通过；格式与Rust全量测试通过，源码与测试证据可追溯。验证只使用loopback合成上游，不发真实推理请求。

## 不在范围

不新增全局query白名单、UA重复准入策略、OpenAI转换、请求解压或响应保活实现。R3-01／03当前只讨论方案，不混入本次修复。
