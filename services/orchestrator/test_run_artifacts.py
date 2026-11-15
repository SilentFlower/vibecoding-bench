"""验证产物预览的工作区边界、有界读取与冻结版本分流。"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi import HTTPException
import main
from run_artifacts import PREVIEW_BYTES, read_workspace_file


class RunArtifactTests(unittest.TestCase):
    """只使用临时文件及合成运行，覆盖路径与读取生命周期。"""

    def test_text_empty_binary_and_utf8_boundary(self):
        """区分空文件、二进制和截断处的完整UTF-8字符。@return 无。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);work=root/'run';work.mkdir()
            (work/'empty').write_bytes(b'')
            self.assertEqual(read_workspace_file(root,'run','empty')['text'],'')
            (work/'binary').write_bytes(b'hello\0world')
            self.assertTrue(read_workspace_file(root,'run','binary')['binary'])
            (work/'long').write_bytes(b'a'*(PREVIEW_BYTES-1)+'中文'.encode())
            value=read_workspace_file(root,'run','long')
            self.assertTrue(value['truncated']);self.assertFalse(value['binary'])
            self.assertEqual(value['text'],'a'*(PREVIEW_BYTES-1))

    def test_reject_traversal_private_paths_links_and_fifo(self):
        """每级链接、私有目录及特殊文件不能进入预览。@return 无。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);work=root/'run';work.mkdir();(root/'outside').write_text('私有内容')
            (work/'link').symlink_to(root/'outside');(work/'linked-dir').symlink_to(root,target_is_directory=True)
            os.mkfifo(work/'pipe')
            for path in ['../outside','/etc/passwd','.claude-home/config','.bench-private','a/../../outside','a\\b']:
                with self.subTest(path=path),self.assertRaises(ValueError):read_workspace_file(root,'run',path)
            for path in ['link','linked-dir/outside','pipe']:
                with self.subTest(path=path),self.assertRaises((ValueError,OSError)):read_workspace_file(root,'run',path)

    def test_route_checks_visibility_and_uses_frozen_project_reader(self):
        """工程预览读取历史对象，隐藏运行在文件读取前被拒绝。@return 无。"""
        connection=Mock();connection.execute.return_value.fetchone.return_value={'run_kind':next(iter(main.PROJECT_RUN_KINDS))}
        manager=Mock();manager.run_context.return_value={'attempt_id':27};manager.artifact_file.return_value={'path':'src/a.py','text':'冻结版本','truncated':False}
        with patch.object(main,'_require_visible_run') as visible,patch.object(main,'get_db',return_value=connection),patch.object(main,'project_iterations',manager),patch.object(main,'read_workspace_file') as workspace:
            self.assertEqual(main.preview_run_file('synthetic','src/a.py')['text'],'冻结版本')
            visible.assert_called_once_with('synthetic');manager.artifact_file.assert_called_once_with(27,'src/a.py');workspace.assert_not_called()
        with patch.object(main,'_require_visible_run',side_effect=HTTPException(404,'隐藏运行')),patch.object(main,'get_db') as database:
            with self.assertRaises(HTTPException):main.preview_run_file('hidden','src/a.py')
            database.assert_not_called()

    def test_scenario_uses_the_same_evaluation_as_file_list(self):
        """场景运行使用该轮最新冻结评测清单的文件读取器。@return 无。"""
        connection=Mock();connection.execute.return_value.fetchone.return_value={'run_kind':next(iter(main.PROJECT_RUN_KINDS))}
        manager=Mock();manager.run_context.return_value={'scenario_execution':True,'id':9,'scenario_task_id':3};manager._one.return_value={'id':11};manager.scenarios.artifact_file.return_value={'path':'a.py','text':'场景冻结版本','truncated':False}
        with patch.object(main,'_require_visible_run'),patch.object(main,'get_db',return_value=connection),patch.object(main,'project_iterations',manager):
            self.assertEqual(main.preview_run_file('synthetic','a.py')['text'],'场景冻结版本')
            manager.scenarios.artifact_file.assert_called_once_with(9,3,'a.py',11)

    def test_capture_preview_uses_visible_run_and_existing_public_reader(self):
        """抓包预览沿用可见运行和元数据白名单，原始正文拒绝公开。@return 无。"""
        connection=Mock();connection.execute.return_value.fetchone.return_value={'id':'synthetic','run_kind':'capture'}
        base=Path('/synthetic/capture')
        with patch.object(main,'_require_visible_run') as visible,patch.object(main,'get_db',return_value=connection),patch.object(main,'_resolve_capture_flows_dirs',return_value=(base,base)),patch.object(main,'capture_file_preview',return_value={'entries':[]}) as reader:
            self.assertEqual(main.get_capture('synthetic','capture_index.json'),{'entries':[]});visible.assert_called_once_with('synthetic');reader.assert_called_once_with(base,'capture_index.json')
        with patch.object(main,'_require_visible_run',side_effect=HTTPException(404,'隐藏运行')),patch.object(main,'capture_file_preview') as reader:
            with self.assertRaises(HTTPException):main.get_capture('hidden','capture_index.json')
            reader.assert_not_called()
        with patch.object(main,'_require_visible_run'),patch.object(main,'get_db',return_value=connection),patch.object(main,'_resolve_capture_flows_dirs',return_value=(base,base)),patch.object(main,'capture_file_preview',side_effect=ValueError('禁止读取原文')):
            with self.assertRaises(HTTPException) as error:main.get_capture('synthetic','raw_body.json')
            self.assertEqual(error.exception.status_code,404)
