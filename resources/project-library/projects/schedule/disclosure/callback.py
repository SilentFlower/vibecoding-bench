import json
from pathlib import Path


def validate_rows():
    """记录合成校验事件并拒绝空金额。@return None。"""
    Path("events.json").write_text(json.dumps(["failed_job"]), encoding="utf-8")
    raise ValueError("synthetic row amount is missing")


def write_report():
    """写入合成健康报表。@return None。"""
    Path("report.json").write_text(json.dumps({"rows": 2}), encoding="utf-8")
