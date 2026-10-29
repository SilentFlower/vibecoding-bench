#!/usr/bin/env python3
"""在控制镜像中复用合成账号初始化，运行本批冻结真实内容。"""
import hashlib
import json
import os
import sys
from pathlib import Path

source_identity = json.loads(os.environ['VERIFY_SOURCE_IDENTITY'])
account_runtime_path = Path('/app/account_runtime.py')
actual_sha256 = hashlib.sha256(account_runtime_path.read_bytes()).hexdigest()
expected_sha256 = source_identity['account_runtime_overlay']['sha256']
if source_identity['account_runtime_overlay']['enabled']:
    assert expected_sha256 == actual_sha256, '本地 account_runtime.py 覆盖摘要不符，拒绝启动'
assert source_identity['base_release'] == os.environ['V3_RELEASE']
source_identity['actual_account_runtime_sha256'] = actual_sha256
source_identity['runtime_source_verified'] = True
Path('/verify/source-validation.json').write_text(json.dumps(source_identity, ensure_ascii=False, indent=2)+'\n')

sys.path.insert(0, '/source/deploy/v3')

import verify_local
import verify_project_scenarios
from formal_scenarios import verify_formal_scenarios


if __name__ == '__main__':
    verify_project_scenarios.verify_project_scenarios = verify_formal_scenarios
    verify_local.verify()
