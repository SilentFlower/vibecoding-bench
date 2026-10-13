"""联合发布必须保存真实配置 ID 与仓库 digest，失败不产生可部署半批清单。"""
import gzip
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import manage


class PublicationTests(unittest.TestCase):
    """用受控 Docker 边界验证发布、下载与离线交付，绝不访问真实仓库。"""

    def setUp(self) -> None:
        """准备两种不同 digest 的同批镜像及隔离 Action 元数据。

        :return: None
        """
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.input = self.root / "local.json"
        self.output = self.root / "release.json"
        self.bundle = self.root / "images.tar.gz"
        self.manifest = {"schema": 3, "bridge_protocol": 1, "layout_version": 1,
            "release": "ci-123-1", "parent_revision": "a" * 40, "gateway_revision": "b" * 40,
            "dirty_worktree": False, "source_content_sha256": "c" * 64,
            "images": {role: {"reference": f"vibebench-v3-{role}:v3-ci-123-1",
                "digest": "sha256:" + value * 64,
                "config_digest": "sha256:" + ("5" if role == "control" else "6") * 64, "platform": "linux/amd64"}
                for role, value in (("control", "1"), ("account", "2"))}}
        self.input.write_text(json.dumps(self.manifest))
        environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/v3",
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40,
            "GITHUB_REPOSITORY_OWNER": "SilentFlower", "GITHUB_REPOSITORY": "SilentFlower/vibecoding-bench"})
        environment.start()
        self.addCleanup(environment.stop)

    def _image(self, role):
        reference = f"ghcr.io/silentflower/vibebench-v3-{role}"
        return {"Id": self.manifest["images"][role]["digest"], "Os": "linux", "Architecture": "amd64",
            "RepoDigests": [reference + "@sha256:" + ("3" if role == "control" else "4") * 64],
            "Config": {"Labels": {"vibebench.product": "v3", "vibebench.role": role,
                "vibebench.release": "ci-123-1", "vibebench.parent-revision": "a" * 40,
                "vibebench.gateway-revision": "b" * 40}}}

    def _command(self, *args, **kwargs):
        if args[:3] == ("docker", "image", "inspect"):
            role = "control" if "control" in args[3] else "account"
            return json.dumps([self._image(role)])
        return ""

    def _publish(self, command=None):
        process = Mock(stdout=io.BytesIO(b"synthetic docker image package"))
        process.wait.return_value = 0
        process.poll.return_value = 0
        missing = SimpleNamespace(returncode=1, stdout="[]", stderr="No such image")
        with patch.object(manage, "command", side_effect=command or self._command), patch.object(manage.subprocess, "run", return_value=missing), patch.object(manage.subprocess, "Popen", return_value=process):
            return manage.publish(self.input, self.output, self.bundle)

    def test_completed_publication_keeps_config_and_registry_digest_distinct(self) -> None:
        """两件成功后才保存清单，镜像包来自同一组正式引用。

        :return: None
        """
        original = self.input.read_bytes()
        result = self._publish()
        self.assertEqual(json.loads(self.output.read_text()), result)
        self.assertEqual(self.input.read_bytes(), original)
        for role in ("control", "account"):
            entry = result["images"][role]
            self.assertEqual(entry["digest"], self.manifest["images"][role]["digest"])
            self.assertNotEqual(entry["digest"], entry["registry_digest"])
            self.assertTrue(entry["reference"].startswith("ghcr.io/silentflower/vibebench-v3-"))
        self.assertEqual(gzip.decompress(self.bundle.read_bytes()), b"synthetic docker image package")
        self.assertEqual(result["bundle"]["sha256"], manage._file_sha256(self.bundle))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_push_failure_retains_marker_and_refuses_same_attempt(self) -> None:
        """任一推送失败均无完整清单；同次重试不能覆盖部分发布。

        :return: None
        """
        for failed_role in ("control", "account"):
            with self.subTest(role=failed_role):
                started = self.output.with_name(self.output.name + ".started")
                started.unlink(missing_ok=True)

                def fail(*args, **kwargs):
                    """只拒绝指定推送，模拟第一件或第二件失败。"""
                    if args[:2] == ("docker", "push") and failed_role in args[2]:
                        raise subprocess.CalledProcessError(1, args)
                    return self._command(*args, **kwargs)

                with self.assertRaises(subprocess.CalledProcessError):
                    self._publish(fail)
                self.assertFalse(self.output.exists())
                self.assertFalse(self.bundle.exists())
                self.assertTrue(started.exists())
                with patch.object(manage, "command") as command:
                    with self.assertRaisesRegex(ValueError, "attempt"):
                        manage.publish(self.input, self.output, self.bundle)
                    command.assert_not_called()

    def test_dirty_wrong_ref_or_reused_output_refuses_before_docker(self) -> None:
        """来源、权限范围与输出边界不符时不产生外部写入。

        :return: None
        """
        for changes in ({"GITHUB_REF": "refs/heads/main"}, {"GITHUB_RUN_ATTEMPT": "2"}, {"GITHUB_REPOSITORY": "other/repo"}):
            with patch.dict(os.environ, changes), patch.object(manage, "command") as command:
                with self.assertRaises(ValueError):
                    manage.publish(self.input, self.output, self.bundle)
                command.assert_not_called()
        self.manifest["dirty_worktree"] = True
        self.input.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "未提交"):
            manage.publish(self.input, self.output, self.bundle)
        self.manifest["dirty_worktree"] = False
        self.input.write_text(json.dumps(self.manifest))
        self.output.write_bytes(b"existing release")
        with self.assertRaisesRegex(ValueError, "全新"):
            manage.publish(self.input, self.output, self.bundle)
        self.assertEqual(self.output.read_bytes(), b"existing release")

    def test_missing_registry_digest_cannot_produce_delivery_manifest(self) -> None:
        """docker push 返回成功但无可回查 digest 时仍然不能交付。

        :return: None
        """
        def missing(*args, **kwargs):
            """只让正式引用缺少仓库 digest，构建镜像本身仍合法。"""
            if args[:3] == ("docker", "image", "inspect") and args[3].startswith("ghcr.io"):
                image = self._image("control")
                image["RepoDigests"] = []
                return json.dumps([image])
            return self._command(*args, **kwargs)

        with self.assertRaisesRegex(ValueError, "digest"):
            self._publish(missing)
        self.assertFalse(self.output.exists())

    def test_pull_uses_registry_digest_and_rejects_wrong_config_before_tag(self) -> None:
        """远程按固定 digest 拉取，不能把配置 ID 当仓库 digest。

        :return: None
        """
        published = self._publish()
        local = SimpleNamespace(returncode=1, stdout="[]", stderr="No such image")
        with patch.object(manage, "command", side_effect=self._command) as command, patch.object(manage.subprocess, "run", return_value=local):
            manage.pull(self.output)
        pulls = [call.args[2] for call in command.call_args_list if call.args[:2] == ("docker", "pull")]
        self.assertEqual(len(pulls), 2)
        for role, pinned in zip(("control", "account"), pulls):
            entry = published["images"][role]
            self.assertTrue(pinned.endswith("@" + entry["registry_digest"]))

        def wrong(*args, **kwargs):
            """模拟仓库 digest 返回了与清单不符的配置。"""
            if args[:3] == ("docker", "image", "inspect"):
                return '[{"Id":"sha256:wrong"}]'
            return ""

        with patch.object(manage, "command", side_effect=wrong) as command, patch.object(manage.subprocess, "run", return_value=local):
            with self.assertRaisesRegex(ValueError, "配置 ID"):
                manage.pull(self.output)
            self.assertFalse(any(call.args[:2] == ("docker", "tag") for call in command.call_args_list))

    def test_offline_checksum_and_foreign_reference_refuse_before_load(self) -> None:
        """镜像包篡改或指向旧镜像的清单都不能触发 docker load。

        :return: None
        """
        result = self._publish()
        self.bundle.write_bytes(self.bundle.read_bytes() + b"changed")
        with patch.object(manage, "command") as command:
            with self.assertRaisesRegex(ValueError, "SHA256"):
                manage.load_bundle(self.output, self.bundle)
            command.assert_not_called()
        result["images"]["control"]["reference"] = "postgres:latest"
        self.output.write_text(json.dumps(result))
        with patch.object(manage, "command") as command:
            with self.assertRaisesRegex(ValueError, "v3 角色"):
                manage.load_bundle(self.output, self.bundle)
            command.assert_not_called()

    def test_existing_local_tag_cannot_be_overwritten_during_pull(self) -> None:
        """已存在的本地同批标签若内容不同，下载之前就拒绝。

        :return: None
        """
        self._publish()
        existing = SimpleNamespace(returncode=0, stdout='[{"Id":"sha256:foreign"}]', stderr="")
        with patch.object(manage.subprocess, "run", return_value=existing), patch.object(manage, "command") as command:
            with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
                manage.pull(self.output)
            command.assert_not_called()

    def test_classic_and_containerd_ids_match_the_same_published_image(self) -> None:
        """不同存储实现的 ID 可不同，仍需匹配同一配置或已发布的 OCI 根。

        :return: None
        """
        published = self._publish()
        entry = published["images"]["control"]
        self.assertTrue(manage._image_matches({"Id": entry["config_digest"]}, entry))
        self.assertTrue(manage._image_matches({"Id": entry["registry_digest"]}, entry))
        self.assertFalse(manage._image_matches({"Id": "sha256:" + "9" * 64}, entry))

    def test_containerd_archive_manifest_uses_original_config_digest(self) -> None:
        """containerd 重建 archive manifest 后仍以原始 config 严格确认内容。

        :return: None
        """
        published = self._publish()
        entry = published["images"]["control"]
        transformed = {"Id": "sha256:" + "9" * 64, "Descriptor": {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": "sha256:" + "9" * 64,
        }}
        with patch.object(manage, "_image_config_digest", return_value=entry["config_digest"]) as digest:
            self.assertTrue(manage._local_image_matches(entry["reference"], transformed, entry))
        digest.assert_called_once_with(entry["reference"])
        with patch.object(manage, "_image_config_digest", return_value="sha256:" + "8" * 64):
            self.assertFalse(manage._local_image_matches(entry["reference"], transformed, entry))
        self.assertFalse(manage._local_image_matches(entry["reference"], {
            "Id": transformed["Id"],
            "Descriptor": {"mediaType": "application/vnd.oci.image.index.v1+json"},
        }, entry))
        self.assertTrue(manage._container_image_matches(transformed["Id"], transformed["Id"], entry))
        self.assertFalse(manage._container_image_matches("sha256:" + "7" * 64, transformed["Id"], entry))


if __name__ == "__main__":
    unittest.main()
