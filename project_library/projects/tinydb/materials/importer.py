from tinydb import TinyDB


def import_orders(path, orders):
    """表示待审查的既有导入流程。@param path 数据库路径。@param orders 有限订单。@return None。"""
    with TinyDB(path) as db:
        table = db.table('orders')
        for order in orders:
            table.insert(order)
