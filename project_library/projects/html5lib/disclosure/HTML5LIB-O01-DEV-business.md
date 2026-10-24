# 业务确认

对应路线01：DOCTYPE逐字段检查publicId/systemId而非重复name，name可None时合法文本仍通过；非法值拒绝且真实walker/对象身份/其他lint保持。

方案确认后实施真实源码改动，公开样例不是全部验收边界。禁止修改原始测试、环境或独立验收器。
