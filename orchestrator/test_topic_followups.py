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

    def test_weighted_prefix_distribution_and_missing_candidates(self):
        """枚举全部随机整数，精确验证次数概率及候选不足的合并。@return None。"""
        candidates = ['Add comparisons.', 'Export the comparison report.']
        for available, expected in ((2, [10,45,45]), (1, [10,90,0])):
            counts = [0,0,0]
            for draw in range(100):
                with patch.object(library.random, 'randrange', return_value=draw) as random:
                    selected = library.sample_followups(candidates[:available])
                    random.assert_called_once_with(100)
                self.assertEqual(candidates[:len(selected)], selected)
                counts[len(selected)] += 1
            self.assertEqual(expected, counts)
        with patch.object(library.random, 'randrange') as random:
            self.assertEqual([], library.sample_followups([]))
            random.assert_not_called()


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
        with patch.object(library.random, 'randrange', side_effect=[0,10,55]) as random:
            result = main.run_task(task_id)
        self.assertEqual(3, random.call_count)
        rows = [main.get_run(rid) for rid in result['run_ids']]
        self.assertEqual([[],['Compare groups.'],['Compare groups.','Export comparisons.']],
            [json.loads(row['followup_plan_json']) for row in rows])
        for row in rows:
            timing = library.decode_followup_timing(row['followup_timing_json'], len(row['followups']['messages']))
            self.assertEqual(2, timing['schema'])
            self.assertTrue(all(90 <= x <= 540 for x in timing['offsets_sec']))
        self.assertEqual(rows[-1]['followup_timing_json'], main.scheduler.submit.call_args.args[2]['followup_timing_json'])
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
        with patch.object(library.random,'randrange',return_value=55):
            main.Scheduler(Mock())._create_batch_task_and_run(batch,account,item,'aade1180bd9d')
            warmup = main.WarmupScheduler(Mock())._create_task_and_run(account,topic,'Build a local table.')
        self.assertIsNotNone(warmup)
        for rid in ('aade1180bd9d',warmup[0]):
            run = main.get_run(rid)
            self.assertEqual(['Compare groups.','Export comparisons.'],json.loads(run['followup_plan_json']))
            timing = library.decode_followup_timing(run['followup_timing_json'], 2)
            self.assertEqual(2, timing['schema'])
            self.assertEqual(2, len(timing['offsets_sec']))
            self.assertTrue(all(90 <= x <= 540 for x in timing['offsets_sec']))

    def test_timing_window_short_budget_and_legacy_null(self):
        """短预算不与收尾重叠，旧运行 NULL 保持原模式。@return None。"""
        for timeout in (60, 300, 1800, 10800):
            with patch.object(library.random,'sample',return_value=[timeout*3//10-1,timeout*3//10]):
                timing = library.decode_followup_timing(library.sample_followup_timing(['First.', 'Second.'], timeout, 600), 2)
            self.assertEqual(2, timing['schema'])
            self.assertLessEqual(timing['offsets_sec'][-1]+5, timeout - timing['wrapup_sec'])
        self.assertIsNone(library.decode_followup_timing(None, 2))
        with main.get_db() as conn:
            conn.execute("INSERT INTO tasks(id,topic_no,title,prompt,account_id) VALUES(99,1,'Legacy','Legacy.',1)")
            conn.execute("INSERT INTO runs(id,task_id,account_id,followup_plan_json) VALUES('legacy',99,1,'[\"Add a view.\"]')")
        main.init_db()
        self.assertIsNone(main.get_run('legacy')['followup_timing_json'])
        self.assertNotIn('mode', main.get_run('legacy')['followups'])

    def test_timed_public_progress_distinguishes_delivery_consumption_and_completion(self):
        """详情只从匹配的快照返回分离计数，不能用入队数冒充完成。@return None。"""
        workspace = main.WORKSPACES_DIR/'aade1180bd9d'
        workspace.mkdir(parents=True)
        project = self.root/'sessions'
        project.mkdir()
        state = workspace/'.bench-followups.json'
        timing = {'schema':1,'offsets_sec':[180,360],'timeout_sec':1800,'wrapup_sec':600}
        messages = ['Compare groups.', 'Export comparisons.']
        STAGES.process('init',state,project,'aade1180bd9d','Build a table.',messages,timing=timing)
        value = json.loads(state.read_text())
        value['started_at'] = 1000
        value['items'][0].update(status='queued',queue_entry='session.jsonl:2')
        value['items'][1].update(status='consumed',input_entry='session.jsonl:4')
        state.write_text(json.dumps(value))
        run = {'id':'aade1180bd9d','status':'running','followup_plan_json':library.encode_followups(messages),
            'followup_timing_json':json.dumps(timing)}
        result = main._public_followup_progress(run)
        self.assertEqual((2,1,0), (result['delivered'],result['consumed'],result['completed']))
        run['followup_timing_json'] = json.dumps(dict(timing,offsets_sec=[181,360]))
        self.assertEqual('invalid', main._public_followup_progress(run)['phase'])

    def test_topic_edit_missing_preserves_and_explicit_empty_clears(self):
        """旧编辑请求不会抹去补充，显式清空仍可用。@return None。"""
        main.update_topic(1,main.TopicIn(no=1,title='Renamed',description='Local example.',category='Examples'))
        self.assertEqual(2,len(main.list_topic_rows()[0]['followups']))
        main.update_topic(1,main.TopicIn(no=1,title='Renamed',description='Local example.',category='Examples',followups=[]))
        self.assertEqual([],main.list_topic_rows()[0]['followups'])

    def test_timed_missing_state_has_unknown_progress_except_queued(self):
        """未启动可以显示零投递，运行后的缺证据只能显示未知。@return None。"""
        timing = {'schema':1,'offsets_sec':[180,360],'timeout_sec':1800,'wrapup_sec':600}
        run = {'id':'aade1180bd9d','followup_plan_json':'["Compare groups.","Export comparisons."]',
            'followup_timing_json':json.dumps(timing)}
        queued = main._public_followup_progress(dict(run,status='queued'))
        self.assertEqual(('not_started',0,0,['scheduled','scheduled']),
            (queued['phase'],queued['delivered'],queued['consumed'],queued['items']))
        for status in ('running','quota_wait','success'):
            with self.subTest(status=status):
                result = main._public_followup_progress(dict(run,status=status))
                self.assertEqual('unknown',result['phase'])
                self.assertEqual([None,None,None],[result[key] for key in ('delivered','consumed','completed')])
                self.assertEqual(['unknown','unknown'],result['items'])

    def test_timed_public_progress_rejects_empty_evidence_or_missing_clock(self):
        """合法 JSON 的空证据和丢失时钟也不能冒充已投递或已完成。@return None。"""
        workspace = main.WORKSPACES_DIR/'aade1180bd9d'
        workspace.mkdir(parents=True)
        project = self.root/'sessions'
        project.mkdir()
        path = workspace/'.bench-followups.json'
        timing = {'schema':1,'offsets_sec':[180,360],'timeout_sec':1800,'wrapup_sec':600}
        messages = ['Compare groups.','Export comparisons.']
        STAGES.process('init',path,project,'aade1180bd9d','Build a table.',messages,timing=timing)
        base = json.loads(path.read_text())
        base.update(started_at=1000,phase='complete',completed_stages=3)
        for index,item in enumerate(base['items']):
            item.update(status='completed',input_entry=f'session.jsonl:{index}',reply_entry='session.jsonl:9')
        run = {'id':'aade1180bd9d','status':'running','followup_plan_json':library.encode_followups(messages),
            'followup_timing_json':json.dumps(timing)}
        for key in ('queue_entry','input_entry','reply_entry','started_at'):
            for value in ('','   ',None):
                with self.subTest(key=key,value=value):
                    state = json.loads(json.dumps(base))
                    if key == 'started_at':
                        state[key] = value
                    else:
                        state['items'][0][key] = value
                        if key == 'queue_entry':
                            state.update(phase='awaiting',completed_stages=1)
                            state['items'][0]['status'] = 'queued'
                    path.write_text(json.dumps(state))
                    result = main._public_followup_progress(run)
                    self.assertEqual('invalid',result['phase'])
                    self.assertEqual([None,None,None],[result[field] for field in ('delivered','consumed','completed')])

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


class TimedEvidenceTests(unittest.TestCase):
    """验证到点入队、合并消费、提前空闲及恢复不重发。"""

    setUp = StageEvidenceTests.setUp
    _append = StageEvidenceTests._append
    _classify = StageEvidenceTests._classify
    timing_schema = 1

    def _process(self, action='tick', now=1000, **kwargs):
        if self.session.exists():
            os.utime(self.session,(now-1,now-1))
        with patch.object(STAGES.time, 'time', return_value=now):
            return STAGES.process(action,self.state,self.project,'aade1180bd9d',self.initial,
                self.followups,idle_seconds=0,timing={'schema':self.timing_schema,'offsets_sec':[10,20],
                    'timeout_sec':100,'wrapup_sec':30},**kwargs)

    def _queue(self, text, **extra):
        with self.session.open('a') as stream:
            stream.write(json.dumps({'type':'queue-operation','operation':'enqueue',
                'sessionId':self.session.stem,'content':text,**extra})+'\n')

    def _start(self):
        self._process('init')
        self._append('user',self.initial,uuid='u0')
        self._process('start')

    def test_busy_delivery_does_not_wait_for_reply_and_one_reply_completes_both(self):
        """首轮没有结束也按时投递，两条消费后同一回复可完成全部。@return None。"""
        self._start()
        self._append('assistant','Working.',uuid='a0',parentUuid='u0',
            message={'role':'assistant','stop_reason':'tool_use','content':[{'type':'text','text':'Working.'}]})
        self.assertEqual('wait',self._process(now=1009)['action'])
        self.assertEqual('send',self._process(now=1010)['action'])
        self._queue(self.followups[0])
        self.assertEqual('wait',self._process(now=1011)['action'])
        self.assertEqual('queued',json.loads(self.state.read_text())['items'][0]['status'])
        self.assertEqual(1,self._classify()[0])
        self.assertEqual('send',self._process(now=1020)['action'])
        self._queue(self.followups[1])
        self._process('observe',now=1021)
        with self.assertRaisesRegex(ValueError,'原队列未消费'):
            self._process('init',now=1022,resume=True)
        self._append('assistant','Initial done.',uuid='a1',parentUuid='a0')
        self.assertEqual('wait',self._process(now=1023)['action'])
        self._append('user',self.followups[0],uuid='u1',parentUuid='a1')
        self._append('user',self.followups[1],uuid='u2',parentUuid='u1')
        self._process(now=1024)
        self.assertEqual(['consumed','consumed'],[x['status'] for x in json.loads(self.state.read_text())['items']])
        self._append('assistant','Both extensions done.',uuid='a2',parentUuid='u2')
        self.assertEqual('complete',self._process(now=1025)['action'])
        self.assertEqual('complete',self._process('init',now=1026,resume=True)['action'])

    def test_early_idle_waits_for_frozen_times_and_does_not_reset_clock(self):
        """提前结束首轮不能提前成功或提前投递，时钟与恢复一致。@return None。"""
        self._start()
        self._append('assistant','Initial complete.',uuid='a0',parentUuid='u0')
        self.assertEqual('wait',self._process('advance',now=1002)['action'])
        self._process('start',now=1008)
        self.assertEqual(1000,json.loads(self.state.read_text())['started_at'])
        self.assertEqual('send',self._process(now=1010)['action'])
        self.assertEqual('wait',self._process(now=1030)['action'])
        with self.assertRaisesRegex(ValueError,'投递结果不确定'):
            self._process('init',now=1030,resume=True)
        self._append('user',self.followups[0],uuid='u1',parentUuid='a0')
        self._process('init',now=1040,resume=True)
        self.assertEqual('send',self._process(now=1040)['action'])

    def test_no_next_never_sends_and_foreign_queue_does_not_acknowledge(self):
        """收尾与退出禁止新消息，异会话及元事件不能确认投递。@return None。"""
        self._start()
        self.assertEqual('wait',self._process(now=1020,allow_next=False)['action'])
        self.assertEqual('send',self._process(now=1020)['action'])
        self._queue(self.followups[0],sessionId='other')
        self._queue(self.followups[0],isMeta=True)
        self._queue(self.followups[0],sessionId='other',message={'role':'queue','content':self.followups[0]})
        self._process(now=1021)
        self.assertEqual('pending',json.loads(self.state.read_text())['items'][0]['status'])
        self.assertEqual('incomplete',self._process('advance',now=1022,allow_next=False)['action'])

    def test_timing_state_corruption_and_changed_plan_fail_closed(self):
        """时间快照和消息状态损坏不能重置或重抽。@return None。"""
        self._start()
        value = json.loads(self.state.read_text())
        for change in ({'schema':1},{'started_at':float('nan')},{'timing_digest':'changed'},
                {'items':[{'status':'completed'},{}]}):
            self.state.write_text(json.dumps(dict(value,**change)))
            with self.assertRaises(ValueError):
                self._process()

    def test_known_session_loss_never_changes_original_progress(self):
        """已消费或已完成后的主会话损坏必须拒绝，原阶段字节保持。@return None。"""
        self._start()
        self._process(now=1010)
        self._append('user',self.followups[0],uuid='u1',parentUuid='u0')
        self._process('observe',now=1011)
        consumed = (self.state.read_bytes(),self.session.read_bytes())
        self._process(now=1020)
        self._append('user',self.followups[1],uuid='u2',parentUuid='u1')
        self._append('assistant','All complete.',uuid='a2',parentUuid='u2')
        self.assertEqual('complete',self._process(now=1021)['action'])
        completed = (self.state.read_bytes(),self.session.read_bytes())
        for snapshot in (consumed,completed):
            for damage in ('deleted','truncated','replaced'):
                for action in ('init','observe','tick'):
                    with self.subTest(damage=damage,action=action):
                        self.state.write_bytes(snapshot[0])
                        self.session.write_bytes(snapshot[1])
                        if damage == 'deleted':
                            self.session.unlink()
                        else:
                            self.session.write_text('' if damage == 'truncated' else
                                json.dumps({'message':{'role':'user','content':'Another request.'}})+'\n')
                        with self.assertRaisesRegex(ValueError,'原主会话输入证据缺失'):
                            self._process(action,now=1030,resume=action=='init')
                        self.assertEqual(snapshot[0],self.state.read_bytes())

    def test_first_input_can_be_delayed_before_session_binding(self):
        """首次输入尚未落盘允许等待，不把正常启动判为证据丢失。@return None。"""
        self._process('init')
        self._process('start')
        self.assertEqual('wait',self._process(now=1010)['action'])
        self._append('user',self.initial,uuid='u0')
        self.assertEqual('send',self._process(now=1011)['action'])


    def test_out_of_order_reply_requires_current_business_parent_chain(self):
        """定时模式仍按父链确认乱序落盘，异根总结不能完成补充。@return None。"""
        self._start()
        self.assertEqual('send',self._process(now=1010)['action'])
        self._append('assistant','Comparison complete.',uuid='a1',parentUuid='u1')
        self._append('user',self.followups[0],uuid='u1',parentUuid='u0')
        self._process(now=1011)
        self.assertEqual('completed',json.loads(self.state.read_text())['items'][0]['status'])
        self.assertEqual('send',self._process(now=1020)['action'])
        self._append('user',self.followups[1],uuid='u2',parentUuid='a1')
        self._append('user','Unrelated request.',uuid='other')
        self._append('assistant','Unrelated summary.',uuid='other-a',parentUuid='other')
        self.assertEqual('wait',self._process(now=1021)['action'])
        self._append('assistant','Current delivery complete.',uuid='a2',parentUuid='u2')
        self.assertEqual('complete',self._process(now=1022)['action'])

    def test_cli_rejects_null_and_mismatched_execution_budget(self):
        """无效快照不得降级成旧模式，也不能用其它超时执行。@return None。"""
        for raw in ('null','[]','{"schema":1,"offsets_sec":[10,20],"timeout_sec":100,"wrapup_sec":30}'):
            result = subprocess.run([sys.executable,str(ROOT/'images/worker/task_followups.py'),'init',
                '--state',str(self.state),'--project',str(self.project)],capture_output=True,text=True,
                env={**os.environ,'RUN_ID':'aade1180bd9d','TASK_INITIAL_PROMPT':self.initial,
                    'TASK_FOLLOWUPS_JSON':json.dumps(self.followups),'TASK_FOLLOWUP_TIMING_JSON':raw,
                    'TIMEOUT_SEC':'1800','TIMEOUT_WRAPUP_SEC':'600'},timeout=10)
            self.assertEqual(1,result.returncode,result.stdout)
            self.assertFalse(self.state.exists())


class EarlierTimedEvidenceTests(TimedEvidenceTests):
    """对新版时间策略复用全部投递、消费、恢复及损坏证据场景。"""

    timing_schema = 2


class TimingCompatibilityTests(unittest.TestCase):
    """核对管理端与独立worker对新旧时间策略的校验一致。"""

    def test_versioned_boundaries_and_invalid_snapshots_match_worker(self):
        """新旧范围不能串用，未知版本和非法类型均在创建状态前拒绝。@return None。"""
        base = {'schema':2,'offsets_sec':[90,540],'timeout_sec':1800,'wrapup_sec':600}
        cases = [(base,True),(dict(base,schema=1,offsets_sec=[180,1080]),True),
            (dict(base,schema=1,offsets_sec=[860]),True),(dict(base,offsets_sec=[]),True)]
        for change in ({'schema':0},{'schema':3},{'schema':True},{'schema':2.0},{'schema':'2'},
                {'offsets_sec':[89,540]},{'offsets_sec':[90,541]},{'offsets_sec':[540,90]},
                {'offsets_sec':[90,90]},{'offsets_sec':[True,90]},{'offsets_sec':[90,90.0]},
                {'schema':1,'offsets_sec':[90,180]},{'schema':2,'offsets_sec':[860]},
                {'timeout_sec':True},{'timeout_sec':'1800'},{'wrapup_sec':float('nan')},
                {'wrapup_sec':1260}):
            cases.append((dict(base,**change),False))
        for index, (timing, accepted) in enumerate(cases):
            messages = ['Compare periods.','Export comparisons.'][:len(timing['offsets_sec'])]
            with self.subTest(timing=timing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                project = root/'project'
                project.mkdir()
                state = root/'state.json'
                if accepted:
                    self.assertEqual(timing,library.decode_followup_timing(json.dumps(timing),len(messages)))
                    STAGES.process('init',state,project,f'f0110b{index:06x}',
                        'Build a local table.',messages,timing=timing)
                    self.assertEqual(2,json.loads(state.read_text())['schema'])
                else:
                    with self.assertRaises(ValueError):
                        library.decode_followup_timing(json.dumps(timing),len(messages))
                    with self.assertRaises(ValueError):
                        STAGES.process('init',state,project,f'f0110b{index:06x}',
                            'Build a local table.',messages,timing=timing)
                    self.assertFalse(state.exists())

    def test_legacy_860_second_plan_resumes_without_changing_clock_or_digest(self):
        """复现线上旧860秒快照，升级恢复仍在原时刻投递。@return None。"""
        timing = {'schema':1,'offsets_sec':[860],'timeout_sec':1800,'wrapup_sec':600}
        initial = 'Build a local timeline.'
        messages = ['Add linked decisions and follow-up actions to timeline events.']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root/'project'
            project.mkdir()
            state = root/'state.json'
            session = project/'session.jsonl'
            with patch.object(STAGES.time,'time',return_value=1000):
                STAGES.process('init',state,project,'490232362377',initial,messages,timing=timing)
                session.write_text(json.dumps({'type':'user','uuid':'u0',
                    'message':{'role':'user','content':initial}})+'\n')
                STAGES.process('start',state,project,'490232362377',initial,messages,timing=timing)
            original = state.read_bytes()
            with patch.object(STAGES.time,'time',return_value=1859):
                result = STAGES.process('init',state,project,'490232362377',initial,messages,resume=True,timing=timing)
                self.assertEqual('wait',result['action'])
                self.assertEqual('wait',STAGES.process('tick',state,project,'490232362377',initial,messages,timing=timing)['action'])
            self.assertEqual(original,state.read_bytes())
            with patch.object(STAGES.time,'time',return_value=1860):
                self.assertEqual('send',STAGES.process('tick',state,project,'490232362377',initial,messages,timing=timing)['action'])
            self.assertEqual(1000,json.loads(state.read_text())['started_at'])


if __name__ == '__main__':
    unittest.main()
