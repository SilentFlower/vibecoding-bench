"""递进题库、运行冻结和主会话阶段证据的回归测试。"""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main
import topic_library as library

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('task_followups', ROOT / 'images/worker/task_followups.py')
STAGES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGES)


class TopicFollowupTests(unittest.TestCase):
    """验证题库消息与有限随机前缀。"""

    def test_library_has_self_starting_distinct_business_extensions(self):
        """所有题目可自启动，补充与初始分离。@return None。"""
        topics = library.parse_topics(ROOT / 'topics.md')
        library.validate_topics(topics)
        messages = [message for topic in topics for message in topic.followups]
        self.assertEqual(1200, len(messages))
        self.assertEqual(1200, len(set(messages)))
        for topic in topics:
            self.assertIn('Start immediately in an empty workspace', topic.description)
            self.assertIn('synthetic', topic.description)
            self.assertEqual(2, len(topic.followups))
            self.assertTrue(all(message not in topic.description for message in topic.followups))

    def test_parser_rejects_orphan_duplicate_and_out_of_order_followups(self):
        """错误子行不能悄悄丢失。@return None。"""
        for text in ('  - Follow-up 1: Add a list.',
                '- [ ] 1. **Example**: Base.\n  - Follow-up 2: Add a list.',
                '- [ ] 1. **Example**: Base.\n  - Follow-up 1: Add a list.\n  - Follow-up 1: Add a view.',
                '- [ ] 1. **Example**: Base.\n  - Follow-up 3: Add a list.'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'topics.md'
                path.write_text(text)
                with self.assertRaises(ValueError):
                    library.parse_topics(path)

    def test_message_validation_and_legacy_defaults(self):
        """坏计划明确拒绝，旧字段缺失兼容零补充。@return None。"""
        self.assertEqual([], library.decode_followups(None))
        for raw in ('null', '{}', '[1]', '[""]', '["中文"]', '["a","a"]', '["a","b","c"]', '["\\u001b"]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                library.decode_followups(raw)
        candidates = ['Add comparisons.', 'Export the comparison report.']
        escaped = ['"' * 8000, '\\' * 8000]
        self.assertEqual(escaped, library.decode_followups(library.encode_followups(escaped)))
        with self.assertRaises(ValueError):
            library.validate_followups(['Invalid\x7finput'])
        for count in (0, 1, 2):
            with patch.object(library.random, 'randint', return_value=count) as random:
                self.assertEqual(candidates[:count], library.sample_followups(candidates))
                random.assert_called_once_with(0, 2)


class StageEvidenceTests(unittest.TestCase):
    """核验主会话输入、正常回复及恢复的不确定窗口。"""

    def setUp(self):
        """建立每次测试独享的状态和会话目录。@return None。"""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.state = self.root / 'followups.json'
        self.session = self.project / 'session.jsonl'
        self.initial = 'Build a local lead score table.\nUse generated sample rows.'
        self.followups = ['Compare two date windows.', 'Export the comparison report.']

    def _process(self, action='advance', **kwargs):
        return STAGES.process(action, self.state, self.project, 'aade1180bd9d',
            self.initial, self.followups, idle_seconds=0, **kwargs)

    def _append(self, role, text, **fields):
        entry = {'type': role, 'message': {'role': role, 'content': [{'type': 'text', 'text': text}]}, **fields}
        with self.session.open('a') as stream:
            stream.write(json.dumps(entry) + '\n')

    def test_zero_one_two_plans_require_all_native_turns(self):
        """只在最后一个已选阶段结束后成功，旧回复不得连发补充。@return None。"""
        for count in (0, 1, 2):
            with self.subTest(count=count):
                self.state.unlink(missing_ok=True)
                self.session.unlink(missing_ok=True)
                self.followups = ['Compare two date windows.', 'Export the comparison report.'][:count]
                self._process('init')
                for index, message in enumerate([self.initial] + self.followups):
                    self.assertEqual('wait', self._process()['action'])
                    self._append('user', message)
                    self.assertEqual('wait', self._process()['action'])
                    self._append('assistant', f'Completed stage {index}.')
                    result = self._process()
                    self.assertEqual('complete' if index == count else 'send', result['action'])
                    if index < count:
                        self.assertEqual(self.followups[index], result['text'])
                        self.assertEqual('wait', self._process()['action'])
                self.assertEqual('complete', self._process('init', resume=True)['action'])

    def test_pending_delivery_is_never_resent_after_uncertain_restart(self):
        """写前 pending 窗口没有主输入时明确失败。@return None。"""
        self._process('init')
        self._append('user', self.initial)
        self._append('assistant', 'First delivery complete.')
        self.assertEqual('send', self._process()['action'])
        original = self.state.read_bytes()
        with self.assertRaisesRegex(ValueError, '投递结果不确定'):
            self._process('init', resume=True)
        self.assertEqual(original, self.state.read_bytes())
        self._append('user', self.followups[0])
        self.assertEqual('wait', self._process('init', resume=True)['action'])
        self._append('assistant', 'Comparison complete.')
        self.assertEqual('send', self._process()['action'])

    def test_existing_history_meta_sidechains_and_synthetic_replies_cannot_finish(self):
        """旧历史、元消息、子会话与错误回复均不能完成阶段。@return None。"""
        self._append('user', self.initial)
        self._append('assistant', 'Old summary.')
        self._process('init')
        self.assertEqual('wait', self._process()['action'])
        self._append('user', self.initial, isMeta=True)
        self._append('assistant', 'Unrelated summary.')
        self.assertEqual('wait', self._process()['action'])
        self._append('user', self.initial)
        for fields in ({'isSidechain': True}, {'isMeta': True}, {'isApiErrorMessage': True}):
            self._append('assistant', 'Not a final response.', **fields)
            self.assertEqual('wait', self._process()['action'])
        self._append('assistant', 'Real first-stage delivery.')
        self.assertEqual('send', self._process()['action'])

    def test_plan_corruption_and_state_links_are_rejected(self):
        """错计划、非法 schema 与链接状态不能静默重置。@return None。"""
        self._process('init')
        self.followups[0] = 'Changed requirement.'
        with self.assertRaises(ValueError):
            self._process()
        self.followups[0] = 'Compare two date windows.'
        value = json.loads(self.state.read_text())
        value['schema'] = True
        self.state.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self._process()
        target = self.root / 'target.json'
        self.state.rename(target)
        self.state.symlink_to(target)
        with self.assertRaises(OSError):
            self._process()

    def test_wrapup_and_truncation_cannot_skip_remaining_requirements(self):
        """收尾不追加新需求，也不能把旧完成回复当全部完成。@return None。"""
        self._process('init')
        self._append('user', self.initial)
        self._append('assistant', 'Initial done.')
        self.assertEqual('incomplete', self._process(allow_next=False)['action'])
        self.assertEqual('send', self._process()['action'])
        self.session.write_text('')
        with self.assertRaisesRegex(ValueError, '截断'):
            self._process()


class FollowupPersistenceTests(unittest.TestCase):
    """通过真实 SQLite 和入口函数检查冻结与兼容。"""

    def setUp(self):
        """准备独立数据库，不启动调度线程。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in {'DB_PATH': self.root/'db.sqlite', 'TOPICS_FILE': self.root/'missing.md',
                'WORKSPACES_DIR': self.root/'workspaces', 'scheduler': Mock(), 'account_runtime': None}.items():
            patcher = patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        main.init_db()
        with main.get_db() as conn:
            conn.execute("INSERT INTO accounts(name,profile_path,cc2api_account_id,warmup_enabled) VALUES('example','none',7,1)")
            conn.execute("INSERT INTO topics(no,title,description,category,followups_json) VALUES(1,'Example','Build a local table.','Command-Line Tools',?)",
                (library.encode_followups(['Compare groups.', 'Export comparisons.']),))

    def test_ordinary_snapshot_randomization_and_custom_canonical_compatibility(self):
        """候选冻结后改题不影响 run，三个随机前缀分别持久化。@return None。"""
        task_id = main.create_task(main.TaskIn(topic_no=1, account_id=1, repeat_n=3))['id']
        with main.get_db() as conn:
            conn.execute("UPDATE topics SET followups_json='[]'")
        with patch.object(library.random, 'randint', side_effect=[0,1,2]) as random:
            result = main.run_task(task_id)
        self.assertEqual(3, random.call_count)
        rows = [main.get_run(rid) for rid in result['run_ids']]
        self.assertEqual([[],['Compare groups.'],['Compare groups.','Export comparisons.']],
            [json.loads(row['followup_plan_json']) for row in rows])
        for custom, mode in ((None,'canonical'),('Use exactly this prompt.','natural'),('   ','natural')):
            tid = main.create_task(main.TaskIn(topic_no=1,account_id=1,prompt=custom,prompt_mode=mode))['id']
            with main.get_db() as conn:
                self.assertEqual('[]', conn.execute('SELECT followup_candidates_json FROM tasks WHERE id=?',(tid,)).fetchone()[0])

    def test_batch_and_warmup_freeze_selected_plan(self):
        """批次排队和养号创建采用同一正文事实来源。@return None。"""
        batch_id = main.create_task_batch(main.BatchIn(account_id=1,topic_ids=[1]))['id']
        with main.get_db() as conn:
            batch = dict(conn.execute('SELECT * FROM task_batches WHERE id=?',(batch_id,)).fetchone())
            item = dict(conn.execute('SELECT * FROM task_batch_items WHERE batch_id=?',(batch_id,)).fetchone())
            account = dict(conn.execute('SELECT * FROM accounts WHERE id=1').fetchone())
            topic = dict(conn.execute('SELECT * FROM topics WHERE id=1').fetchone())
            conn.execute("UPDATE topics SET followups_json='[]'")
        item.update(topic_no=topic['no'],title=topic['title'])
        with patch.object(library.random,'randint',return_value=2):
            main.Scheduler(Mock())._create_batch_task_and_run(batch,account,item,'aade1180bd9d')
            warmup = main.WarmupScheduler(Mock())._create_task_and_run(account,topic,'Build a local table.')
        self.assertIsNotNone(warmup)
        for rid in ('aade1180bd9d',warmup[0]):
            self.assertEqual(['Compare groups.','Export comparisons.'],json.loads(main.get_run(rid)['followup_plan_json']))

    def test_topic_edit_missing_preserves_and_explicit_empty_clears(self):
        """旧编辑请求不会抹去补充，显式清空仍可用。@return None。"""
        main.update_topic(1,main.TopicIn(no=1,title='Renamed',description='Local example.',category='Examples'))
        self.assertEqual(2,len(main.list_topic_rows()[0]['followups']))
        main.update_topic(1,main.TopicIn(no=1,title='Renamed',description='Local example.',category='Examples',followups=[]))
        self.assertEqual([],main.list_topic_rows()[0]['followups'])

    def test_public_progress_never_trusts_wrong_run_state(self):
        """阶段文件归属错误应显示无效，不能冒充完成。@return None。"""
        workspace = main.WORKSPACES_DIR/'aade1180bd9d'
        workspace.mkdir(parents=True)
        state = workspace/'.bench-followups.json'
        state.write_text(json.dumps({'schema':1,'run_id':'bad','phase':'complete','completed_stages':2}))
        state.chmod(0o600)
        result = main._public_followup_progress({'id':'aade1180bd9d','status':'running','followup_plan_json':'["Add a view."]'})
        self.assertEqual('invalid',result['phase'])
        self.assertIsNone(result['completed'])


if __name__ == '__main__':
    unittest.main()
