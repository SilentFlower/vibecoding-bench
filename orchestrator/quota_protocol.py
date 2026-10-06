"""被动额度协议的纯函数；sidecar 构建副本由 sync-quota-protocol.py 同步。"""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any


WINDOWS = {"five_hour": "5h", "seven_day": "7d", "seven_day_fable": "7d_oi"}


def quota_timestamp(value: Any) -> float | None:
    """
    解析秒、毫秒或 RFC3339 时间。

    :param value: 上游时间字段
    :return: 有限 UTC 秒数，非法值返回 None
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
        if result > 100_000_000_000:
            result /= 1000
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            result = parsed.timestamp()
        except (ValueError, OverflowError, OSError):
            return None
    return result if isfinite(result) and result > 0 else None


def quota_observation(headers: dict, status: int, now: float) -> dict:
    """
    从白名单响应头解析额度观察，拒绝事实不依赖完整利用率。

    :param headers: 上游响应头
    :param status: 上游 HTTP 状态
    :param now: 收到响应头的 UTC 秒数
    :return: 包含窗口与允许事实的观察对象
    """
    headers = {str(key).lower(): str(value).strip() for key, value in headers.items()}
    windows = {}
    for key, name in WINDOWS.items():
        prefix = f"anthropic-ratelimit-unified-{name}-"
        window_status = headers.get(prefix + "status", "").lower()
        try:
            utilization = float(headers.get(prefix + "utilization", ""))
            if not isfinite(utilization) or utilization < 0:
                utilization = None
        except ValueError:
            utilization = None
        exceeded = headers.get(prefix + "surpassed-threshold", "").lower()
        try:
            exceeded_number = float(exceeded)
            surpassed = isfinite(exceeded_number) and exceeded_number > 0
        except ValueError:
            surpassed = exceeded == "true"
        rejected = status == 429 and (
            window_status == "rejected"
            or (window_status != "allowed" and (
                surpassed or (utilization is not None and utilization >= 1 - 1e-9)
            ))
        )
        reset = quota_timestamp(headers.get(prefix + "reset"))
        horizon = 6 * 3600 if name == "5h" else 8 * 86400
        if reset is not None and not now < reset <= now + horizon:
            reset = None
        if not rejected and (utilization is None or reset is None):
            continue
        window = {"observed_at": now, "rejected": rejected, "exhausted": rejected}
        if reset is not None:
            window["reset_at"] = reset
            window["resets_at"] = datetime.fromtimestamp(reset, timezone.utc).isoformat()
        if utilization is not None:
            window["utilization"] = utilization * 100
            # 429 中明确 allowed 的其它窗口不能被高位残留误判为耗尽。
            if status != 429 and utilization >= 1 - 1e-9 and reset is not None:
                window["exhausted"] = True
        windows[key] = window
    retry_until = None
    if any(window["rejected"] for window in windows.values()):
        try:
            delay = float(headers.get("retry-after", ""))
            if isfinite(delay) and 0 < delay <= 8 * 86400:
                retry_until = now + delay
        except ValueError:
            retry_until = quota_timestamp(headers.get("retry-after"))
            if retry_until is not None and not now < retry_until <= now + 8 * 86400:
                retry_until = None
    return {"windows": windows, "observed_at": now,
            "allowed": 200 <= status < 300, "retry_until": retry_until}


def merge_quota_observation(existing: dict, incoming: dict) -> dict:
    """
    按窗口合并观察，保留缺失字段并排除跨周期残留与乱序样本。

    :param existing: 已持久化额度对象
    :param incoming: 本次真实响应观察
    :return: 合并后的新对象，不修改输入
    """
    result = dict(existing)
    windows = {key: dict(value) for key, value in existing.get("windows", {}).items()
               if isinstance(value, dict)}
    observed = float(incoming.get("observed_at") or 0)
    for key, value in incoming.get("windows", {}).items():
        if key not in (*WINDOWS, "unknown") or not isinstance(value, dict):
            continue
        previous = windows.get(key, {})
        window_observed = float(value.get("observed_at") or observed)
        # sidecar 的本地缓存可能包含多个时刻的窗口，不能用另一个窗口的新时间覆盖旧拒绝。
        previous_observed = float(previous.get("observed_at") or 0)
        if (window_observed < previous_observed
                or (window_observed == previous_observed and previous.get("rejected")
                    and not value.get("rejected"))):
            continue
        normalized = {**previous, **value}
        old_reset = quota_timestamp(previous.get("reset_at"))
        new_reset = quota_timestamp(value.get("reset_at"))
        # 成功样本证明进入下一周期；旧/新均为高位时不能把旧周期用量带过去。
        if (not value.get("rejected") and old_reset is not None and new_reset is not None
                and old_reset <= window_observed < new_reset and new_reset > old_reset
                and float(previous.get("utilization") or 0) >= 97
                and float(value.get("utilization") or 0) >= 97):
            normalized.update(utilization=0.0, exhausted=False)
        if value.get("rejected") and new_reset is None and (
            old_reset is None or old_reset <= window_observed
        ):
            normalized.pop("reset_at", None)
            normalized.pop("resets_at", None)
        windows[key] = normalized
    result["windows"] = windows
    result["observed_at"] = max(float(existing.get("observed_at") or 0), observed)
    if incoming.get("retry_until") is not None:
        result["retry_until"] = max(float(existing.get("retry_until") or 0),
                                    float(incoming["retry_until"]))
    return result


def quota_decision(state: dict, now: float) -> dict:
    """
    计算通用窗口等待和到期恢复机会，不把到期缓存伪装成实时可用额度。

    :param state: 已合并的账号额度对象
    :param now: 当前 UTC 秒数
    :return: blocked、exhausted、resume_at、retry_ready 与中文原因
    """
    exhausted = []
    deadlines = []
    unknown = False
    for key in ("five_hour", "seven_day", "unknown"):
        window = state.get("windows", {}).get(key, {})
        if not window.get("exhausted"):
            continue
        exhausted.append(key)
        reset = quota_timestamp(window.get("reset_at"))
        if reset is None:
            unknown = True
        else:
            deadlines.append(reset)
    retry_until = quota_timestamp(state.get("retry_until"))
    if retry_until is not None:
        deadlines.append(retry_until)
    resume_at = max(deadlines) if deadlines and not unknown else None
    retry_ready = bool(exhausted and resume_at is not None and resume_at <= now)
    names = " / ".join({"five_hour": "5h", "seven_day": "7d", "unknown": "额度窗口未知"}[key] for key in exhausted)
    return {
        "blocked": bool(exhausted) and not retry_ready,
        "exhausted": exhausted,
        "resume_at": resume_at,
        "retry_ready": retry_ready,
        "message": (f"{names} 额度耗尽，缺少可信恢复时间" if unknown
                    else f"{names} 窗口已到期，等待正常任务响应更新" if retry_ready
                    else f"{names} 额度耗尽，等待窗口重置" if exhausted else ""),
    }
