"""平台手动发布入口的共同来源校验。"""
import os
import re

from system_update_contract import REPOSITORY


def validate_publish_source(build: dict | None = None) -> str:
    """在发布副作用前核对明确的入口、提交和批次。

    :param build: 可选同批构建清单；省略时仅执行入口预检。
    :return: 当前 Action 的唯一 ci 批次名；来源异常抛出 ValueError。
    """
    ref = os.environ.get('GITHUB_REF', '')
    run_id, attempt = os.environ.get('GITHUB_RUN_ID', ''), os.environ.get('GITHUB_RUN_ATTEMPT', '')
    revision = os.environ.get('GITHUB_SHA', '')
    expected = f'ci-{run_id}-{attempt}'
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or os.environ.get('V3_PUBLISH_CONFIRMED') != 'true'
            or ref not in ('refs/heads/v3', 'refs/heads/flower2api')
            or os.environ.get('GITHUB_REPOSITORY', '').lower() != REPOSITORY.lower()
            or os.environ.get('GITHUB_WORKFLOW_REF', '').lower()
                != f'{REPOSITORY}/.github/workflows/v3-release.yml@{ref}'.lower()
            or not re.fullmatch(r'[1-9][0-9]*', run_id) or not re.fullmatch(r'[1-9][0-9]*', attempt)
            or not re.fullmatch(r'[a-f0-9]{40}', revision)):
        raise ValueError('发布必须来自本仓 v3/flower2api 的已确认手动发布工作流')
    if build is not None:
        if build.get('release') != expected or build.get('parent_revision') != revision:
            raise ValueError('发布批次必须匹配当前 Action 的提交和 run/attempt')
        if build.get('dirty_worktree') is not False:
            raise ValueError('不能发布含未提交修改或来源未知的批次')
    return expected
