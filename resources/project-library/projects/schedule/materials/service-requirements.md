# Reconciliation service integration

One process owns one Scheduler. Run reconciliation once immediately during startup and then every minute. Abort startup if that initial callback fails. Tag recurring work `reconcile`, allow inspection by tag, and clear that group during shutdown. Poll using existing APIs. When `idle_seconds` is None, use a bounded default wait rather than busy-spinning; never treat None as a number. No persistence, threads, or cross-machine coordination is required. Formatting examples or a plan must not edit checkout files.
