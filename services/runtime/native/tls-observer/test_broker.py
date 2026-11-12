"""受限加载器协议、归属和大事件读取回归；不建立网络。"""
import ctypes
import asyncio
import errno
import hashlib
import json
import struct
import unittest
from unittest.mock import AsyncMock, Mock, patch

from broker import Broker, validate
from observer import IMAGE_SHA256, Observer
from test_http_capture import request


class BrokerTests(unittest.TestCase):
    """确认客户端只能指向同sender的固定执行体。"""

    def test_peer_target_schema_and_image_are_admitted_together(self):
        """额外参数、外来PID及未知映像均在加载前拒绝。@return None。"""
        value = {'pid': 12, 'worker': '11111111-1111-4111-8111-111111111111',
            'capture': '22222222-2222-4222-8222-222222222222', 'image': IMAGE_SHA256}
        with patch('broker.identity', return_value=(10, 1001, '123')):
            self.assertEqual(validate(value, 11, 10), '123')
            for other in ({**value, 'pid': True}, {**value, 'owner': 10}, {**value, 'image': '0'*64},
                          {**value, 'worker': 'not-a-uuid'}, {**value, 'pid': -1}):
                with self.assertRaises(ValueError):
                    validate(other, 11, 10)
        for other in ((99, 1001, '123'), (10, 0, '123')):
            with patch('broker.identity', return_value=other), self.assertRaises(ValueError):
                validate(value, 11, 10)

    def test_all_event_capacities_keep_exact_hash_and_bounded_preview(self):
        """六档实际接受量与完整摘要独立于正文预览。@return None。"""
        for capacity in (16384, 65536, 262144, 1048576, 4194304, 8388608):
            body = b'x' * (capacity - 256)
            raw = request(body)
            observer = Observer.__new__(Observer)
            observer.pid = 1234
            observer.connections = {}
            observer.writes = observer.accepted = 0
            observer.reason = None
            header = struct.pack('<QQQII', 1234 << 32 | 1, 99, 1, len(raw), len(raw))
            event = ctypes.create_string_buffer(header + raw + b'\0' * (capacity - len(raw)))
            observer._sample(None, event, 32 + capacity)
            self.assertIsNone(observer.reason)
            self.assertEqual(observer.accepted, len(raw))
            evidence = observer.connections[99].evidence(None)
            self.assertTrue(evidence['complete'])
            self.assertEqual(evidence['body_sha256'], hashlib.sha256(body).hexdigest())
            self.assertLessEqual(len(evidence['body'].encode()), 2 * 1024 * 1024)

    def test_event_reader_only_copies_header_and_accepted_range(self):
        """容量尾部不进入Python副本，非法size在解引用前拒绝。@return None。"""
        observer = Observer.__new__(Observer)
        observer.pid = 1234
        observer.connections = {}
        observer.writes = observer.accepted = 0
        observer.reason = None
        raw = request()
        event = ctypes.create_string_buffer(struct.pack('<QQQII', 1234 << 32, 99, 1, len(raw), len(raw)) + raw)
        original = ctypes.string_at
        with patch('observer.c.string_at', wraps=original) as copying:
            observer._sample(None, event, 8388640)
            self.assertEqual([call.args[1] for call in copying.call_args_list], [32, len(raw)])
            observer._sample(None, None, 17)
            self.assertEqual(observer.reason, 'EVENT_INVALID')
            self.assertEqual(copying.call_count, 2)


class BrokerCleanupTests(unittest.IsolatedAsyncioTestCase):
    """故障及EOF均归还本次采集名额，清理不分配帮助进程句柄。"""

    def setUp(self):
        """准备固定的同账号私有请求。@return None。"""
        self.value = {'pid': 12, 'worker': '11111111-1111-4111-8111-111111111111',
            'capture': '22222222-2222-4222-8222-222222222222', 'image': IMAGE_SHA256}
        self.reader = Mock()
        self.reader.readline = AsyncMock(side_effect=[(json.dumps(self.value)+'\n').encode(), b''])
        self.writer = Mock()
        self.writer.get_extra_info.return_value.getsockopt.return_value = struct.pack('3i', 11, 1001, 1001)
        self.writer.wait_closed = AsyncMock()

    async def test_target_descriptor_exhaustion_does_not_start_helper(self):
        """目标句柄耗尽在派生前拒绝，连接名额完整释放。@return None。"""
        service = Broker(10, 6)
        with patch('broker.identity', return_value=(10, 1001, '123')), \
                patch('broker.os.pidfd_open', side_effect=OSError(errno.EMFILE, '合成故障')), \
                patch('broker.asyncio.create_subprocess_exec', new=AsyncMock()) as spawn:
            await asyncio.wait_for(service.handle(self.reader, self.writer), .2)
        spawn.assert_not_awaited()
        self.assertEqual(service.active, set())
        self.assertEqual(service.clients, 0)
        self.writer.close.assert_called_once()

    async def test_eof_closes_supervisor_without_helper_descriptor(self):
        """EOF监督释放不依赖第二次pidfd_open，复现旧故障的槽位可重新使用。@return None。"""
        service = Broker(10, 6)
        exited = asyncio.Event()
        process = Mock(returncode=None)
        process.stdout = asyncio.StreamReader()
        process.stdin.close.side_effect = exited.set

        async def wait():
            """模拟监督进程收到EOF后退出。@return 进程终态。"""
            await exited.wait()
            return 0

        process.wait = AsyncMock(side_effect=wait)
        with patch('broker.identity', return_value=(10, 1001, '123')), \
                patch('broker.os.pidfd_open', side_effect=[101, OSError(errno.EMFILE, '合成故障')]) as descriptors, \
                patch('broker.os.close') as closing, \
                patch('broker.asyncio.create_subprocess_exec', new=AsyncMock(return_value=process)):
            await asyncio.wait_for(service.handle(self.reader, self.writer), .2)
        descriptors.assert_called_once_with(12)
        closing.assert_called_once_with(101)
        process.stdin.close.assert_called_once()
        self.assertEqual(service.active, set())
        self.assertEqual(service.clients, 0)

    async def test_abandoned_reader_cannot_hold_connection_cleanup(self):
        """对端拒绝读取时有界放弃尾部缓冲，采集名额保持释放。@return None。"""
        service = Broker(10, 6)

        async def stalled():
            """模拟socket尾部缓冲始终无法刷出。@return 无正常返回。"""
            await asyncio.Event().wait()

        self.writer.wait_closed = AsyncMock(side_effect=stalled)
        with patch('broker.identity', return_value=(10, 1001, '123')), \
                patch('broker.os.pidfd_open', side_effect=OSError(errno.EMFILE, '合成故障')):
            await asyncio.wait_for(service.handle(self.reader, self.writer), .5)
        self.writer.transport.abort.assert_called_once()
        self.assertEqual(service.clients, 0)
        self.assertEqual(service.active, set())


if __name__ == '__main__':
    unittest.main()
