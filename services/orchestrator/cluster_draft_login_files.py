"""中央受信草稿文件传输，逐文件及集合摘要核对后返回完整配置。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from cluster_draft_login_contract import DraftLoginFiles
from cluster_login_contract import login_authorization_sha256
from runtime_files import private_directory
from system_update_contract import safe_read, strict_json


def read_draft_login_documents(transfer, index: DraftLoginFiles, directory: Path) -> dict:
    """只沿冻结Node索引读取完整文件，恢复时复用已核对的原私有副本。

    :param transfer: 原SSH固定Docker归档读取器。
    :param index: 原Scope及固定文件索引。
    :param directory: 本次中央操作的专属私有目录。
    :return: 保留全部未知字段的JSON文件集合，任一摘要变化保持拒绝。
    """
    index=DraftLoginFiles.model_validate(index.model_dump())
    private_directory(directory)
    documents={}
    for name,metadata in index.files.items():
        path=directory/name
        private_directory(path.parent)
        if not path.exists() and not path.is_symlink():
            transfer.download_login_document(index.scope.environment_id,index.scope.operation_id,name,
                path,metadata.sha256,metadata.bytes)
        raw=safe_read(path,1024*1024,private=True)
        if len(raw)!=metadata.bytes or hashlib.sha256(raw).hexdigest()!=metadata.sha256:
            raise ValueError('中央草稿原文件字节或摘要已经变化')
        document=strict_json(raw,1024*1024)
        if not isinstance(document,dict):
            raise ValueError('原草稿授权文件必须为JSON对象')
        documents[name]=document
    if login_authorization_sha256(documents)!=index.authorization_sha256:
        raise ValueError('原草稿完整授权集合摘要不一致')
    return documents
