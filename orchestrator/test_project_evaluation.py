"""同模型评审协议与原生用量的确定性反例回归。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from project_evaluation import parse_review, review_package
from project_library import digest_json
from project_scenario_usage import aggregate_usage, source_usage


class ReviewProtocolTests(unittest.TestCase):
    """错误事实、身份、证据和缺失上下文不能被解析成通过。"""

    def setUp(self) -> None:
        """准备冻结对话及逐项判定。@return None。"""
        conversation = [{'role':'user','content':'请根据业务约束给出可行方案。'}]
        rubric = {'criteria':[{'id':'constraint','requirement':'满足业务约束','evidence':['source.py:1']}]}
        answer = '方案可行且满足约束。'
        job = {'job_id':1,'task_id':2,'turn_no':1,'response_digest':digest_json(answer),
            'basis_digest':digest_json(rubric),'input_digest':digest_json(conversation)}
        self.package = review_package(job,{'id':'Q1','kind':'plan','allowed_paths':[],
            'outcomes':['feasible'],'branches':[{'id':'context','when':'必要信息不足'}]},
            rubric,answer,conversation[0]['content'],{'status':'passed'},{'source.py:1':'1: VALUE = 1'},conversation=conversation)
        self.result = {key:self.package[key] for key in ('job_id','task_id','turn_no','response_digest','basis_digest')}
        self.result.update(decision='pass',outcome='feasible',branch_id=None,
            criteria=[{'id':'constraint','status':'satisfied','reason':'符合固定约束','evidence':['source.py:1']}],feedback_codes=[])

    def test_valid_pass_and_uncertain_have_distinct_semantics(self) -> None:
        """合法短答案通过；uncertain有效但不声明业务成功。@return None。"""
        self.assertEqual('pass',parse_review(json.dumps(self.result),self.package)['decision'])
        self.result.update(decision='uncertain',outcome=None)
        self.result['criteria'][0].update(status='unknown',evidence=[])
        self.assertEqual('uncertain',parse_review(json.dumps(self.result),self.package)['decision'])

    def test_wrong_identity_duplicates_unknown_evidence_and_program_failure_rejected(self) -> None:
        """不能靠回显错误身份、重复字段或伪造证据覆盖程序事实。@return None。"""
        for change in ('identity','criterion','evidence','program','contradiction','feedback'):
            result,package = copy.deepcopy(self.result),copy.deepcopy(self.package)
            if change=='identity':
                result['task_id']=99
            elif change=='criterion':
                result['criteria'].append(copy.deepcopy(result['criteria'][0]))
            elif change=='evidence':
                result['criteria'][0]['evidence']=['not-provided.py:1']
            elif change=='program':
                package['native_result']['status']='failed'
            elif change=='contradiction':
                result['criteria'][0]['status']='violated'
            else:
                result['feedback_codes']=['invented-feedback']
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse_review(json.dumps(result),package)
        raw=json.dumps(self.result).replace('"job_id": 1','"job_id": 1, "job_id": 1')
        with self.assertRaises(ValueError):
            parse_review(raw,self.package)

    def test_disclosure_is_fixed_and_input_digest_is_verified(self) -> None:
        """只能选择现有固定分支，完整业务对话不能被替换。@return None。"""
        self.result.update(decision='disclose',outcome=None,branch_id='context')
        self.assertEqual('context',parse_review(json.dumps(self.result),self.package)['branch_id'])
        self.result['branch_id']='freeform'
        with self.assertRaises(ValueError):
            parse_review(json.dumps(self.result),self.package)
        with self.assertRaises(ValueError):
            review_package(self.package,{'id':'Q1','kind':'plan','allowed_paths':[],'outcomes':['feasible']},
                self.package['rubric'],self.package['answer'],'已替换问题',{'status':'passed'},{},conversation=[])

    def test_candidate_evidence_requires_explicit_permission_and_actual_file(self) -> None:
        """交付文件引用须由判定项授权且实际存在，不能任意编路径。@return None。"""
        self.package['candidate_files']={'app/example.py':{'text':'VALUE = 1','digest':'a'*64,'size':9,'binary':False}}
        self.result['criteria'][0]['evidence']=['candidate:app/example.py']
        with self.assertRaises(ValueError):
            parse_review(json.dumps(self.result),self.package)
        self.package['rubric']['criteria'][0]['allow_candidate_evidence']=True
        self.assertEqual('pass',parse_review(json.dumps(self.result),self.package)['decision'])
        self.result['criteria'][0]['evidence']=['candidate:app/not-provided.py']
        with self.assertRaises(ValueError):
            parse_review(json.dumps(self.result),self.package)


class ScenarioUsageTests(unittest.TestCase):
    """逐来源去重、部分字段和未知区间不被重复计费或补零。"""

    def test_duplicate_streaming_responses_preserve_known_cache_fields(self) -> None:
        """同一响应后续增量缺字段时仍保留已知计数，只计一次请求。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            records=[{'type':'assistant','message':{'id':'same','role':'assistant','usage':usage}} for usage in (
                {'input_tokens':7,'output_tokens':1,'cache_read_input_tokens':20,'cache_creation_input_tokens':3},
                {'output_tokens':11})]
            records.append({'type':'assistant','isSidechain':True,'message':{'id':'side','role':'assistant','usage':{'output_tokens':999}}})
            path=directory/'session.jsonl'
            path.write_text(''.join(json.dumps(record)+'\n' for record in records))
            source=source_usage(directory,{}, {path.name:path.stat().st_size},'session')
            usage=aggregate_usage([source,source])
            self.assertEqual((7,11,20,3,1),(usage['input_tokens'],usage['output_tokens'],usage['cache_read_input_tokens'],
                usage['cache_creation_input_tokens'],usage['requests']))
            self.assertTrue(usage['complete'])
            partial=aggregate_usage([source,source_usage(directory,None,None,'session')])
            self.assertEqual(11,partial['output_tokens'])
            self.assertFalse(partial['complete'])

    def test_unanswered_or_truncated_source_stays_unknown(self) -> None:
        """只有已消费问题或截断边界时，未知token不是零。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            path=directory/'session.jsonl'
            path.write_text(json.dumps({'type':'user','message':{'role':'user','content':'尚未回答'}})+'\n')
            for size in (path.stat().st_size,path.stat().st_size-1):
                source=source_usage(directory,{}, {path.name:size},'session')
                usage=aggregate_usage([source])
                self.assertIsNone(usage['input_tokens'])
                self.assertIsNone(usage['requests'])
                self.assertFalse(usage['complete'])
