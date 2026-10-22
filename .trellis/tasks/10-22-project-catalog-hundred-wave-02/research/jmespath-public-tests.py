"""公开验证递归JSON比较，布尔字面与数字保持独立。"""
from copy import deepcopy
import unittest

from jmespath import search


class JsonEqualityTests(unittest.TestCase):
    """通过真实查询验证业务结果，不依赖具体实现写法。"""

    def compare(self, left, right, expected: bool) -> None:
        """核双向相等／不等及输入归属。@param left 左值。@param right 右值。@param expected 期望。@return None。"""
        value = {'a': left, 'b': right}
        before = deepcopy(value)
        self.assertIs(search('a == b', value), expected)
        self.assertIs(search('a != b', value), not expected)
        self.assertIs(search('b == a', value), expected)
        self.assertEqual(value, before)

    def test_nested_arrays_keep_boolean_types(self) -> None:
        """各层数组都必须遵循JSON成员类型。@return None。"""
        self.compare([True], [1], False)
        self.compare([[False]], [[0]], False)
        self.compare([True, False], [True, False], True)
        self.compare([1, [2.0]], [1.0, [2]], True)

    def test_objects_compare_nested_values_and_key_sets(self) -> None:
        """对象成员递归比较，键顺序不改变相等。@return None。"""
        self.compare({'x': [True]}, {'x': [1]}, False)
        self.compare({'x': {'active': False}}, {'x': {'active': 0}}, False)
        self.compare({'a': 1, 'b': [True]}, {'b': [True], 'a': 1.0}, True)
        self.compare({'x': None}, {}, False)

    def test_filter_uses_recursive_equality_and_inequality(self) -> None:
        """导出筛选必须使用同样的递归规则。@return None。"""
        rows = {'items': [{'id': 'same', 'a': {'x': [True]}, 'b': {'x': [True]}},
            {'id': 'wrong-type', 'a': {'x': [True]}, 'b': {'x': [1]}},
            {'id': 'numeric', 'a': {'x': [1]}, 'b': {'x': [1.0]}}]}
        self.assertEqual(search('items[?a==b].id', rows), ['same', 'numeric'])
        self.assertEqual(search('items[?a!=b].id', rows), ['wrong-type'])

    def test_scalar_null_order_and_length_compatibility(self) -> None:
        """递归修复不改变既有标量、空值和数组形状边界。@return None。"""
        for left, right, expected in [(True, 1, False), (False, 0, False), (1, 1.0, True),
                (None, None, True), (None, 0, False), ([1, 2], [2, 1], False), ([1], [1, 2], False)]:
            self.compare(left, right, expected)
