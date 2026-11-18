"""场景输入文件的真实替换、旧现场保存与有限证明拒绝回归。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from project_input_files import bind_code_input_files, materialize_input_files, prepare_scenario_input_files
from project_library import read_document, snapshot_tree, write_document


class ProjectInputFileTests(unittest.TestCase):
    """所有目录、对象和标记均为本次测试专用实际文件。"""

    def setUp(self) -> None:
        """建立已接受源码及另一份未接受现场。:return: None。"""
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data=Path(temporary.name)
        self.objects,self.manifests=self.data/'objects',self.data/'manifests'
        accepted=self.data/'accepted'
        accepted.mkdir()
        (accepted/'app.py').write_text('已接受代码')
        self.base=snapshot_tree(accepted,self.objects)
        write_document(self.manifests/(self.base['digest']+'.json'),self.base)
        self.workspace=self.data/'workspace'
        self.workspace.mkdir()
        (self.workspace/'partial.txt').write_text('原未接受半成品')
        self.marker=self.data/'markers/code-dependency.json'
        self.identity={'task_id':1,'dependencies':{'7':self.base['digest']},
            'base_checkpoint_digest':self.base['digest'],'base_checkpoint_job_id':7}

    def bind(self, **options) -> dict:
        """调用原文件交接，使用真实对象恢复。:param options: 本次证明或暂存参数。:return: 原标记。"""
        return bind_code_input_files(self.data,self.workspace,self.marker,self.identity,self.objects,self.manifests,
            lambda digest:self.assertEqual(self.base['digest'],digest),**options)

    def test_accepted_code_replaces_workspace_and_saved_partial_remains_after_idempotent_resume(self) -> None:
        """交接保留旧现场，已ready的同任务接续保留后来半成品。:return: None。"""
        result=self.bind()
        self.assertEqual(self.base['digest'],snapshot_tree(self.workspace)['digest'])
        saved=self.data/result['saved_relative']
        self.assertEqual('原未接受半成品',(saved/'partial.txt').read_text())
        (self.workspace/'new-partial.txt').write_text('本任务新半成品')
        self.assertEqual(result,self.bind())
        self.assertEqual('本任务新半成品',(self.workspace/'new-partial.txt').read_text())

    def test_second_rename_unknown_keeps_replacing_and_original_saved_tree(self) -> None:
        """替换中断只保留原意图和原现场，后续调用拒绝重建。:return: None。"""
        original=os.rename
        def rename(source,target):
            if Path(source)==self.workspace:
                return original(source,target)
            raise OSError('合成第二次发布失败')
        with patch('project_input_files.os.rename',side_effect=rename):
            with self.assertRaises(OSError):
                self.bind()
        marker=read_document(self.marker)
        self.assertEqual('replacing',marker['state'])
        self.assertEqual('原未接受半成品',(self.data/marker['saved_relative']/'partial.txt').read_text())
        with self.assertRaisesRegex(ValueError,'交接中断'):
            self.bind()

    def test_expired_permission_preserves_workspace_and_removes_only_unpublished_staging(self) -> None:
        """实际发布前拒绝许可，旧工作区保留，未发布临时树收口。:return: None。"""
        proof=Mock(side_effect=ValueError('原有限证明已到期'))
        staging=self.data/'owned-staging'
        with self.assertRaisesRegex(ValueError,'到期'):
            self.bind(staging_root=staging,before_write=proof)
        self.assertEqual('原未接受半成品',(self.workspace/'partial.txt').read_text())
        self.assertFalse(self.marker.exists())
        self.assertEqual([],list(staging.glob('code-input-*')))

    def test_frozen_setup_rejects_links_and_conflicts_and_keeps_ready_identity(self) -> None:
        """固定业务材料只写原目标，冲突和链接留待核对，ready重复保持原摘要。:return: None。"""
        project=self.data/'project'
        project.mkdir()
        (project/'input.json').write_text('{"固定":"材料"}')
        setup=[{'source':'input.json','target':'app/input.json'}]
        marker=self.data/'markers/setup.json'
        result=materialize_input_files(project,self.workspace,setup,marker,{'task_id':1},self.objects,self.manifests)
        self.assertEqual('{"固定":"材料"}',(self.workspace/'app/input.json').read_text())
        self.assertEqual(result,materialize_input_files(project,self.workspace,setup,marker,{'task_id':1},self.objects,self.manifests))
        marker.unlink()
        (self.workspace/'app/input.json').write_text('已有不同内容')
        with self.assertRaisesRegex(ValueError,'不同内容'):
            materialize_input_files(project,self.workspace,setup,marker,{'task_id':1},self.objects,self.manifests)
        self.assertFalse(marker.exists())
        (self.workspace/'app/input.json').unlink()
        (self.workspace/'app/input.json').symlink_to(project/'input.json')
        with self.assertRaisesRegex(ValueError,'链接'):
            materialize_input_files(project,self.workspace,setup,marker,{'task_id':1},self.objects,self.manifests)

    def test_scenario_receipts_include_each_frozen_stage_and_resume_preserves_partial_work(self) -> None:
        """逐阶段保留完整对象，只复制已披露材料，同任务接续保留原现场。:return: None。"""
        project=self.data/'frozen-project'
        project.mkdir()
        for name in ('entry','task','branch','hidden'):
            (project/(name+'.txt')).write_text(name)
        setup=lambda name:[{'source':name+'.txt','target':'app/'+name+'.txt'}]
        scenario={'entries':[{'id':'normal','setup':setup('entry')}]}
        task={'setup':setup('task'),'branches':[{'id':'shown','setup':setup('branch')},
            {'id':'hidden','setup':setup('hidden')}]}
        selection={'scenario_id':2,'task_id':1,'entry_key':'normal','code':self.identity,'disclosures':['shown']}
        root=self.data/'node-environment/runtime/scenario-inputs'
        proof=Mock()
        def check(checksum):
            manifest=read_document(self.manifests/(checksum+'.json'))
            for item in manifest['files'].values():
                self.assertEqual(item['size'],(self.objects/item['digest'][:2]/item['digest']).stat().st_size)
        def prepare():
            return prepare_scenario_input_files(self.data,self.workspace,project,scenario,task,selection,self.objects,
                self.manifests,check,marker_root=root,staging_root=self.data/'node-environment/runtime/input-staging',
                before_write=proof)
        result=prepare()
        self.assertEqual(['entry','task','branch:shown'],list(result['stages']))
        self.assertEqual({'entry.txt','task.txt','branch.txt'},{path.name for path in (self.workspace/'app').iterdir()})
        self.assertEqual(result['input_checkpoint_digest'],snapshot_tree(self.workspace)['digest'])
        self.assertEqual('原未接受半成品',(self.data/result['code']['saved_relative']/'partial.txt').read_text())
        self.assertTrue(result['code']['saved_relative'].startswith('node-environment/runtime/input-staging/'))
        for record in result['stages'].values():
            check(record['input_checkpoint_digest'])
        calls=proof.call_count
        (self.workspace/'later-partial.txt').write_text('本任务尚未完成的修改')
        self.assertEqual(result,prepare())
        self.assertEqual(calls,proof.call_count)
        self.assertEqual('本任务尚未完成的修改',(self.workspace/'later-partial.txt').read_text())
        selection['disclosures'].append('missing')
        with self.assertRaisesRegex(ValueError,'披露选择'):
            prepare()
        self.assertEqual('本任务尚未完成的修改',(self.workspace/'later-partial.txt').read_text())
