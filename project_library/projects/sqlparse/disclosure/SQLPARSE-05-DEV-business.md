# 业务确认

路线13：Token.match增加显式大小写政策，None完全保留默认；True按原文精确、False普通字符串casefold，regex按Python flags而不改写表达式。保持生成器、类型匹配及原token值；这是可选增强，非误报默认Keyword缺陷。

请先调查、澄清并确认方案再实施。公开样例不是全部验收边界；独立失败必须返工。
