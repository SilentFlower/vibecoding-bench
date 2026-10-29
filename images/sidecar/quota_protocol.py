"""被动额度协议的纯函数；sidecar 构建副本由 sync-quota-protocol.py 同步。"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from json import dumps, loads
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


def warmup_quota_decision(state: dict, limits: dict, now: float) -> dict:
    """计算养号专用阈值，不改写共用额度事实。

    :param state: 当前身份已合并的真实窗口
    :param limits: five_hour/seven_day 的整数阈值，None 表示关闭
    :param now: 当前 UTC 秒数
    :return: 阈值命中、未知窗口、恢复时间及稳定策略/周期键
    """
    limits = {key: limits.get(key) for key in ("five_hour", "seven_day")}
    if any(value is not None and (type(value) is not int or not 1 <= value <= 100)
           for value in limits.values()):
        raise ValueError("养号额度阈值必须为 1-100 的整数或关闭")
    hit, unknown, deadlines, periods = [], [], [], {}
    missing_reset = False
    windows = state.get("windows", {})
    if not isinstance(windows, dict):
        raise ValueError("额度窗口结构无效")
    for key, limit in limits.items():
        if limit is None:
            continue
        window = windows.get(key, {})
        if not isinstance(window, dict):
            raise ValueError("额度窗口结构无效")
        reset = quota_timestamp(window.get("reset_at"))
        periods[key] = [reset, bool(reset is not None and reset <= now)]
        try:
            raw = window.get("utilization")
            used = float(raw) if not isinstance(raw, bool) else float("nan")
            if not isfinite(used) or used < 0:
                used = None
        except (TypeError, ValueError):
            used = None
        if used is not None and used >= limit and (reset is None or reset > now):
            hit.append(key)
            missing_reset = missing_reset or reset is None
            if reset is not None:
                deadlines.append(reset)
        elif used is None or reset is None or reset <= now:
            unknown.append(key)
    names = " / ".join("5h" if key == "five_hour" else "7d" for key in hit)
    return {"enabled": any(value is not None for value in limits.values()), "limits": limits,
            "hit": hit, "unknown": unknown, "blocked": bool(hit),
            "sample_required": bool(unknown) and not hit,
            "resume_at": max(deadlines) if deadlines and not missing_reset else None,
            "message": (f"{names} 已用达到养号阈值，等待可信窗口更新" if hit
                        else "养号额度未知或窗口已到期，等待一次正式请求更新" if unknown else ""),
            "policy_key": sha256(dumps(limits, sort_keys=True).encode()).hexdigest(),
            "window_key": dumps(periods, sort_keys=True)}


def passive_recovery_decision(state: dict, limits: dict, now: float) -> dict:
    """计算 v3 正常执行的被动恢复机会，与抓包侧共用周期身份。

    :param state: 当前身份已合并的真实窗口
    :param limits: five_hour/seven_day 的整数阈值，None 表示关闭
    :param now: 当前 UTC 秒数
    :return: 阈值判定及仅针对已到期旧命中窗口的恢复周期
    """
    decision = warmup_quota_decision(state, limits, now)
    limits = decision["limits"]
    windows = state.get("windows") or {}
    renewal = [key for key in decision["unknown"] if limits.get(key) is not None
        and (windows.get(key, {}).get("reset_at") or float("inf")) <= now
        and (windows.get(key, {}).get("utilization") or 0) >= limits[key]]
    periods = loads(decision["window_key"])
    for key, period in periods.items():
        period.append(limits[key])
    for key in ("five_hour", "seven_day", "unknown"):
        window = windows.get(key, {})
        reset = window.get("reset_at")
        if window.get("exhausted") and reset is not None and reset <= now:
            renewal.append("common:" + key)
            periods["common:" + key] = [reset]
    # 首次未知不消耗机会；共同耗尽到期即使关闭阈值仍要保留持久的单次恢复约束。
    decision.update(policy_key="v3-passive-recovery", window_key=dumps(periods, sort_keys=True),
        sample_required=bool(renewal), sample_windows=renewal)
    return decision


def warmup_sample_used(decision: dict, admission: dict | None) -> bool:
    """判断仍未知的窗口是否已经使用本策略的单次更新机会。

    :param decision: 最新养号判定；v3 的 sample_windows 仅包含实际需要恢复的窗口
    :param admission: 当前身份的持久许可，不存在时为 None
    :return: 任一仍需更新的窗口已经使用机会时返回 True
    """
    if not admission or admission.get("policy_key") != decision["policy_key"]:
        return False
    previous = loads(admission["window_key"])
    current = loads(decision["window_key"])
    # 部分窗口刚得到数据不能为仍未知的另一个窗口重新发放机会。
    return any(key in previous and previous[key] == current[key]
               for key in decision.get("sample_windows", decision["unknown"]))
