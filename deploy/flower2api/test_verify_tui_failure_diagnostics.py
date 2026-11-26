"""验证公开夹具失败时固定诊断查询边界。"""

from datetime import datetime, timezone
from io import StringIO
import json
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import verify_tui_cold_history as fixture


class FailureDiagnosticTests(TestCase):
    """核对精确关联与无响应头的会话候选。"""

    def test_failure_window_excludes_later_request_in_same_session(self):
        """模拟查询前的真实后发顺序，保留失败所在毫秒的候选。@return 无。"""
        start = datetime(2026, 11, 26, 19, 29, 13, 609123, tzinfo=timezone.utc)
        failure = start.replace(microsecond=630456)
        session = "合成会话"
        dates = {
            "original": (session, 611000), "same_millisecond": (session, 630000),
            "other_session": ("另一会话", 620000), "before": (session, 608000),
            "at_exclusive_end": (session, 631000), "later_success": (session, 692000),
        }
        rows = {key: {"request_id": key, "original_session_id": owner,
                      "started_at": start.replace(microsecond=ticks).isoformat(timespec="milliseconds"),
                      "status_code": 200 if key == "later_success" else None}
                for key, (owner, ticks) in dates.items()}
        details = []

        def manage(method, path):
            self.assertEqual(method, "GET")
            if path.startswith("request-diagnostics?"):
                query = parse_qs(urlsplit(path).query)
                self.assertEqual(query, {"since": ["2026-11-26T19:29:13.609+00:00"],
                                         "until": ["2026-11-26T19:29:13.631+00:00"], "page_size": ["100"]})
                return {"items": [row for row in rows.values() if query["since"][0] <= row["started_at"] < query["until"][0]]}
            key = path.rsplit("/", 1)[-1]
            details.append(key)
            return {"request": rows[key], "attempts": []}

        clock = Mock()
        clock.now.side_effect = (start, failure)
        with (
            patch.object(fixture, "datetime", clock),
            patch.object(fixture, "call", side_effect=TimeoutError),
            patch.object(fixture, "stderr", StringIO()) as trace,
            self.assertRaises(TimeoutError),
        ):
            fixture.checked_messages(manage, "合成令牌", {}, {"x-session-id": session}, [], "initial")

        raw, diagnostic = map(json.loads, trace.getvalue().splitlines())
        self.assertIsNone(raw["http_status"])
        self.assertIsNone(raw["request_id"])
        self.assertEqual(raw["failed_at"], "2026-11-26T19:29:13.630+00:00")
        self.assertEqual(diagnostic["correlation"], "session_candidates")
        self.assertEqual(diagnostic["until"], "2026-11-26T19:29:13.631+00:00")
        self.assertIsNone(diagnostic["request_id"])
        self.assertEqual([item["request_id"] for item in diagnostic["requests"]], ["original", "same_millisecond"])
        self.assertEqual(details, ["original", "same_millisecond"])

    def test_no_candidate_preserves_empty_attribution(self):
        """候选窗口为空时保留原请求 ID 的未知状态。@return 无。"""
        start = datetime(2026, 11, 26, 19, 29, 13, 609000, tzinfo=timezone.utc)
        manage = Mock(return_value={"items": []})
        with patch.object(fixture, "wait_for", lambda observe: observe()), patch.object(fixture, "stderr", StringIO()):
            diagnostic = fixture.report_request_diagnostics(
                manage, "initial", None, "合成会话", start.isoformat(timespec="milliseconds"), failed_at=start,
            )
        self.assertIsNone(diagnostic["request_id"])
        self.assertEqual(diagnostic["correlation"], "session_candidates")
        self.assertEqual(diagnostic["requests"], [])
        query = parse_qs(urlsplit(manage.call_args.args[1]).query)
        self.assertEqual(query["until"], ["2026-11-26T19:29:13.610+00:00"])
