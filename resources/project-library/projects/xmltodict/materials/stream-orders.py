from xmltodict import parse

received = []

def accept(path, item):
    """保存已处理订单。@param path 当前路径。@param item 订单。@return 是否继续。"""
    received.append((tuple(name for name, attributes in path), item))
    return True

chunks = ["<orders>", "<order id='A'><qty>2</qty></order>", "<order id='B'><qty>3</qty></order>", "</orders>"]
returned = parse((chunk for chunk in chunks), item_depth=2, item_callback=accept)
print(returned, received)
