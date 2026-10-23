# Business scope

Make repr safe for an unconfigured Job, including default interval one. Preserve its unconfigured state and exact representation of configured jobs. Do not assign a default unit, register it, or run a callback merely to format it. Add focused public tests. This independent scenario starts from the original checkout and does not inherit the run_all repair. Use the pinned checkout as evidence and cite the relevant source symbols. State assumptions and missing information. Preserve existing public behavior unless this task explicitly requests a change.

# Investigation topics

- 解释默认未配置任务的表示异常与正常对照

# Supplied business material: materials/interactive.txt

Pinned checkout observations (independent Scheduler instances):

>>> repr(schedule.Scheduler().every())
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
  File "schedule/__init__.py", line 320, in __repr__
    unit=(self.unit[:-1] if self.interval == 1 else self.unit),
          ~~~~~~~~~^^^^^
TypeError: 'NoneType' object is not subscriptable
>>> str(schedule.Scheduler().every())
'Job(interval=1, unit=None, do=None, args=(), kwargs={})'
>>> repr(schedule.Scheduler().every(2))
'Every 2 None do [None] (last run: [never], next run: [never])'

Each object has unit=None, job_func=None, last_run=None and next_run=None. No job has been registered in its scheduler. The interval-one formatting branch is the differing case; do not assume every unconfigured interval raises.


# Supplied business material: materials/repr-contract.md

# Authorized safe formatting

Make repr safe for a Job that has not finished configuration, including Scheduler().every() and every(2), and for a unit-selected job before do(). Return a nonempty readable string without changing state, registering jobs, or invoking callbacks. Do not choose a default time unit. Keep str behavior and exact configured repr output compatible for intervals one/two, random ranges, at-times, positional/keyword arguments and functools.partial callbacks. Only library/schedule/__init__.py and library/test_schedule.py may change. Add focused public regression tests. This is an independent scenario based on the pinned original checkout: it does not inherit the run_all repair from another scenario.

