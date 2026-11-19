"""本机与节点共用的无凭据OAuth到期投影。"""
from __future__ import annotations

import json
import time
from pathlib import Path


def oauth_expiry_status(expires_at: object, *, token_state: str = 'valid', now: float | None = None) -> dict:
    """从受控到期值生成原公开四字段。

    :param expires_at: 毫秒到期值；缺失状态传None。
    :param token_state: 已核对的凭据内容状态。
    :param now: 测试或观察使用的UTC秒。
    :return: 仅到期值与状态，不含账号身份或凭据。
    """
    result={'oauth_expires_at_ms':None,'oauth_expires_at_iso':None,
        'oauth_expires_in_sec':None,'oauth_token_state':token_state}
    if token_state in ('missing','invalid','unknown'):
        return result
    if type(expires_at) not in (int,float) or not 0<expires_at<253402300800000:
        return {**result,'oauth_token_state':'invalid'}
    milliseconds=int(expires_at)
    remaining=int((milliseconds-int((time.time() if now is None else now)*1000))/1000)
    return {'oauth_expires_at_ms':milliseconds,
        'oauth_expires_at_iso':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(milliseconds/1000)),
        'oauth_expires_in_sec':remaining,
        'oauth_token_state':'expired' if remaining<=0 else 'expiring' if remaining<=600 else 'valid'}


def oauth_document_status(data: object, *, now: float | None = None) -> dict:
    """投影实际凭据文件，令牌仅参与存在性检查。

    :param data: 原当前HOME或本机profile文件解析值。
    :param now: 观察UTC秒。
    :return: 原公开四字段。
    """
    oauth=data.get('claudeAiOauth') if isinstance(data,dict) else None
    if not isinstance(oauth,dict):
        return oauth_expiry_status(None,token_state='invalid')
    if not isinstance(oauth.get('accessToken'),str) or not oauth['accessToken']:
        return oauth_expiry_status(None,token_state='missing')
    return oauth_expiry_status(oauth.get('expiresAt'),now=now)


def read_oauth_status(path: Path) -> dict:
    """读取原本机profile并复用原缺失与损坏语义。

    :param path: 已定位的本机凭据文件。
    :return: 无凭据公开状态。
    """
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return oauth_expiry_status(None,token_state='missing')
    except (OSError,ValueError):
        return oauth_expiry_status(None,token_state='invalid')
    return oauth_document_status(value)
