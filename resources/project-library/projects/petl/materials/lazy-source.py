import petl as etl

rows = [("sku", "qty"), ("001", "2"), ("002", "3")]
reads = []
class Source:
    """提供合成可重读订单表。"""
    def __iter__(self):
        """记录读取次数。@return 当前订单表的行迭代器。"""
        reads.append("read")
        return iter(rows)
view = etl.convert(Source(), "qty", int)
one_shot_view = etl.convert(iter(rows), "qty", int)
