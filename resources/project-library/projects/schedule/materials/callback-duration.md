# Complete execution timeline

A job configured with `scheduler.every(2).minutes.do(write_report)` is registered at 2026-10-21 12:00:00. Polling starts it at 12:02:00. The callback completes at 12:02:30. Observed `last_run` is 12:02:30 and `next_run` is 12:04:30. A zero-duration callback instead gives `next_run` 12:04:00. No process pause or other missed poll is involved. The service currently has a single execution thread.
