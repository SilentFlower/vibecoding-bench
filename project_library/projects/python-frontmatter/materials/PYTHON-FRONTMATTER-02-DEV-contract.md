# 带前导空白的文档保持真实格式及业务元数据

路线02：导入器收到前导空行或空白时，格式识别与既有parse一致；check、load和loads保持TOML/YAML真实处理器，保留正文及已交付的content/handler业务元数据。显式handler不替换，不搜索正文中间的分隔符。
