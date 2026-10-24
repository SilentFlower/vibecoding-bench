# Token匹配显式选择原文大小写策略且保持默认兼容

路线13：Token.match增加显式大小写政策，None完全保留默认；True按原文精确、False普通字符串casefold，regex按Python flags而不改写表达式。保持生成器、类型匹配及原token值；这是可选增强，非误报默认Keyword缺陷。
