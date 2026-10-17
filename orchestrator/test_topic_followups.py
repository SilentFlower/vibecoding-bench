"""递进题库、运行冻结和主会话阶段证据的回归测试。"""
import importlib.util
import json
import os
import re
import subprocess
import sys
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
        self.project = self.root / 'projects' / '-workspace'
        self.project.mkdir(parents=True)
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

    def _classify(self, baseline=None):
        source = (ROOT / 'images/worker/entrypoint.sh').read_text()
        classifier = re.search(r'^classify_claude_completion\(\) \{.*?^\}$', source, re.M | re.S).group(0)
        result = subprocess.run(['bash', '-c', classifier + '\nclassify_claude_completion 0'],
            env={**os.environ, 'CLAUDE_DIR': str(self.root), 'PYTHONPATH': str(ROOT / 'images/worker'),
                'COMPLETION_BASELINE': str(baseline or self.root / 'missing-baseline.json')},
            capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout.strip()

    def test_mixed_thinking_and_text_advance_without_accepting_tools_or_errors(self):
        """两种完成检测允许混合正文，工具和合成错误仍优先排除。@return None。"""
        # 两种检测使用同一主目录，避免测试各自造一套解析规则。
        self._process('init')
        self._append('user', self.initial)
        self._append('assistant', '', isApiErrorMessage=True, error='unknown',
            message={'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 'Not a delivery.'},
                {'type': 'text', 'text': 'API Error: 500'}]})
        self.assertEqual(5, self._classify()[0])
        self.assertEqual('wait', self._process()['action'])
        for extra, expected_code in (({'type': 'tool_use', 'id': 'local', 'name': 'Read', 'input': {}}, 1),
                ({'type': 'thinking', 'thinking': 'Local reasoning.'}, 0)):
            self._append('assistant', '', message={'role': 'assistant', 'stop_reason': 'end_turn',
                'content': [extra, {'type': 'text', 'text': 'Local delivery complete.'}]})
            self.assertEqual(expected_code, self._classify()[0])
            self.assertEqual('send' if expected_code == 0 else 'wait', self._process()['action'])

    def test_out_of_order_native_turns_keep_stage_cursors_and_shared_completion(self):
        """回复先落盘且经过附件父链时，0/1/2 阶段仍只推进一次。@return None。"""
        candidates = list(self.followups)
        for count in (0, 1, 2):
            self.state.unlink(missing_ok=True)
            self.session.unlink(missing_ok=True)
            self.followups = candidates[:count]
            self._process('init')
            for index, message in enumerate([self.initial] + self.followups):
                self._append('assistant', 'Done.', uuid=f'a{index}', parentUuid=f'm{index}',
                    timestamp=f'2026-10-17T02:02:0{index}.285Z')
                self._append('user', message, uuid=f'u{index}', parentUuid=f'a{index-1}' if index else None,
                    timestamp=f'2026-10-17T02:02:0{index}.201Z')
                self._append('attachment', 'Context.', uuid=f'm{index}', parentUuid=f'u{index}',
                    timestamp=f'2026-10-17T02:02:0{index}.231Z')
                self.assertEqual((0, 'complete'), self._classify())
                self.assertEqual('complete' if index == count else 'send', self._process()['action'])
                if index < count:
                    self.assertEqual('wait', self._process()['action'])
            self.assertEqual('complete', self._process('init', resume=True)['action'])

    def test_parent_chain_precedes_clock_and_old_attempt_baseline(self):
        """父链可纠正时钟倒序，既有游标仍排除旧回复。@return None。"""
        self._append('assistant', 'Old reply.', uuid='old', timestamp='2030-01-01T00:00:00Z')
        baseline = self.root / 'baseline.json'
        baseline.write_text(json.dumps({str(self.session): self.session.stat().st_size}))
        self._process('init')
        self.assertEqual(1, self._classify(baseline)[0])
        self._append('assistant', 'Current done.', uuid='a', parentUuid='u', timestamp='2026-10-17T02:00:00Z')
        self._append('user', self.initial, uuid='u', timestamp='2026-10-17T02:00:01Z')
        self.assertEqual((0, 'complete'), self._classify(baseline))
        self.assertEqual('send', self._process()['action'])

    def test_unrelated_root_reply_does_not_complete_current_stage(self):
        """其它根对话的正常回复不能被借来确认本阶段。@return None。"""
        self._process('init')
        self._append('user', self.initial, uuid='u')
        self._append('user', 'Another request.', uuid='other')
        self._append('assistant', 'Other reply.', uuid='a', parentUuid='other')
        self.assertEqual('wait', self._process()['action'])
        self.assertEqual('incomplete', self._process(allow_next=False)['action'])
        self.assertEqual(0, json.loads(self.state.read_text())['completed_stages'])

    def test_invalid_parent_cycles_and_duplicate_ids_are_rejected(self):
        """循环或重复标识不能被猜测为合法主会话顺序。@return None。"""
        for parent in ('a', 'u'):
            with self.subTest(parent=parent):
                self.state.unlink(missing_ok=True)
                self.session.unlink(missing_ok=True)
                self._process('init')
                self._append('user', self.initial, uuid='u', parentUuid=parent)
                self._append('assistant', 'Invalid reply.', uuid='a', parentUuid='u')
                with self.assertRaisesRegex(ValueError, '循环'):
                    self._process()
        self.session.write_text('')
        self._append('user', self.initial, uuid='u')
        self._append('assistant', 'Conflicting id.', uuid='u')
        with self.assertRaisesRegex(ValueError, '标识重复'):
            self._process()

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

    def test_native_paste_wrappers_confirm_initial_and_followup_inputs(self):
        """真实 CLI 的整体包装可确认输入，恢复及最终复核仍沿用原正文。@return None。"""
        self._process('init')
        for index, message in enumerate([self.initial] + self.followups):
            wrapped = f'\n\n<pasted_content id="316b-{index}">\n{message}\n</pasted_content id="316b-{index}">\n'
            fields = {'message': {'role': 'user', 'content': wrapped}} if index == 0 else {}
            self._append('user', wrapped, **fields)
            self.assertEqual('wait', self._process('init', resume=True)['action'])
            self._append('assistant', f'Completed wrapped stage {index}.')
            self.assertEqual('complete' if index == 2 else 'send', self._process()['action'])
        self.assertEqual('complete', self._process('init', resume=True)['action'])

    def test_wrapper_matching_rejects_extra_text_wrong_ids_and_partial_quotes(self):
        """只有完整同 ID 包装可匹配，任意引用和其它输入都不能推进阶段。@return None。"""
        wrapped = f'<pasted_content id="316b">\n{self.initial}\n</pasted_content id="316b">'
        for text in (wrapped + '\nAnother request.', 'Quoted requirement:\n' + wrapped,
                wrapped.replace('</pasted_content id="316b">', '</pasted_content id="other">'),
                wrapped.removesuffix('</pasted_content id="316b">'), wrapped + '\n' + wrapped,
                wrapped.replace('Build a local', 'Build a different local')):
            with self.subTest(text=text):
                self.state.unlink(missing_ok=True)
                self.session.unlink(missing_ok=True)
                self._process('init')
                self._append('user', text)
                self._append('assistant', 'Unrelated final reply.')
                self.assertEqual('wait', self._process()['action'])
                self.assertEqual(0, json.loads(self.state.read_text())['completed_stages'])

    def test_no_next_finishes_unknown_input_without_rewriting_progress(self):
        """收尾回复已经结束但输入未识别时返回未完成，不空等或伪造确认。@return None。"""
        self._process('init')
        self._append('user', 'Unrecognized transport: ' + self.initial)
        self._append('assistant', 'Wrap-up complete.')
        original = self.state.read_bytes()
        self.assertEqual('wait', self._process('observe', allow_next=False)['action'])
        self.assertEqual('incomplete', self._process(allow_next=False)['action'])
        self.assertEqual(original, self.state.read_bytes())

    def test_no_next_pending_delivery_keeps_uncertainty_and_never_resends(self):
        """禁止追加时缺少 pending 消费证据明确未完成，恢复仍按不确定投递拒绝。@return None。"""
        self._process('init')
        self._append('user', self.initial)
        self._append('assistant', 'Initial done.')
        self.assertEqual('send', self._process()['action'])
        original = self.state.read_bytes()
        self.assertEqual('incomplete', self._process(allow_next=False)['action'])
        self.assertEqual(original, self.state.read_bytes())
        with self.assertRaisesRegex(ValueError, '投递结果不确定'):
            self._process('init', resume=True)

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
