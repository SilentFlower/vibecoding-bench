"""验证物理特征的来源、缓存归属和真实资源口径。"""
import json
import tempfile
import time
import unittest
from pathlib import Path

from physical_features import FEATURE_LABELS, configured_features, physical_features_summary, validate_features


class PhysicalFeaturesTests(unittest.TestCase):
    """使用隔离快照验证配置不能冒充实测。"""

    def setUp(self) -> None:
        """准备当前代环境及独立观察文件。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "features.json"
        self.now = time.time()
        self.row = {"environment_id": "a" * 32, "generation": 3, "container_id": "cli-current", "isolation_version": 2,
            "fingerprint": {"hostname": "saved-host", "mac": "02:00:00:00:00:01", "tz": "UTC", "lang": "en_US.UTF-8",
                "machine_id": "b" * 32, "mem": "1536m", "swap": "2048m",
                "system_profile": {"kernel_release": "6.1.0-test", "cpu_model_name": "Synthetic CPU"},
                "computer_profile": {"dmi": {"manufacturer": "Synthetic Vendor", "uuid": "synthetic-uuid"}}}}

    def _snapshot(self, **changes) -> dict:
        """写入有界白名单快照，参数覆盖元数据，返回该快照。"""
        values = dict.fromkeys(FEATURE_LABELS)
        values.update(hostname="saved-host", memory_bytes=1152 * 1024 ** 2, machine_id=True)
        snapshot = {"schema": 1, "environment_id": self.row["environment_id"], "generation": 3,
            "container_id": "cli-current", "observed_at": self.now, "values": values, **changes}
        self.path.write_text(json.dumps(snapshot))
        return snapshot

    def test_missing_snapshot_keeps_configured_values_unobserved(self) -> None:
        """存在配置也不能在没有采集时标为已实测。@return None。"""
        summary = physical_features_summary(self.row, self.path, self.now)
        host = next(field for field in summary["fields"] if field["key"] == "hostname")
        self.assertEqual("missing", summary["status"])
        self.assertEqual("saved-host", host["configured"])
        self.assertIsNone(host["observed"])
        self.assertEqual("unobserved", host["status"])
        self.assertFalse(self.path.exists())

    def test_current_observation_compares_actual_cli_ram(self) -> None:
        """CLI RAM 应扣除网络与发送器，不能把总预算或 swap 当作它。@return None。"""
        self._snapshot()
        summary = physical_features_summary(self.row, self.path, self.now)
        fields = {field["key"]: field for field in summary["fields"]}
        self.assertEqual("cached", summary["status"])
        self.assertEqual("match", fields["memory_bytes"]["status"])
        self.assertEqual(1152 * 1024 ** 2, fields["memory_bytes"]["configured"])
        self.assertEqual(1536 * 1024 ** 2, fields["account_memory_bytes"]["configured"])
        self.assertIsNone(fields["account_memory_bytes"]["observed"])

    def test_mismatch_is_reported_without_modifying_configuration(self) -> None:
        """观察到差异只展示差异，不旋转身份或回填假数据。@return None。"""
        saved = self._snapshot()
        saved["values"]["hostname"] = "different-host"
        self.path.write_text(json.dumps(saved))
        before = json.dumps(self.row)
        summary = physical_features_summary(self.row, self.path, self.now)
        host = next(field for field in summary["fields"] if field["key"] == "hostname")
        self.assertEqual("mismatch", host["status"])
        self.assertEqual("different-host", host["observed"])
        self.assertEqual(before, json.dumps(self.row))

    def test_old_generation_never_claims_current_match(self) -> None:
        """重建后保留旧观察与时间，明确它属于旧代。@return None。"""
        self._snapshot(generation=2, container_id="cli-old")
        summary = physical_features_summary(self.row, self.path, self.now)
        self.assertEqual("stale", summary["status"])
        self.assertEqual(2, summary["generation"])
        self.assertEqual(self.now, summary["observed_at"])
        self.assertTrue(all(field["status"] == "stale" for field in summary["fields"]))

    def test_invalid_or_cross_environment_snapshot_is_not_exposed(self) -> None:
        """坏来源与未来时间拒收，响应不带快照原文。@return None。"""
        for changes in ({"environment_id": "other"}, {"observed_at": self.now + 61}, {"generation": True}, {"secret": "private"}):
            with self.subTest(changes=changes):
                self._snapshot(**changes)
                summary = physical_features_summary(self.row, self.path, self.now)
                self.assertEqual("invalid", summary["status"])
                self.assertIsNone(summary["observed_at"])
                self.assertNotIn("private", json.dumps(summary))

    def test_linked_snapshot_is_not_read(self) -> None:
        """私有快照路径的符号链接不能把其它文件带入响应。@return None。"""
        target = self.path.with_name("other.json")
        target.write_text('{"private":"secret"}')
        self.path.symlink_to(target)
        self.assertEqual("invalid", physical_features_summary(self.row, self.path, self.now)["status"])

    def test_probe_rejects_unknown_fields_invalid_numbers_and_control_text(self) -> None:
        """探针边界拒收意外字段、bool 资源值和任意多行内容。@return None。"""
        for key, value in (("memory_bytes", True), ("memory_bytes", -1), ("cpu", "value\nextra"), ("cpu", "x" * 513)):
            values = dict.fromkeys(FEATURE_LABELS)
            values[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_features({"schema": 1, "values": values})
        with self.assertRaises(ValueError):
            validate_features({"schema": 1, "values": {**dict.fromkeys(FEATURE_LABELS), "secret": "private"}})

    def test_legacy_ram_does_not_use_isolated_cli_allocation(self) -> None:
        """旧布局的 RAM 仍使用它自身总上限，缺字段不生成配置。@return None。"""
        self.assertEqual(1536 * 1024 ** 2, configured_features({**self.row, "isolation_version": 0})["memory_bytes"])
        del self.row["fingerprint"]["mem"]
        self.assertNotIn("memory_bytes", configured_features(self.row))


if __name__ == "__main__":
    unittest.main()
