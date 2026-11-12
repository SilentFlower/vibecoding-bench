"""按账号 IANA 时区判断每周运行窗口，配置不改变环境身份。"""
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo


def normalize_run_window(value: object) -> dict:
    """规范化独立窗口配置，关闭时仍保留用户已保存的日期和区间。

    :param value: schema=1 对象；None 表示旧账号不限制。
    :return: 可持久化的严格配置；不接受未知键或隐式类型转换。
    """
    if value is None:
        return {"schema": 1, "enabled": False, "days": [], "intervals": []}
    if not isinstance(value, dict) or set(value) != {"schema", "enabled", "days", "intervals"} \
            or type(value["schema"]) is not int or value["schema"] != 1 or type(value["enabled"]) is not bool:
        raise ValueError("运行时段配置格式无效")
    days, intervals = value["days"], value["intervals"]
    if not isinstance(days, list) or len(days) > 7 or any(type(day) is not int or not 0 <= day <= 6 for day in days) \
            or not isinstance(intervals, list) or len(intervals) > 8:
        raise ValueError("请选择有效星期，时间段最多设置 8 个")
    normalized = []
    for interval in intervals:
        if not isinstance(interval, dict) or set(interval) != {"start", "end"} \
                or any(not isinstance(interval[key], str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", interval[key])
                    for key in ("start", "end")):
            raise ValueError("运行时段必须使用 HH:MM 格式")
        if interval["start"] == interval["end"]:
            raise ValueError("开始和结束时间不能相同；全天运行请关闭限制")
        normalized.append({"start": interval["start"], "end": interval["end"]})
    if value["enabled"] and (not days or not normalized):
        raise ValueError("启用运行时段时必须选择星期和至少一个时间段")
    return {"schema": 1, "enabled": value["enabled"], "days": sorted(set(days)),
        "intervals": sorted(normalized, key=lambda interval: (interval["start"], interval["end"]))}


def _configuration_key(configuration: dict) -> tuple:
    return (tuple(configuration["days"]), tuple((int(interval["start"][:2]) * 60 + int(interval["start"][3:]),
        int(interval["end"][:2]) * 60 + int(interval["end"][3:])) for interval in configuration["intervals"]))


def _allowed(key: tuple, local: datetime) -> bool:
    days, intervals = key
    weekday, minute = local.weekday(), local.hour * 60 + local.minute
    return any((weekday in days and start <= minute < end) if start < end else (
        (weekday in days and minute >= start) or ((weekday - 1) % 7 in days and minute < end))
        for start, end in intervals)


@lru_cache(maxsize=256)
def _next_transition(key: tuple, zone: str, minute: int, allowed: bool) -> float | None:
    # 沿真实 UTC 分钟前进，自然跳过不存在的当地分钟，并覆盖重复小时的两个时刻。
    target = ZoneInfo(zone)
    for offset in range(1, 15 * 24 * 60 + 1):
        timestamp = (minute + offset) * 60
        if _allowed(key, datetime.fromtimestamp(timestamp, timezone.utc).astimezone(target)) != allowed:
            return float(timestamp)
    return None


def run_window_snapshot(configuration: dict, zone: str, now: float) -> dict:
    """给出当地时间、当前准入及下一边界，不生成执行或发起网络请求。

    :param configuration: 已规范化的窗口配置。
    :param zone: 账号环境中实际固化的 IANA 时区。
    :param now: 当前 UTC 秒；允许测试使用确定时刻。
    :return: 公开窗口摘要，边界采用开始包含、结束不包含。
    """
    if type(now) not in (int, float) or not math.isfinite(now):
        raise ValueError("当前时间无效")
    local = datetime.fromtimestamp(now, timezone.utc).astimezone(ZoneInfo(zone))
    key = _configuration_key(configuration)
    allowed = not configuration["enabled"] or _allowed(key, local)
    boundary = _next_transition(key, zone, int(now // 60), allowed) if configuration["enabled"] else None
    return {"enabled": configuration["enabled"], "allowed": allowed, "timezone": zone,
        "server_now": now, "local_time": local.isoformat(), "config": configuration,
        "next_open_at": boundary if not allowed else None, "next_close_at": boundary if allowed else None,
        "message": "未限制运行时段" if not configuration["enabled"] else (
            "当前允许启动新一轮" if allowed else "休息中，等待当地可运行时间段")}
