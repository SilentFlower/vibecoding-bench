# 业务确认

路线09：独立ZonedTimeStamper明确tzinfo/ZoneInfo、ISO精度与注入aware时钟，真实瞬间转换并输出offset；拒绝naive/无效精度，原TimeStamper不动。

请先调查、澄清并确认方案再实施。公开样例不是全部验收边界；独立失败必须返工。
