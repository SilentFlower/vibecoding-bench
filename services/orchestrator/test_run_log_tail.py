"""验证运行日志尾部读取的边界与旧完整文件入口。"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi import HTTPException
from fastapi.responses import FileResponse
import main


class RunLogTailTests(unittest.TestCase):
    """仅使用本地合成日志，不访问真实运行环境。"""

    def test_bounded_tail_preserves_full_file_route(self):
        """尾部读取限制字节且保持完整行，省略参数仍返回文件。@return 无。"""
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'transcript.log'
            path.write_text('较早的运行日志\n'*200+'最后一行\n')
            runtime=Mock();runtime.run_artifact_path.return_value=path
            with patch.object(main,'account_runtime',runtime),patch.object(main,'_require_visible_run') as visible:
                response=main.get_transcript('synthetic-run',1024)
                self.assertLessEqual(len(response.body),1024)
                self.assertTrue(response.body.decode().endswith('最后一行\n'))
                self.assertEqual(response.headers['x-log-truncated'],'true')
                self.assertIsInstance(main.get_transcript('synthetic-run'),FileResponse)
                with self.assertRaises(HTTPException):main.get_transcript('synthetic-run',1048577)
                self.assertTrue(visible.called)


class RuntimeSummaryTests(unittest.TestCase):
    """导航计数只使用数据库完整聚合。"""

    def test_summary_counts_active_visible_runs(self):
        """已删除和终结记录不计入活动数量，额度等待保持计数。@return 无。"""
        connection = sqlite3.connect(':memory:')
        connection.execute('CREATE TABLE runs(status TEXT,deleted_at TEXT)')
        connection.executemany('INSERT INTO runs VALUES(?,?)',[
            ('queued',None),('running',None),('stopping',None),('quota_wait',None),
            ('succeeded',None),('failed',None),('running','2026-11-15')])
        with patch.object(main,'get_db',return_value=connection):
            self.assertEqual({'active_runs':4},main.runtime_summary())
