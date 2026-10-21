import json
from pathlib import Path
import schedule

scheduler = schedule.Scheduler()
def export():
    """写入合成导出后返回取消信号。@return 调度取消标记。"""
    Path("export.json").write_text(json.dumps({"rows": 2}), encoding="utf-8")
    return schedule.CancelJob

job = scheduler.every().minute.do(export).tag("exports")
other = scheduler.every().minute.do(lambda: None).tag("exports")
unrelated = scheduler.every().minute.do(lambda: None).tag("other")
