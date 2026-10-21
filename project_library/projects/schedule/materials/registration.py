import json
from pathlib import Path
import schedule

scheduler_a = schedule.Scheduler()
scheduler_b = schedule.Scheduler()
output = Path("reconciliation.json")
job = scheduler_a.every().minute.do(
    lambda account, day: output.write_text(json.dumps({"account": account, "day": day}), encoding="utf-8"),
    "demo-ledger", day="2026-10-21",
)
# 注册业务时刻为 2026-10-21 12:00:00，第一次轮询也在同一时刻。
scheduler_a.run_pending()
