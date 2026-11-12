"""验证当地运行窗口在跨日、周切换及真实夏令时下的行为。"""
import unittest
from datetime import datetime

from run_windows import normalize_run_window, run_window_snapshot


class RunWindowTests(unittest.TestCase):
    """使用确定 UTC 时刻验证业务边界，不修改系统时钟。"""

    def _snapshot(self, utc: str, zone="America/Los_Angeles", days=None, intervals=None) -> dict:
        """构造已启用配置并返回指定 UTC 时刻的公开摘要。"""
        configuration = normalize_run_window({"schema": 1, "enabled": True,
            "days": [0, 1, 2, 3, 4] if days is None else days,
            "intervals": [{"start": "09:00", "end": "18:00"}] if intervals is None else intervals})
        return run_window_snapshot(configuration, zone, datetime.fromisoformat(utc).timestamp())

    def test_start_inclusive_end_exclusive_and_weekday(self) -> None:
        """同一当地星期开始可启动、结束休息，周末等待下一周。@return None。"""
        self.assertTrue(self._snapshot("2026-10-19T16:00:00+00:00")["allowed"])
        end = self._snapshot("2026-10-20T01:00:00+00:00")
        self.assertFalse(end["allowed"])
        self.assertEqual(datetime.fromisoformat("2026-10-20T16:00:00+00:00").timestamp(), end["next_open_at"])
        self.assertFalse(self._snapshot("2026-10-24T16:00:00+00:00")["allowed"])

    def test_overnight_belongs_to_start_day(self) -> None:
        """周一跨夜区间覆盖周二凌晨，但不覆盖周三凌晨。@return None。"""
        intervals = [{"start": "22:00", "end": "02:00"}]
        self.assertTrue(self._snapshot("2026-10-19T23:00:00+00:00", zone="UTC", days=[0], intervals=intervals)["allowed"])
        self.assertTrue(self._snapshot("2026-10-20T01:59:59+00:00", zone="UTC", days=[0], intervals=intervals)["allowed"])
        self.assertFalse(self._snapshot("2026-10-20T02:00:00+00:00", zone="UTC", days=[0], intervals=intervals)["allowed"])
        self.assertFalse(self._snapshot("2026-10-21T01:00:00+00:00", zone="UTC", days=[0], intervals=intervals)["allowed"])

    def test_sunday_overnight_wraps_week(self) -> None:
        """周日尾段可跨到下周一，不受周序号切换影响。@return None。"""
        self.assertTrue(self._snapshot("2026-10-19T00:30:00+00:00", zone="UTC", days=[6],
            intervals=[{"start": "23:00", "end": "01:00"}])["allowed"])

    def test_multiple_overlapping_intervals_form_one_open_span(self) -> None:
        """相邻和重叠区间取并集，不在中间错误休息。@return None。"""
        result = self._snapshot("2026-10-19T12:00:00+00:00", zone="UTC", intervals=[
            {"start": "09:00", "end": "12:00"}, {"start": "12:00", "end": "14:00"},
            {"start": "13:00", "end": "18:00"}])
        self.assertTrue(result["allowed"])
        self.assertEqual(datetime.fromisoformat("2026-10-19T18:00:00+00:00").timestamp(), result["next_close_at"])

    def test_spring_jump_opens_at_first_existing_allowed_minute(self) -> None:
        """02:30 不存在时，03:00 是 02:30～03:30 的首个可用时刻。@return None。"""
        intervals = [{"start": "02:30", "end": "03:30"}]
        result = self._snapshot("2026-03-08T09:59:30+00:00", days=[6], intervals=intervals)
        self.assertFalse(result["allowed"])
        self.assertEqual(datetime.fromisoformat("2026-03-08T10:00:00+00:00").timestamp(), result["next_open_at"])
        self.assertTrue(self._snapshot("2026-03-08T10:00:00+00:00", days=[6], intervals=intervals)["allowed"])

    def test_skipped_weekly_interval_waits_until_next_week(self) -> None:
        """整个周日区间被跳过时，应等待下一周真实存在的区间。@return None。"""
        result = self._snapshot("2026-03-08T09:59:30+00:00", days=[6], intervals=[{"start": "02:10", "end": "02:20"}])
        self.assertEqual(datetime.fromisoformat("2026-03-15T09:10:00+00:00").timestamp(), result["next_open_at"])

    def test_fall_repeated_hour_can_open_twice(self) -> None:
        """重复小时按真实 UTC 两次判断，不混用第一次与第二次的边界。@return None。"""
        intervals = [{"start": "01:30", "end": "01:45"}]
        for utc in ("2026-11-01T08:30:00+00:00", "2026-11-01T09:30:00+00:00"):
            self.assertTrue(self._snapshot(utc, days=[6], intervals=intervals)["allowed"])
        result = self._snapshot("2026-11-01T08:45:00+00:00", days=[6], intervals=intervals)
        self.assertFalse(result["allowed"])
        self.assertEqual(datetime.fromisoformat("2026-11-01T09:30:00+00:00").timestamp(), result["next_open_at"])

    def test_same_utc_instant_uses_each_accounts_timezone(self) -> None:
        """同一 UTC 时刻在纽约可运行、洛杉矶尚未开始。@return None。"""
        self.assertTrue(self._snapshot("2026-10-19T14:00:00+00:00", zone="America/New_York")["allowed"])
        self.assertFalse(self._snapshot("2026-10-19T14:00:00+00:00")["allowed"])

    def test_unconfigured_account_is_unrestricted(self) -> None:
        """NULL 配置不暗中启用默认作息。@return None。"""
        result = run_window_snapshot(normalize_run_window(None), "UTC", 1792454400)
        self.assertTrue(result["allowed"])
        self.assertFalse(result["enabled"])
        self.assertIsNone(result["next_close_at"])

    def test_strict_configuration_rejects_ambiguous_values(self) -> None:
        """拒绝 bool 星期、相同端点及无有效窗口，关闭仍保留合法配置。@return None。"""
        base = {"schema": 1, "enabled": True, "days": [0], "intervals": [{"start": "09:00", "end": "18:00"}]}
        for changes in ({"days": [True]}, {"enabled": 1}, {"days": []}, {"intervals": []},
                {"intervals": [{"start": "9:00", "end": "18:00"}]},
                {"intervals": [{"start": "09:00", "end": "09:00"}]}, {"timezone": "UTC"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize_run_window({**base, **changes})
        self.assertEqual(base["intervals"], normalize_run_window({**base, "enabled": False})["intervals"])


if __name__ == "__main__":
    unittest.main()
