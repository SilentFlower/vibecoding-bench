# 演示主题RGB颜色严格校验六位ASCII输入而不静默误色

路线01：RGBColor.from_string仅收六位ASCII十六进制，大小写合法、输出六位大写；长度/空白/前缀/Unicode类数字/类型错误明确ValueError，数值构造不动。
