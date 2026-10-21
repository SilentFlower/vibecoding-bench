# Complete polling timeline

The job is registered with `scheduler.every().minute.do(write_report)` at 2026-10-21 12:00:00. The process is paused and does not poll for 30 minutes. At 12:30:00 it calls `scheduler.run_pending()` twice without advancing the clock. Exactly one JSON report is written. `last_run` is 12:30:00 and `next_run` is 12:31:00. At 12:31:00 another poll produces the second report. The callback itself is instantaneous in this reproduction.
