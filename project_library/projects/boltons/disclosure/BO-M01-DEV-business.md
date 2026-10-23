# Business scope

Implement the complete public falsey-key contract for redundant, including grouped output and zero-length callables over unhashable records. Preserve original values/order, None/default and errors. Modify only the authorized implementation/test files with meaningful original-failing public tests.

# Investigation topics

- 解释唯一项与首个重复项报告
- 用已有key选择业务重复规则
- 定位falsey归一化函数被忽略

# Supplied business material: materials/redundancy.py

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


# Supplied business material: materials/key-contract.md

Repair redundant so every supported non-None key is used even when a callable has false __bool__ or zero __len__. Preserve the public signature, None identity default, normal callables and attribute-name shorthand, original duplicate values, first-redundancy group order and exception propagation. Support falsey callables that map unhashable business records to hashable keys. Keep both groups=False and groups=True. Do not sort or replace the source values with normalized keys, change other iterator utilities, or alter dependencies/test controls. Only library/boltons/iterutils.py and library/tests/test_iterutils.py may change. Add meaningful original-failing public regressions and preserve all frozen original doctests/main/subtests.

