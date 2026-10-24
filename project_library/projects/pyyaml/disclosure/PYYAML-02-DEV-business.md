# 业务确认

路线02：仅内建bool/int/float/timestamp预期转换错误规范为ConstructorError并保位置/cause；timestamp无匹配先检查，合法值不改，不吞任意内部或用户构造器错误。

请先调查、澄清并确认方案再实施。公开样例不是全部验收边界；独立失败必须返工。
