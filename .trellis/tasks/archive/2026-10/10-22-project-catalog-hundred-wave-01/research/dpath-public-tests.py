"""公开回归：过滤删除必须同时满足路径与值条件。"""
from copy import deepcopy
import unittest

from dpath import delete
from dpath.exceptions import PathNotFound


class DeleteFilterTests(unittest.TestCase):
    """验证业务路径边界，保留无过滤及无匹配合同。"""

    def test_equal_outside_value_is_retained(self) -> None:
        """范围外同值不能被删除。@return None。"""
        value = {'selected': {'drop': 1, 'keep': 0}, 'outside': {'same': 1}}
        self.assertEqual(delete(value, 'selected/*', afilter=lambda item: item == 1), 1)
        self.assertEqual(value, {'selected': {'keep': 0}, 'outside': {'same': 1}})

    def test_nonmatching_selected_value_is_not_deleted(self) -> None:
        """路径命中但值不通过时保持原件且报无匹配。@return None。"""
        value = {'selected': {'keep': 0}, 'outside': {'same': 1}}
        before = deepcopy(value)
        with self.assertRaises(PathNotFound):
            delete(value, 'selected/*', afilter=lambda item: item == 1)
        self.assertEqual(value, before)

    def test_custom_separator_keeps_same_path_boundary(self) -> None:
        """自定义分隔符也必须取路径和值的交集。@return None。"""
        value = {'selected': {'drop': 1}, 'outside': {'same': 1}}
        self.assertEqual(delete(value, 'selected.*', separator='.', afilter=lambda item: item == 1), 1)
        self.assertEqual(value, {'selected': {}, 'outside': {'same': 1}})

    def test_no_filter_keeps_original_glob_behavior(self) -> None:
        """未传过滤器时保留全部路径命中删除。@return None。"""
        value = {'selected': {'drop': 1, 'keep': 0}, 'outside': {'same': 1}}
        self.assertEqual(delete(value, 'selected/*'), 2)
        self.assertEqual(value, {'selected': {}, 'outside': {'same': 1}})
