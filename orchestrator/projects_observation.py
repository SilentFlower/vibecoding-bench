"""仅归一化已确认的 CLI 显示噪声，真实画面与业务决定仍保留给 Pi。"""
from __future__ import annotations

import re


_PROGRESS = re.compile(r'^[✢✳✶✻✽·*] [A-Za-z][A-Za-z -]*…(?:\s*\([^\n]*\))?\s*$')
_SELECTED_OPTION = re.compile(r'^\s*[❯>]\s+\d+[.)]\s+\S')
_OTHER_OPTION = re.compile(r'^\s+\d+[.)]\s+\S')
_TIP = 'Tip: Use /btw to ask a quick side question without interrupting Claude\'s current work'


def screen_content(screen: str) -> str:
    """移除固定 CLI 已实测的忙碌显示行，供唤醒比较使用。

    :param screen: tmux 原始画面，调用者仍保存完整正文。
    :return: 仅用于变化检测的有效内容，不用于还原画面或判断业务完成。
    """
    lines = []
    for line in screen.splitlines():
        # 只合并带标准进度元数据的整行，不能把正文中的数字或菜单选项抹掉。
        if _PROGRESS.fullmatch(line):
            continue
        if line.strip().removeprefix('⎿').strip() == _TIP:
            continue
        if line.strip():
            lines.append(line.rstrip())
    return '\n'.join(lines)


def screen_busy(screen: str) -> bool:
    """检测固定 CLI 的前台忙碌指示，不解释业务正文。

    :param screen: tmux 原始画面。
    :return: 是否仍显示已核实的工作动画行。
    """
    return any(_PROGRESS.fullmatch(line) for line in screen.splitlines())


def screen_menu(screen: str) -> bool:
    """识别需要 Pi 阅读的编号选择界面，不推断答案。

    :param screen: tmux 原始画面。
    :return: 是否同时存在选中指针及其他编号选项。
    """
    lines = screen.splitlines()
    return any(_SELECTED_OPTION.match(line) for line in lines) and any(_OTHER_OPTION.match(line) for line in lines)
