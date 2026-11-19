"""用合成压缩映像验证处理产物准备和原子交付，全部断开外部下载。"""
import hashlib
import io
import lzma
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agy_artifact as artifact


class AgyArtifactTests(unittest.TestCase):
    """覆盖缓存、压缩身份与实际解码边界。"""

    def setUp(self) -> None:
        """准备独立小型执行映像和固定摘要。@return 无。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.image = b'synthetic-fixed-image' * 200
        self.archive = lzma.compress(self.image)
        self.source = self.root / 'existing.xz'
        self.source.write_bytes(self.archive)
        constants = patch.multiple(artifact, ARCHIVE_BYTES=len(self.archive),
            ARCHIVE_SHA256=hashlib.sha256(self.archive).hexdigest(), SOURCE_BYTES=len(self.image),
            SOURCE_SHA256=hashlib.sha256(self.image).hexdigest(), BLOCK=1024)
        constants.start()
        self.addCleanup(constants.stop)

    def test_export_and_prepare_reuse_existing_processed_bytes(self) -> None:
        """导出只包含固定附件，准备得到相同执行映像。@return 无。"""
        output = self.root / 'export'
        value = artifact.export_artifact(self.source, output)
        self.assertEqual({artifact.ASSET, 'agy-artifact.json'}, {p.name for p in output.iterdir()})
        self.assertEqual(self.archive, (output / artifact.ASSET).read_bytes())
        self.assertEqual(hashlib.sha256(self.image).hexdigest(), value['image']['sha256'])
        with patch.object(artifact, 'urlopen') as download:
            binary = artifact.prepare(self.root / 'prepared', output / artifact.ASSET)
            self.assertEqual(self.image, binary.read_bytes())
            self.assertEqual(binary, artifact.prepare(binary.parent))
            download.assert_not_called()

    def test_cold_cache_reads_only_own_artifact_then_reuses_cache(self) -> None:
        """冷缓存读取自有附件，后续准备沿压缩缓存接续。@return 无。"""
        with patch.object(artifact, 'urlopen', return_value=io.BytesIO(self.archive)) as download:
            binary = artifact.prepare(self.root / 'prepared')
            download.assert_called_once_with(artifact.URL, timeout=60)
            binary.unlink()
            self.assertEqual(self.image, artifact.prepare(binary.parent).read_bytes())
            self.assertEqual(1, download.call_count)

    def test_changed_compressed_identity_never_publishes_output(self) -> None:
        """解码相同但压缩身份变化仍拒绝。@return 无。"""
        with patch.object(artifact, 'ARCHIVE_SHA256', '0' * 64):
            with self.assertRaises(ValueError):
                artifact.prepare(self.root / 'prepared', self.source)
        self.assertFalse((self.root / 'prepared/agy-1.5.9').exists())

    def test_truncated_trailing_and_concatenated_streams_are_rejected(self) -> None:
        """压缩协议边界独立于外层摘要，尾随与拼接不被接受。@return 无。"""
        for number, data in enumerate([self.archive[:-2], self.archive + b'tail', self.archive * 2]):
            with self.subTest(number=number):
                path = self.root / f'bad-{number}.xz'
                path.write_bytes(data)
                with patch.multiple(artifact, ARCHIVE_BYTES=len(data), ARCHIVE_SHA256=hashlib.sha256(data).hexdigest()):
                    with self.assertRaises((ValueError, lzma.LZMAError)):
                        artifact.prepare(self.root / f'prepared-{number}', path)
                self.assertFalse((self.root / f'prepared-{number}/agy-1.5.9').exists())

    def test_oversized_or_wrong_decoded_image_is_rejected(self) -> None:
        """解码预算和完整执行体摘要均独立核对。@return 无。"""
        for changes in [{'SOURCE_BYTES': len(self.image) - 1}, {'SOURCE_SHA256': '0' * 64}]:
            with self.subTest(changes=changes), patch.multiple(artifact, **changes):
                with self.assertRaises(ValueError):
                    artifact.prepare(self.root / 'prepared', self.source)
        self.assertFalse((self.root / 'prepared/agy-1.5.9').exists())

    def test_cache_links_and_corruption_are_rejected(self) -> None:
        """缓存链接及同长度损坏拒绝进入镜像输入。@return 无。"""
        folder = self.root / 'prepared'
        folder.mkdir()
        target = folder / 'agy-1.5.9'
        raw = self.root / 'raw'
        raw.write_bytes(self.image)
        target.symlink_to(raw)
        with self.assertRaises(ValueError):
            artifact.prepare(folder)
        target.unlink()
        target.write_bytes(b'0' * len(self.image))
        with self.assertRaises(ValueError):
            artifact.prepare(folder)

    def test_download_failure_leaves_no_accepted_cache(self) -> None:
        """下载中断保留原子交付边界。@return 无。"""
        with patch.object(artifact, 'urlopen', side_effect=OSError('synthetic disconnect')):
            with self.assertRaises(OSError):
                artifact.prepare(self.root / 'prepared')
        self.assertEqual([], list((self.root / 'prepared').iterdir()))
