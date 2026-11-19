"""使用合成文本和真实文件校验AGY阶段预览及归属保护。"""
import hashlib
import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from agy_runtime.capture import BODY_LIMIT, RETENTION_MS, cleanup_snapshot_steps, read_snapshot, save_ingress, save_submission
from runtime_files import atomic_json


class AgyCaptureTests(unittest.TestCase):
    """独立阶段、重复秘密及文件边界验证。"""

    def setUp(self):
        """创建固定账号的隔离采集根。@return 无。"""
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.capture=self.root/'flows/api/agy-prepared'
        self.capture.mkdir(parents=True,mode=0o700);self.attempt=str(uuid.uuid4())
        self.decoded={'systemInstruction':{'parts':[{'text':'ABC 中文'}]},'contents':[{'parts':[{'text':'synthetic-at repeated-secret'}]}],'api_key':'repeated-secret'}
        self.submitted={'cascadeConfig':{'promptSections':[{'custom':{'content':'ΑΒС 中文'}}]},'synthetic':'synthetic-at repeated-secret'}

    def save(self):
        """保存真实序列化提交预览。@return 快照路径。"""
        save_submission(self.capture,7,self.attempt,self.decoded,self.submitted,'synthetic-at')
        return self.capture/'snapshots'/(self.attempt+'.json')

    def test_stages_redact_repeated_secrets_and_keep_source_digests(self):
        """原摘要来自原始表示，显示副本仅做脱敏。@return 无。"""
        self.save();value=read_snapshot(self.root,7,self.attempt)
        text=json.dumps(value)
        self.assertNotIn('synthetic-at',text);self.assertNotIn('repeated-secret',text)
        self.assertEqual(value['original_body_sha256'],hashlib.sha256(json.dumps(self.submitted,ensure_ascii=False).encode()).hexdigest())
        self.assertIn('ΑΒС',value['body']);self.assertIn('ABC',value['decoded_gemini']['body'])
        self.assertEqual(value['stages'][-1]['status'],'unavailable')

    def test_ingress_is_independent_and_has_shared_preview_budget(self):
        """原生与入口独立原子文件合并，UTF-8与总预算准确。@return 无。"""
        self.save()
        ingress={'source':'gateway_http_ingress','representation':'http_logical_bytes','body':'中'*300000,'headers':[['authorization','[redacted]']],
            'body_truncated':False,'headers_truncated':False,'original_body_bytes':900000,'original_body_sha256':'a'*64,'captured_at_ms':int(time.time()*1000)}
        save_ingress(self.capture,7,self.attempt,ingress)
        value=read_snapshot(self.root,7,self.attempt)
        self.assertTrue(value['ingress']['body_truncated'])
        self.assertLessEqual(sum(len(item['body'].encode()) for item in [value,value['decoded_gemini'],value['ingress']]),BODY_LIMIT)

    def test_file_and_identity_boundaries(self):
        """错账号、穿越、链接、共享权限和硬链接均拒绝。@return 无。"""
        path=self.save()
        with self.assertRaises(ValueError):read_snapshot(self.root,8,self.attempt)
        with self.assertRaises(ValueError):read_snapshot(self.root,7,'../other')
        path.chmod(0o644)
        with self.assertRaises(ValueError):read_snapshot(self.root,7,self.attempt)
        path.chmod(0o600);os.link(path,path.with_suffix('.hard'))
        with self.assertRaises(ValueError):read_snapshot(self.root,7,self.attempt)
        path.with_suffix('.hard').unlink();path.unlink();path.symlink_to(self.root/'missing')
        with self.assertRaises(OSError):read_snapshot(self.root,7,self.attempt)

    def test_expiry_corruption_and_unknown_source_are_visible(self):
        """有效归属先验期，坏表示不会被宣称已读取。@return 无。"""
        path=self.save();value=json.loads(path.read_text());value['captured_at_ms']=int(time.time()*1000)-RETENTION_MS-1;atomic_json(path,value)
        with self.assertRaises(TimeoutError):read_snapshot(self.root,7,self.attempt)
        value['captured_at_ms']=int(time.time()*1000);value['source']='unknown';atomic_json(path,value)
        with self.assertRaises(ValueError):read_snapshot(self.root,7,self.attempt)

    def test_nested_unknown_fields_and_fabricated_wire_are_rejected(self):
        """嵌套扩展不能越过管理白名单或虚构线字节。@return 无。"""
        path=self.save();original=json.loads(path.read_text())
        for section in ['decoded_gemini','system_prompt_policy','stages']:
            value=json.loads(json.dumps(original))
            if section=='system_prompt_policy':value[section]={'token':'synthetic-secret'}
            elif section=='stages':value[section][-1]['status']='complete'
            else:value[section]['secret']='synthetic-secret'
            atomic_json(path,value)
            with self.assertRaises(ValueError):read_snapshot(self.root,7,self.attempt)

    def test_quota_counts_both_views_and_preserves_active_raw_material(self):
        """共享容量会淘汰旧快照，活跃原始材料持续受保护。@return 无。"""
        path=self.save();size=path.stat().st_size
        ingress={'source':'gateway_http_ingress','representation':'http_logical_bytes','body':'{}','headers':[],
            'body_truncated':False,'headers_truncated':False,'original_body_bytes':2,'original_body_sha256':'a'*64}
        with patch('agy_runtime.capture.STORAGE_LIMIT',size+100):
            save_ingress(self.capture,7,self.attempt,ingress)
        self.assertFalse(path.exists());self.assertTrue((self.capture/'ingress/snapshots'/(self.attempt+'.json')).exists())
        active=self.capture/('a'*32);active.mkdir();(active/'raw').write_bytes(b'x'*4096)
        with patch('agy_runtime.capture.STORAGE_LIMIT',4096):
            with self.assertRaises(ValueError):self.save()
        self.assertEqual((active/'raw').stat().st_size,4096)

    def test_cleanup_checks_account_expiry_and_retired_worker(self):
        """按归属清理过期快照，保留活跃worker及其他账号。@return 无。"""
        path=self.save();value=json.loads(path.read_text());value['captured_at_ms']=int(time.time()*1000)-RETENTION_MS-1000;atomic_json(path,value)
        active=self.capture/('b'*32);active.mkdir();(active/'config.json').write_text(json.dumps({'account_id':7}))
        retired=self.capture/('c'*32);retired.mkdir();atomic_json(retired/'config.json',{'account_id':7});atomic_json(retired/'retired.json',{'retired_at':time.time()-RETENTION_MS/1000-10})
        self.assertEqual(sum(row['deleted'] for row in cleanup_snapshot_steps(self.root,8)),0)
        self.assertTrue(path.exists());self.assertTrue(retired.exists())
        self.assertEqual(sum(row['deleted'] for row in cleanup_snapshot_steps(self.root,7)),2)
        self.assertTrue(active.exists());self.assertFalse(path.exists());self.assertFalse(retired.exists())

    def test_symlink_in_shared_store_blocks_capture(self):
        """容量遍历拒绝链接，防止跨目录读取和淘汰。@return 无。"""
        (self.capture/'linked').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):self.save()


if __name__=='__main__':unittest.main()
