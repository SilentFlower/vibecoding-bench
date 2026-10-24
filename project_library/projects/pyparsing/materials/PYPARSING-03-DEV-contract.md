# 本地化金额按显式地区分组规则解析为精确Decimal

路线09：金额使用明确小数符/分组符/组宽/小数位上限，直接Decimal不经float，不读取宿主locale；严格分组、NBSP、符号、大精度与原有number完全分离。
