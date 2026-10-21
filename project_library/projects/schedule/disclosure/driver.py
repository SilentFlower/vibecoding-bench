import schedule
from callback import validate_rows, write_report

scheduler = schedule.Scheduler()
scheduler.every().minute.do(validate_rows)
scheduler.every().minute.do(write_report)
scheduler.run_all()
