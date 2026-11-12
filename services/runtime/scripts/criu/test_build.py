"""验证固定 CRIU 配方的来源校验及失败目录所有权。"""
import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('criu_build', Path(__file__).with_name('build.py'))
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class BuildBoundaryTest(unittest.TestCase):
    """核对错误输入和失败构建的资源边界。"""

    def test_wrong_archive_stops_before_creating_output(self):
        """错误来源在任何构建命令之前拒绝。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'source.tar.gz'
            archive.write_bytes(b'wrong-source')
            with patch.object(BUILD.subprocess, 'run') as execute:
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    BUILD.build(root / 'output', archive)
                execute.assert_not_called()
            self.assertFalse((root / 'output').exists())
            self.assertEqual(archive.read_bytes(), b'wrong-source')

    def test_existing_output_is_preserved(self):
        """已有输出及其内容保持原所有权。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'output'
            output.mkdir()
            marker = output / 'previous-build'
            marker.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                BUILD.build(output)
            self.assertEqual(marker.read_bytes(), b'keep')

    def test_failed_build_cleans_only_its_new_output(self):
        """失败只清理本轮创建的目录。@return 无。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'fixture.tar.gz'
            with tarfile.open(archive, 'w:gz') as stream:
                info = tarfile.TarInfo('criu-4.2/Makefile')
                content = b'fixture'
                info.size = len(content)
                stream.addfile(info, io.BytesIO(content))
            marker = root / 'preserved'
            marker.write_bytes(b'keep')
            with patch.object(BUILD, 'verify_archive'), patch.object(BUILD, 'run', side_effect=RuntimeError('构建失败')):
                with self.assertRaisesRegex(RuntimeError, '构建失败'):
                    BUILD.build(root / 'output', archive)
            self.assertFalse((root / 'output').exists())
            self.assertTrue(archive.exists())
            self.assertEqual(marker.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
