# Scheduling requirements

Assess each option separately: (A) one Python process runs a daily report and rebuilds its task registrations at startup; (B) schedules and execution state survive process restarts; (C) multiple machines coordinate synchronized sub-second work. Only A is the current service. B and C are comparison options; no implementation is requested. All data in this package are synthetic.
