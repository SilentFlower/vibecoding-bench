"""商品字典导入的公开回归，独立于私有验收实现。"""
import unittest

from tablib import Dataset
from tablib.exceptions import UnsupportedFormat


class MappingImportTests(unittest.TestCase):
    """覆盖字段顺序、共享格式入口和拒绝后的原数据保留。"""

    def test_reordered_mapping(self):
        """后续字段顺序变化时按第一行表头读取。@return None。"""
        data = Dataset()
        rows = [{'sku': 'A', 'qty': 2}, {'qty': 5, 'sku': 'B'}]
        data.dict = rows
        self.assertEqual(data.dict, [{'sku': 'A', 'qty': 2}, {'sku': 'B', 'qty': 5}])
        self.assertEqual(list(rows[1]), ['qty', 'sku'])

    def test_json(self):
        """JSON对象经同一修复入口对齐。@return None。"""
        data = Dataset().load('[{"sku":"A","qty":2},{"qty":5,"sku":"B"}]', format='json')
        self.assertEqual(data['sku'], ['A', 'B'])

    def test_yaml(self):
        """YAML对象经同一修复入口对齐。@return None。"""
        data = Dataset().load('- sku: A\n  qty: 2\n- qty: 5\n  sku: B\n', format='yaml')
        self.assertEqual(data['qty'], [2, 5])

    def test_missing_key_preserves_existing(self):
        """拒绝缺字段前不替换旧数据。@return None。"""
        data = Dataset(('old', 9), headers=['sku', 'qty'])
        with self.assertRaises(UnsupportedFormat):
            data.dict = [{'sku': 'A', 'qty': 2}, {'sku': 'B'}]
        self.assertEqual(data[0], ('old', 9))

    def test_extra_key_preserves_existing(self):
        """拒绝多字段前不替换旧数据。@return None。"""
        data = Dataset(('old', 9), headers=['sku', 'qty'])
        with self.assertRaises(UnsupportedFormat):
            data.dict = [{'sku': 'A', 'qty': 2}, {'sku': 'B', 'qty': 3, 'extra': 4}]
        self.assertEqual(data[0], ('old', 9))

    def test_mixed_records_preserve_existing(self):
        """映射批次中的非映射记录得到明确拒绝。@return None。"""
        data = Dataset(('old', 9), headers=['sku', 'qty'])
        with self.assertRaises(UnsupportedFormat):
            data.dict = [{'sku': 'A', 'qty': 2}, ['B', 3]]
        self.assertEqual(data[0], ('old', 9))

    def test_falsey_unicode_values(self):
        """保留空字符串、零、空值及Unicode键值。@return None。"""
        data = Dataset()
        data.dict = [{'商品': '米', '数量': 0}, {'数量': None, '商品': ''}]
        self.assertEqual(list(data), [('米', 0), ('', None)])

    def test_compatibility(self):
        """空列表沿用旧无操作，位置行仍按位置导入。@return None。"""
        data = Dataset(('old', 9), headers=['sku', 'qty'])
        data.dict = []
        self.assertEqual(data[0], ('old', 9))
        data.dict = [['A', 2], ['B', 5]]
        self.assertIsNone(data.headers)
        self.assertEqual(list(data), [('A', 2), ('B', 5)])
