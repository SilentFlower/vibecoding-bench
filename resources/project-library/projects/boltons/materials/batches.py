from boltons.iterutils import chunked_iter

def records():
    """产生有限记录并显示实际消费。@return 生成器。"""
    for value in range(5):
        print("consume", value)
        yield value

batches = chunked_iter(records(), 2)
print("created")
print(next(batches))
print(list(batches))
print(list(chunked_iter(range(5), 2, fill=None)))
