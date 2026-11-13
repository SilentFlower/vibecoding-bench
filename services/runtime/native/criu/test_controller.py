"""共享映像模板的失败、撤销及恢复取消资源回归。"""
import asyncio
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import controller
from protocol import receive, send


class ControllerImageLifetimeTest(unittest.IsolatedAsyncioTestCase):
    """真实句柄与控制连接必须覆盖在途恢复生命周期。"""

    async def asyncSetUp(self) -> None:
        """准备合成进程目录和私有控制器。@return 无。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work = self.root / 'native'
        self.worker = str(uuid4())
        self.identifier = str(uuid4())
        source = self.work / self.worker
        for name in ('home', 'config', 'cwd'):
            (source / name).mkdir(parents=True)
        proc = self.root / 'proc'
        (proc / 'task/4242').mkdir(parents=True)
        (proc / 'cwd').symlink_to(source / 'cwd')
        (proc / 'environ').write_bytes(b'\0'.join([
            b'CCRB_TEMPLATE_ID=' + self.identifier.encode(), b'CCRB_WORKER_ID=' + self.worker.encode(),
            b'HOME=' + str(source / 'home').encode(), b'CLAUDE_CONFIG_DIR=' + str(source / 'config').encode()]))

        def process_path(*parts):
            """仅将合成进程目录映射到夹具。@param parts 路径片段。@return 本地路径。"""
            path = Path(*parts)
            return proc / path.relative_to('/proc/4242') if path.is_relative_to('/proc/4242') else path

        def freeze(source, target, owner):
            """建立独立空目录以隔离文件复制验收。@param source 来源。@param target 目标。@param owner 所有者。@return 空元数据。"""
            target.mkdir()
            return {}

        original_readlink = os.readlink

        def process_link(path, *args, **kwargs):
            """提供种子的合成管道名称。@param path 路径。@param args 位置参数。@param kwargs 关键字参数。@return 链接目标。"""
            if str(path).startswith('/proc/4242/fd/'):
                return 'pipe:[' + str(99 + int(str(path).rsplit('/', 1)[1])) + ']'
            return original_readlink(path, *args, **kwargs)

        self.base = os.open('/dev/null', os.O_RDONLY)
        self.pinned = os.dup(self.base)
        self.patches = [patch.object(controller, 'ROOT', self.root / 'criu'),
            patch.object(controller, 'Path', side_effect=process_path),
            patch.object(controller, 'process_identity', return_value=(12, '10', {})),
            patch.object(controller, 'restricted', return_value=True),
            patch.object(controller.os, 'pidfd_open', side_effect=lambda pid: os.dup(self.base)),
            patch.object(controller, 'pin_image', return_value=self.pinned),
            patch.object(controller.os, 'readlink', side_effect=process_link),
            patch.object(controller, 'freeze_tree', side_effect=freeze)]
        for item in self.patches:
            item.start()
        (self.root / 'criu/templates').mkdir(parents=True)
        self.service = controller.Controller(12, 4, str(self.work), {'image_bytes': 42, 'image_sha256': 'a' * 64})
        self.service.run = AsyncMock()
        self.value = {'type': 'template', 'key': 'b' * 64, 'template': self.identifier, 'worker': self.worker, 'pid': 4242}

    async def asyncTearDown(self) -> None:
        """撤销补丁和测试私有资源。@return 无。"""
        for item in reversed(self.patches):
            item.stop()
        for descriptor in (self.pinned, self.base):
            try:
                os.close(descriptor)
            except OSError:
                pass
        self.temporary.cleanup()

    async def test_dump_failure_closes_pinned_image(self) -> None:
        """dump失败关闭种子映像句柄并撤销登记。@return 无。"""
        self.service.run.side_effect = ValueError('RESTORE_CRIU_FAILED')
        with self.assertRaisesRegex(ValueError, 'CRIU_FAILED'):
            await self.service.template(self.value, None)
        with self.assertRaises(OSError):
            os.fstat(self.pinned)
        self.assertFalse(self.service.templates)
        self.assertFalse(self.service.building)
        self.assertFalse((self.root / 'criu/templates' / self.identifier).exists())

    async def test_template_revocation_retains_image_until_inflight_cleanup(self) -> None:
        """模板EOF与控制器close共同等待在途引用，避免二次取消清理。@return 无。"""
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        with patch.object(self.service, 'authenticate'):
            handling = asyncio.create_task(self.service.handle(left))
            closing = None
            try:
                await send(right, self.value)
                self.assertEqual((await asyncio.wait_for(receive(right), 2))['type'], 'template_ready')
                template = self.service.templates[self.identifier]
                template.users = 1
                template.drained.clear()
                right.close()
                async with asyncio.timeout(2):
                    while template.valid:
                        await asyncio.sleep(0)
                self.assertFalse(self.service.templates)
                self.assertEqual(os.fstat(self.pinned).st_size, 0)
                closing = asyncio.create_task(self.service.close())
                await asyncio.sleep(0)
                self.assertFalse(closing.done())
                self.assertEqual(os.fstat(self.pinned).st_size, 0)
                template.users = 0
                template.drained.set()
                await asyncio.wait_for(closing, 2)
                await handling
                with self.assertRaises(OSError):
                    os.fstat(self.pinned)
            finally:
                right.close()
                if not handling.done():
                    handling.cancel()
                await asyncio.gather(handling, return_exceptions=True)
                if closing is not None:
                    await asyncio.gather(closing, return_exceptions=True)

    def make_restorable_template(self) -> controller.Template:
        """构造可进入恢复阶段的冻结夹具。@return 已登记模板。"""
        template_root = self.root / 'criu/templates' / self.identifier
        for name in ('images', 'fs'):
            (template_root / name).mkdir(parents=True)
        (self.root / 'criu/instances').mkdir()
        frozen = {}
        for name in ('images', 'fs'):
            info = (template_root / name).lstat()
            frozen[name] = {'identity': (info.st_dev, info.st_ino, info.st_size, info.st_ctime_ns,
                info.st_mtime_ns, info.st_mode, info.st_uid, info.st_nlink)}
        template = controller.Template(self.value, template_root, {}, frozen, {}, self.pinned)
        template.drained.set()
        self.service.templates[self.identifier] = template
        return template

    async def test_restore_launch_failure_closes_instance_fd_and_preserves_template(self) -> None:
        """加载器创建失败只清理本次恢复引用，模板源句柄保持有效。@return 无。"""
        template = self.make_restorable_template()
        opened = os.dup(self.base)
        before = len(list(Path('/proc/self/fd').iterdir()))
        value = {'template': self.identifier, 'key': self.value['key'], 'worker': str(uuid4())}
        with patch.object(controller, 'reopen_image', return_value=opened), patch.object(
                controller.asyncio, 'create_subprocess_exec', AsyncMock(side_effect=OSError('合成启动失败'))):
            with self.assertRaisesRegex(OSError, '合成启动失败'):
                await self.service.restore(value, None)
        self.assertEqual(self.service.active, 0)
        self.assertEqual(template.users, 0)
        self.assertTrue(template.drained.is_set())
        self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), before - 1)
        with self.assertRaises(OSError):
            os.fstat(opened)
        self.assertEqual(os.fstat(self.pinned).st_size, 0)
        self.assertEqual(list((self.root / 'criu/instances').iterdir()), [])

    async def test_partial_pipe_failure_releases_all_previously_created_fds(self) -> None:
        """第二次管道分配失败时，首对管道和实例映像均关闭。@return 无。"""
        template = self.make_restorable_template()
        opened = os.dup(self.base)
        original = os.pipe2
        allocated = []

        def pipe_pair(flags):
            """在部分成功后注入资源耗尽。@param flags 管道标志。@return 首对管道。"""
            if allocated:
                raise OSError('合成管道额度不足')
            pair = original(flags)
            allocated.extend(pair)
            return pair

        value = {'template': self.identifier, 'key': self.value['key'], 'worker': str(uuid4())}
        with patch.object(controller, 'reopen_image', return_value=opened), patch.object(controller.os, 'pipe2', side_effect=pipe_pair):
            with self.assertRaisesRegex(OSError, '合成管道额度不足'):
                await self.service.restore(value, None)
        for descriptor in (opened, *allocated):
            with self.assertRaises(OSError):
                os.fstat(descriptor)
        self.assertEqual(self.service.active, 0)
        self.assertEqual(template.users, 0)
        self.assertTrue(template.drained.is_set())
        self.assertEqual(os.fstat(self.pinned).st_size, 0)


if __name__ == '__main__':
    unittest.main()
