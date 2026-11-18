"""原固定授权文件的真实HTTPX/tar读取、完整未知字段与失败恢复。"""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from httpx import ByteStream, Client, HTTPStatusError, MockTransport, Response
from pydantic import ValidationError

from cluster_draft_login_contract import DraftLoginFiles, DraftLoginScope
from cluster_draft_login_files import read_draft_login_documents
from cluster_login_contract import login_authorization_sha256
from cluster_transfer import NodeArchiveTransfer


class DraftLoginDocumentsTests(unittest.TestCase):
    """逐文件校验与规范集合校验一起保护首次草稿完整镜像。"""

    def setUp(self) -> None:
        """建立包含大配置及未知字段的合成Node授权文件。:return: None。"""
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data=Path(temporary.name)
        self.scope=DraftLoginScope(operation_id='a'*32,node_key='b'*32,environment_id='e'*32,
            name='draft_only',draft_generation='d'*32,generation=2,source='login:'+'c'*12)
        self.documents={'.claude.json':{'userID':'synthetic-device','unknown':{'nested':['x'*90000]}},
            '.claude/.credentials.json':{'claudeAiOauth':{'accessToken':'synthetic-at','refreshToken':'synthetic-rt'},
                'unknown_credentials':{'preserved':True}},'.claude/settings.json':{'unknown_settings':{'preserved':True}}}
        self.raw={name:json.dumps(value,ensure_ascii=False).encode() for name,value in self.documents.items()}
        self.index=DraftLoginFiles(scope=self.scope,authorization_sha256=login_authorization_sha256(self.documents),
            files={name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in self.raw.items()})
        self.transfer=NodeArchiveTransfer(self.data/'docker.sock','1.45','flower2api-node-'+'a'*24)
        self.requests=[]
        self.fail_file=None

    def handler(self, request):
        """只响应本次Node操作的固定文件。:param request: 实际HTTPX请求。:return: 单文件Docker归档。"""
        prefix=f'/data/node-draft-logins/{self.scope.environment_id}/{self.scope.operation_id}/authorization/'
        path=request.url.params['path']
        self.assertTrue(path.startswith(prefix))
        filename=path.removeprefix(prefix)
        self.assertIn(filename,self.raw)
        self.requests.append(filename)
        if filename==self.fail_file:
            return Response(503)
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode='w') as archive:
            member=tarfile.TarInfo(filename.rsplit('/',1)[-1])
            member.size=len(self.raw[filename])
            archive.addfile(member,io.BytesIO(self.raw[filename]))
        return Response(200,stream=ByteStream(output.getvalue()))

    def connection(self):
        """保留真实HTTPX及tar解析，仅替换底层网络。:return: 客户端补丁。"""
        return patch.object(self.transfer,'_client',side_effect=lambda:Client(transport=MockTransport(self.handler),trust_env=False))

    def test_complete_large_json_and_unknown_fields_survive_fixed_private_transfer(self) -> None:
        """超过公开RPC大小的完整配置经单文件流读取，秘密只进入私有副本。:return: None。"""
        directory=self.data/'private'
        with self.connection():
            documents=read_draft_login_documents(self.transfer,self.index,directory)
            self.assertEqual(documents,read_draft_login_documents(self.transfer,self.index,directory))
        self.assertEqual(self.documents,documents)
        self.assertEqual(set(self.raw),set(self.requests))
        self.assertEqual(3,len(self.requests))
        self.assertNotIn('synthetic-rt',self.index.model_dump_json())
        for filename in self.raw:
            self.assertEqual(0o600,(directory/filename).stat().st_mode&0o777)

    def test_interrupted_second_file_reuses_only_verified_first_file_on_resume(self) -> None:
        """下载中断保留已核对副本，恢复继续原索引并重新读取失败文件。:return: None。"""
        directory=self.data/'private'
        self.fail_file='.claude/.credentials.json'
        with self.connection():
            with self.assertRaises(HTTPStatusError):
                read_draft_login_documents(self.transfer,self.index,directory)
            self.assertTrue((directory/'.claude.json').is_file())
            self.assertFalse((directory/self.fail_file).exists())
            self.fail_file=None
            self.assertEqual(self.documents,read_draft_login_documents(self.transfer,self.index,directory))
        self.assertEqual(1,self.requests.count('.claude.json'))
        self.assertEqual(2,self.requests.count('.claude/.credentials.json'))

    def test_wrong_collection_digest_and_replaced_cached_bytes_are_rejected(self) -> None:
        """单文件合法仍须匹配原集合摘要，本地副本变化也保持拒绝。:return: None。"""
        directory=self.data/'private'
        with self.connection():
            with self.assertRaisesRegex(ValueError,'集合摘要'):
                read_draft_login_documents(self.transfer,self.index.model_copy(update={'authorization_sha256':'f'*64}),directory)
            (directory/'.claude.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'原文件字节'):
                read_draft_login_documents(self.transfer,self.index,directory)

    def test_index_and_transfer_reject_extra_paths_or_unbounded_size(self) -> None:
        """原路径枚举和单文件上限均在网络读取前核验。:return: None。"""
        for changes in ({'../outside':{'sha256':'f'*64,'bytes':2}},
                {'.claude.json':{'sha256':'f'*64,'bytes':1024*1024+1}}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                DraftLoginFiles.model_validate({**self.index.model_dump(),'files':{**self.index.model_dump()['files'],**changes}})
        with self.assertRaises(ValueError):
            self.transfer.download_login_document(self.scope.environment_id,self.scope.operation_id,'../outside',self.data/'outside','f'*64,2)
