"""账号养号的持久空工作区适配，原生终端操作复用 PiTerminal。"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from account_runtime import AccountRuntime, atomic_json
from pi_terminal import PiTerminal
from project_library import read_document, safe_relative


@lru_cache(maxsize=1)
def _dialogue_parser():
    """复用已部署的主会话证据解析器，不复制阶段判断。:return: 原生对话解析模块。"""
    local = Path(__file__).resolve().parents[1] / 'images/worker/task_followups.py'
    path = local if local.is_file() else Path(__file__).with_name('task_followups.py')
    specification = spec_from_file_location('warmup_native_dialogue', path)
    if specification is None or specification.loader is None or not path.is_file():
        raise ValueError('原生会话证据解析器尚未部署')
    module = module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def matches_topic_input(actual: str, expected: str) -> bool:
    """逐字核对真实业务输入，只允许官方粘贴包装的无损还原。

    :param actual: 原生主会话中实际收到的用户文本。
    :param expected: 本轮冻结的题目或补充要求。
    :return: 是否为同一完整输入，不丢弃包装前后的额外指令。
    """
    return _dialogue_parser()._matches_input(actual, expected)


class WarmupTerminal(PiTerminal):
    """为一个冻结养号轮次保留独立工作区与原 Claude 会话。

    :param runtime: 固定账号运行环境。
    :param settings: CLI 设置回调。
    :param quota_context: 当前轮次的被动额度登记回调。
    """

    def __init__(self, runtime: AccountRuntime, settings, quota_context, quota_release=None, credentials=None,
                 driver: Path | None = None, *, quota_observation=None) -> None:
        """绑定账号养号运行依赖，不准备工程内容或启动模型。

        :param runtime: 固定账号运行环境。
        :param settings: CLI 设置回调。
        :param quota_context: 精确养号来源的被动额度回调。
        :param quota_release: 执行收口后的额度许可释放回调。
        :param credentials: 权威所有者同步凭据的回调。
        :param driver: 原生终端监督脚本。
        :param quota_observation: 原生认证或限额事实的回调。
        :return: None。
        """
        super().__init__(runtime, settings, quota_context, quota_release, credentials, driver,
            quota_observation=quota_observation, namespace='warmup')

    def _prepare_execution(self, root: Path, row: dict, account: dict, work: dict) -> tuple[Path, dict]:
        """新轮创建空工作区，恢复时核对原身份并保留全部已有成果。

        :param root: 已认领的账号持久目录。
        :param row: 当前账号环境。
        :param account: 当前账号。
        :param work: 冻结养号轮次及原会话标识。
        :return: 原工作区与空的附加环境；CLI 和系统 Python 沿用账号环境。
        """
        identifier = work['id']
        if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
            raise ValueError('养号轮次标识不合法')
        projects = root / 'projects'
        markers = root / 'runtime/warmup-workspaces'
        if projects.is_symlink() or markers.is_symlink():
            raise ValueError('养号工作区父目录不能是链接')
        workspace = projects / ('warmup-' + identifier)
        marker = markers / (identifier + '.json')
        identity = {'account_id': account['id'], 'environment_id': row['environment_id'],
            'round_id': identifier, 'session_id': work['session_id'],
            'account_identity': work.get('account_identity')}
        if marker.is_symlink() or workspace.is_symlink():
            raise ValueError('养号原工作区或身份凭据不能是链接')
        if marker.exists():
            if read_document(marker) != identity or not workspace.is_dir():
                raise ValueError('养号原工作区身份或会话证明不符')
            return workspace, {}
        if workspace.exists() or work.get('resume_required') or work.get('started_at'):
            raise ValueError('养号原工作区凭据缺失，保留现场等待核对')
        projects.mkdir(parents=True, exist_ok=True)
        workspace.mkdir(mode=0o755)
        os.chown(workspace, 1000, 1000, follow_symlinks=False)
        markers.mkdir(parents=True, exist_ok=True, mode=0o750)
        atomic_json(marker, identity)
        return workspace, {}

    def dialogue(self, work: dict) -> list[dict]:
        """从本轮真实主会话解析正常回复、父链和字节证据，不信任 Pi 提供的完成标志。

        :param work: 已登记账号、代次、原会话与运行定位的养号轮次。
        :return: 由共用解析器排序并标注 normal、synthetic、tool 和父链的记录。
        """
        info = json.loads(work['runtime_json'])
        job = self.runtime.job_for_container(info['token'])
        source = f"warmup:{work['id']}:{work['generation']}"
        if (job['account']['id'] != work['account_id'] or job['row']['account_id'] != work['account_id']
                or job['source'] != source or info.get('source') != source or job.get('heartbeat_failed')):
            raise ValueError('养号完成证据与账号或执行代次不符')
        root = self.runtime._root(job['row'])
        directory = self.runtime.data / safe_relative(info['native'])
        expected = root / 'home/.claude/projects' / job['cwd'].replace('/', '-')
        path = directory / (work['session_id'] + '.jsonl')
        if (directory != expected or directory.is_symlink() or path.is_symlink()
                or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError('养号完成证据缺少当前账号原生主会话')
        # CLI 尚未收到首题时不会创建 JSONL；空历史不构成完成证据，但应允许先观察再输入。
        if not path.exists():
            return []
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError('养号完成证据缺少当前账号原生主会话')
        return _dialogue_parser().read_dialogue(path)
