from boltons.iterutils import unique, redundant

values = ["A", "a", "a", "B", "b"]
print(unique(values, key=str.lower))
print(redundant(values, key=str.lower))
print(redundant(values, key=str.lower, groups=True))

class CaseKey:
    """自身真值为False的合法业务归一化函数。"""
    def __call__(self, value):
        """返回业务键。@param value 原值。@return 小写值。"""
        return value.lower()

    def __bool__(self):
        """模拟falsey对象。@return False。"""
        return False

print(redundant(values, key=CaseKey()))
