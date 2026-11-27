"""验证公开夹具失败时固定诊断查询边界。"""

from datetime import datetime, timezone
from io import StringIO
import json
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import verify_tui_cold_history as fixture
import verify_tui_final_tls as transport


class FailureDiagnosticTests(TestCase):
    """核对精确关联与无响应头的会话候选。"""

    def test_original_503_and_resend_header_timeout_keep_independent_attribution(self):
        """原 503 精确查询后，补发无头时只查询补发窗口。@return 无。"""
        start = datetime(2026, 11, 26, 19, 29, 13, 100000, tzinfo=timezone.utc)
        original = {"request_id": "original", "finished_at": "已结束", "status_code": 503,
                    "context": {"tui_reservation_id": "original-reservation"}}
        resend = {"request_id": "resend-candidate", "original_session_id": "会话",
                  "context": {"tui_reservation_id": "resend-reservation"}}
        first_connection, second_connection = Mock(), Mock()
        response = first_connection.getresponse.return_value
        response.status = 503
        response.getheader.side_effect = lambda name: "original" if name == "x-cc2api-request-id" else None
        response.read.return_value = b'{"error":"synthetic"}'
        second_connection.getresponse.side_effect = TimeoutError
        clock = Mock()
        clock.now.side_effect = [start.replace(microsecond=tick) for tick in (100000, 200000, 300000, 400000)]
        manage = Mock(side_effect=[{"items": [original]}, {"request": original, "attempts": []},
                                   {"items": [resend]}, {"request": resend, "attempts": []}])
        with (
            patch.object(fixture, "datetime", clock),
            patch.object(transport, "HTTPConnection", side_effect=[first_connection, second_connection]),
            patch.object(fixture, "stderr", StringIO()) as trace,
            self.assertRaises(AssertionError) as failed,
        ):
            fixture.checked_messages(manage, "合成令牌", {}, {"x-session-id": "会话"}, [], "recovered_receipt",
                                     trace_recovery_resend=True)

        self.assertEqual(failed.exception.args[0], ("recovered_receipt", 503, 200, "original"))
        self.assertEqual(first_connection.request.call_args, second_connection.request.call_args)
        raw_original, diagnostic_original, raw_resend, diagnostic_resend = map(json.loads, trace.getvalue().splitlines())
        self.assertEqual(raw_original["client_stage"], "response_complete")
        self.assertIsNotNone(raw_original["response_headers_ms"])
        self.assertEqual(raw_resend["resend_of"], raw_original["observation_id"])
        self.assertNotEqual(raw_resend["observation_id"], raw_original["observation_id"])
        self.assertEqual(raw_resend["request_body_sha256"], raw_original["request_body_sha256"])
        self.assertEqual(raw_resend["client_stage"], "waiting_response_headers")
        self.assertIsNone(raw_resend["http_status"])
        self.assertIsNone(raw_resend["request_id"])
        self.assertIsNone(raw_resend["response_headers_ms"])
        for raw, diagnostic, reservation in ((raw_original, diagnostic_original, "original-reservation"),
                                             (raw_resend, diagnostic_resend, "resend-reservation")):
            self.assertEqual(diagnostic["observation_id"], raw["observation_id"])
            self.assertEqual(diagnostic["requests"][0]["diagnostic_context"]["tui_reservation_id"], reservation)
        self.assertEqual(diagnostic_original["correlation"], "response_request_id")
        self.assertEqual(diagnostic_resend["correlation"], "session_candidates")
        self.assertEqual(diagnostic_resend["since"], "2026-11-26T19:29:13.300+00:00")
        self.assertEqual(diagnostic_resend["until"], "2026-11-26T19:29:13.401+00:00")

    def test_changed_signature_409_preserves_public_and_prepare_evidence(self):
        """改签名意外返回 409 时记录原请求并保持 422 断言。@return 无。"""
        record = {"request_id": "signed-rejection", "finished_at": "已结束", "status_code": 409,
                  "error_stage": "request", "attempt_count": 0,
                  "context": {"tui_reservation_id": "signed-reservation"}}
        response = Mock(status=409)
        response.getheader.side_effect = lambda name: record["request_id"] if name == "x-cc2api-request-id" else None
        response.read.return_value = b'{"error":{"type":"invalid_request_error","code":"tool_recovery_unconfirmed"}}'
        connection = Mock()
        connection.getresponse.return_value = response
        manage = Mock(side_effect=[{"items": [record]}, {"request": record, "attempts": []}])
        with (
            patch.object(transport, "HTTPConnection", return_value=connection) as request,
            patch.object(fixture, "stderr", StringIO()) as trace,
            self.assertRaises(AssertionError) as failed,
        ):
            fixture.checked_messages(manage, "合成令牌", {}, {"x-session-id": "会话"}, [("首轮", {}, None)],
                                     "changed_signature", expected_status=422)
        self.assertEqual(failed.exception.args[0], ("changed_signature", 409, 422, "signed-rejection"))
        request.assert_called_once()
        client, diagnostic = map(json.loads, trace.getvalue().splitlines())
        self.assertEqual(client["response_error"]["code"], "tool_recovery_unconfirmed")
        self.assertEqual(client["client_stage"], "response_complete")
        self.assertEqual((client["model_posts_before"], client["model_posts_during"]), (1, 0))
        self.assertEqual(diagnostic["observation_id"], client["observation_id"])
        self.assertEqual((diagnostic["correlation"], diagnostic["request_id"]), ("response_request_id", "signed-rejection"))
        observed, = diagnostic["requests"]
        self.assertEqual(observed["diagnostic_context"]["tui_reservation_id"], "signed-reservation")
        self.assertEqual((observed["error_stage"], observed["attempt_count"]), ("request", 0))
        self.assertEqual(observed["attempts"], [])

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
