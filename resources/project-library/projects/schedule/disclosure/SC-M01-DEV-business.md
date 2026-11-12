# Business scope

Fix Scheduler.run_all so delay_seconds is applied only between jobs in the current snapshot, with no trailing delay. Preserve execution order, snapshot semantics, callback arguments, cancellation and exception propagation. Add focused public regression tests. Do not change unrelated scheduling behavior. Use the pinned checkout as evidence and cite the relevant source symbols. State assumptions and missing information. Preserve existing public behavior unless this task explicitly requests a change.

# Investigation topics

- Locate the unnecessary final wait during batch execution.

# Supplied business material: materials/run-all-trace.json

{
  "delay_seconds": 2,
  "synthetic_callbacks": true,
  "cases": [
    {
      "jobs": 0,
      "events": []
    },
    {
      "jobs": 1,
      "events": [
        [
          "job",
          0
        ],
        [
          "sleep",
          2
        ]
      ]
    },
    {
      "jobs": 3,
      "events": [
        [
          "job",
          0
        ],
        [
          "sleep",
          2
        ],
        [
          "job",
          1
        ],
        [
          "sleep",
          2
        ],
        [
          "job",
          2
        ],
        [
          "sleep",
          2
        ]
      ]
    }
  ],
  "measurement": "Only schedule.time.sleep is replaced by an event recorder in the isolated business subprocess. Platform timeouts and budgets use the real clock."
}


# Supplied business material: materials/run-all-contract.md

# Authorized correction

Apply delay_seconds only between executions of jobs in the snapshot taken at the start of run_all. With a positive delay of 2 seconds, 0, 1, and 3 jobs must request 0, 0, and 2 sleeps. Maintain the snapshot if callbacks add or cancel jobs. Preserve order, positional/keyword arguments, decorator use, CancelJob handling, and exception propagation. If a callback raises, stop immediately without an extra sleep. Zero-delay sleeps may be omitted. Only library/schedule/__init__.py and library/test_schedule.py may change. Add focused public regression tests. Do not change test configuration, dependencies, or verifier files.

