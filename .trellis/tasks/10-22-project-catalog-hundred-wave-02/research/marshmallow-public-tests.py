"""日期字段严格区分日历日期与时间戳的公开回归。"""
import datetime as dt
import unittest

from marshmallow import Schema, ValidationError, fields


class DateContract(unittest.TestCase):
    """拒绝隐式丢弃时间，保留合法日期行为。"""

    def test_naive_and_aware_datetime_are_rejected(self):
        """时区和无时区时间都不能静默变成日期。@return None。"""
        for value in [dt.datetime(2026, 4, 3, 23, 59), dt.datetime(2026, 4, 3, tzinfo=dt.timezone.utc)]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                fields.Date().deserialize(value)

    def test_date_identity_and_parsing(self):
        """真正日期不复制，ISO及自定格式仍有效。@return None。"""
        value = dt.date(2026, 4, 3)
        self.assertIs(fields.Date().deserialize(value), value)
        self.assertEqual(fields.Date().deserialize('2026-04-03'), value)
        self.assertEqual(fields.Date(format='%d/%m/%Y').deserialize('03/04/2026'), value)

    def test_schema_error_uses_external_key(self):
        """字段错误仍归属外部日期键。@return None。"""
        class Shipment(Schema):
            """合成发货输入。"""
            day = fields.Date(data_key='shipDate')
        with self.assertRaises(ValidationError) as observed:
            Shipment().load({'shipDate': dt.datetime(2026, 4, 3)})
        self.assertEqual(set(observed.exception.messages), {'shipDate'})

    def test_none_invalid_text_and_datetime_field(self):
        """其他字段和缺省空值政策保持。@return None。"""
        self.assertIsNone(fields.Date(allow_none=True).deserialize(None))
        with self.assertRaises(ValidationError):
            fields.Date().deserialize('2026-04-03T00:00:00')
        value = dt.datetime(2026, 4, 3)
        self.assertIs(fields.DateTime().deserialize(value), value)
