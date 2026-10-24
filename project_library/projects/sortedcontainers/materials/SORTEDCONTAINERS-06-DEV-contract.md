# 有序映射惰性读取键区间的业务项和值

路线12：SortedDict的irange_items/values惰性输出当前值，边界和顺序完全沿用键irange；空值/无界/反向key明确，结构修改遵循原迭代契约而非虚构快照。
