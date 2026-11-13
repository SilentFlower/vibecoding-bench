"""共享执行体的真实memfd身份、权限、映射及引用边界回归。"""
import fcntl
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shared_image import IMAGE_LINK, IMAGE_NAME, REQUIRED_SEALS, image_identity, pin_image, reopen_image, verify_restored_image


@unittest.skipUnless(os.getuid() == 0 and hasattr(os, 'memfd_create'), '可信元数据验证需要Linux root测试环境')
class SharedImageTest(unittest.TestCase):
    """通过内核对象验证共享身份，拒绝内容相同的其他inode。"""

    def setUp(self) -> None:
        """创建合成封存映像。@return 无。"""
        self.descriptors = []
        self.content = b'synthetic-executable' * 256
        self.profile = {'image_bytes': len(self.content), 'image_sha256': hashlib.sha256(self.content).hexdigest()}
        self.image = self.create_image()

    def tearDown(self) -> None:
        """关闭本测试仍拥有的句柄。@return 无。"""
        for descriptor in self.descriptors:
            os.close(descriptor)

    def create_image(self, name: str = IMAGE_NAME, seals: int = REQUIRED_SEALS) -> int:
        """创建真实封存对象。@param name 调试名称。@param seals 封存位。@return 只读FD。"""
        descriptor = os.memfd_create(name, os.MFD_ALLOW_SEALING)
        try:
            os.write(descriptor, self.content)
            os.fchmod(descriptor, 0o555)
            fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
            opened = os.open(f'/proc/self/fd/{descriptor}', os.O_RDONLY | os.O_CLOEXEC)
        finally:
            os.close(descriptor)
        self.descriptors.append(opened)
        return opened

    def test_reopen_shares_inode_but_preserves_independent_offsets_and_lifetime(self) -> None:
        """重新open保持独立偏移，原持有FD关闭后引用仍有效。@return 无。"""
        first = reopen_image(self.image, self.profile)
        second = reopen_image(self.image, self.profile)
        self.descriptors.extend((first, second))
        self.assertEqual(image_identity(first, self.profile), image_identity(second, self.profile))
        os.read(first, 11)
        self.assertEqual(os.lseek(second, 0, os.SEEK_CUR), 0)
        os.close(self.image)
        self.descriptors.remove(self.image)
        self.assertEqual(os.read(second, len(self.content)), self.content)
        os.close(first)
        self.descriptors.remove(first)
        self.assertEqual(os.pread(second, 10, 0), self.content[:10])

    def test_rejects_wrong_name_size_seals_and_mode(self) -> None:
        """名称、大小、封存和权限均参与准入。@return 无。"""
        for descriptor in (self.create_image('other'), self.create_image(seals=fcntl.F_SEAL_SEAL)):
            with self.assertRaisesRegex(ValueError, 'IMAGE_IDENTITY'):
                image_identity(descriptor, self.profile)
        with self.assertRaisesRegex(ValueError, 'IMAGE_IDENTITY'):
            image_identity(self.image, {**self.profile, 'image_bytes': len(self.content) + 1})
        os.fchmod(self.image, 0o755)
        with self.assertRaisesRegex(ValueError, 'IMAGE_IDENTITY'):
            reopen_image(self.image, self.profile)

    def test_rejects_writable_source_descriptor(self) -> None:
        """源句柄访问模式不能沿FD移交扩大。@return 无。"""
        opened = os.open(f'/proc/self/fd/{self.image}', os.O_RDWR)
        self.descriptors.append(opened)
        with self.assertRaisesRegex(ValueError, 'IMAGE_IDENTITY'):
            image_identity(opened, self.profile)

    def test_pin_checks_digest_without_changing_existing_offsets(self) -> None:
        """摘要核验使用pread，避免影响其他持有者。@return 无。"""
        original = os.open
        opened = []

        def executable(path, flags):
            """为合成PID提供实际memfd。@param path 路径。@param flags 标志。@return 新FD。"""
            descriptor = original(f'/proc/self/fd/{self.image}' if path == '/proc/123456/exe' else path, flags)
            opened.append(descriptor)
            return descriptor

        os.lseek(self.image, 7, os.SEEK_SET)
        with patch('shared_image.os.open', side_effect=executable):
            held = pin_image(123456, self.profile)
        self.descriptors.append(held)
        self.assertEqual(os.lseek(self.image, 0, os.SEEK_CUR), 7)
        self.assertEqual(image_identity(held, self.profile), image_identity(self.image, self.profile))
        with patch('shared_image.os.open', side_effect=executable):
            with self.assertRaisesRegex(ValueError, 'IMAGE_IDENTITY'):
                pin_image(123456, {**self.profile, 'image_sha256': '0' * 64})
        with self.assertRaises(OSError):
            os.fstat(opened[-1])

    def test_pin_protects_private_execution_mode_and_fails_safely(self) -> None:
        """私有执行权限可转换，改权失败发生在属主转换之前。@return 无。"""
        original = os.open
        os.fchmod(self.image, 0o700)

        def executable(path, flags):
            """为合成PID打开现有映像。@param path 路径。@param flags 标志。@return 新FD。"""
            return original(f'/proc/self/fd/{self.image}' if path == '/proc/123456/exe' else path, flags)

        with patch('shared_image.os.open', side_effect=executable), patch('shared_image.os.fchown') as chown, patch(
                'shared_image.os.fchmod', side_effect=PermissionError('合成改权拒绝')):
            with self.assertRaisesRegex(PermissionError, '合成改权拒绝'):
                pin_image(123456, self.profile)
        chown.assert_not_called()
        self.assertEqual(os.fstat(self.image).st_mode & 0o777, 0o700)
        with patch('shared_image.os.open', side_effect=executable):
            opened = pin_image(123456, self.profile)
        self.descriptors.append(opened)
        self.assertEqual(image_identity(opened, self.profile), image_identity(self.image, self.profile))

    def test_owner_change_failure_preserves_read_execute_permissions(self) -> None:
        """属主转换失败后仍保留业务身份的读执行条件。@return 无。"""
        original = os.open
        os.fchmod(self.image, 0o700)

        def executable(path, flags):
            """为合成PID打开现有映像。@param path 路径。@param flags 标志。@return 新FD。"""
            return original(f'/proc/self/fd/{self.image}' if path == '/proc/123456/exe' else path, flags)

        with patch('shared_image.os.open', side_effect=executable), patch(
                'shared_image.os.fchown', side_effect=PermissionError('合成属主拒绝')):
            with self.assertRaisesRegex(PermissionError, '合成属主拒绝'):
                pin_image(123456, self.profile)
        self.assertEqual(os.fstat(self.image).st_mode & 0o777, 0o555)

    def check_restored(self, actual: int, mapping: str) -> None:
        """向恢复校验提供合成PID和真实执行体FD。@param actual 执行体FD。@param mapping 映射文本。@return 无。"""
        original = os.open

        def executable(path, flags):
            """返回实际执行体引用。@param path 路径。@param flags 标志。@return 新FD。"""
            return original(f'/proc/self/fd/{actual}' if path == '/proc/123456/exe' else path, flags)

        with patch('shared_image.os.open', side_effect=executable), patch.object(Path, 'read_text', return_value=mapping):
            verify_restored_image(123456, self.image, self.profile)

    def mapping(self, permissions: str = 'rw-p', inode: int | None = None) -> str:
        """构造真实设备与inode对应的映射行。@param permissions 权限。@param inode 可选其他inode。@return maps文本。"""
        device, actual = image_identity(self.image, self.profile)
        return f'1000-2000 {permissions} 00000000 {os.major(device):02x}:{os.minor(device):02x} {actual if inode is None else inode} {IMAGE_LINK}\n'

    def test_restore_accepts_private_write_mapping(self) -> None:
        """内容封存允许各实例的私有COW写页。@return 无。"""
        self.check_restored(self.image, self.mapping())

    def test_restore_rejects_identical_content_with_different_inode(self) -> None:
        """同名且摘要相同仍不能代替指定背板。@return 无。"""
        duplicate = self.create_image()
        with self.assertRaisesRegex(ValueError, 'IMAGE_IDENTITY'):
            self.check_restored(duplicate, self.mapping())

    def test_restore_rejects_wrong_missing_or_shared_write_mapping(self) -> None:
        """实际映射必须属于指定背板，私有写入保持原类型。@return 无。"""
        for mapping in ('', self.mapping('rw-s'), self.mapping(inode=0)):
            with self.subTest(mapping=mapping), self.assertRaisesRegex(ValueError, 'IMAGE_MAPPING'):
                self.check_restored(self.image, mapping)

    def test_regular_file_is_rejected(self) -> None:
        """普通文件不满足封存memfd合同。@return 无。"""
        with tempfile.TemporaryFile() as stream:
            stream.write(self.content)
            stream.flush()
            with self.assertRaisesRegex(ValueError, 'IMAGE_IDENTITY'):
                image_identity(stream.fileno(), self.profile)


if __name__ == '__main__':
    unittest.main()
