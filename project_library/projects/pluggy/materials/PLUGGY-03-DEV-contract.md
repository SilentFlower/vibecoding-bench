# Engineering contract: PLUGGY-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair registry ownership using object is identity across register/get_name/is_registered/HookCaller removal and subset filtering. Independent eq-equal/unhashable instances may register under distinct names; the exact same object still cannot register twice. User __eq__ must not run, raise, return arrays or decide None/block markers during these operations. Preserve subset input snapshot and remove only explicitly identical plugin instances, without set-based equality collapsing. Keep get_plugins() existing set/hashability API unchanged and document that separate boundary rather than overpromise it supports unhashable objects.

Deliver real implementation, original-failing public tests at library/tests/test_development_pluggy_03_dev.py, and English compatibility documentation at library/docs/development-pluggy-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pluggy/_manager.py
- library/src/pluggy/_caller.py
- library/tests/test_development_pluggy_03_dev.py
- library/docs/development-pluggy-03-dev.md
