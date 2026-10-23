# Business scope

Implement only the explicitly authorized callback repair and public regressions in the supplied complete material. Preserve original tests and every listed lifecycle boundary.

# Investigation topics

- 核对完成标注缺失的完整复现

# Supplied business material: materials/finalize-repair.md

Explicit repair authorization: change only library/alive_progress/core/progress.py and add app/test_finalize.py. A callable object with __bool__ returning False records bar.current when invoked. list(alive_it([1,2], finalize=that_object, file=StringIO(), force_tty=False, enrich_print=False, receipt=False)) currently consumes both items but never invokes it. Treat None as absence; invoke any provided callable exactly once after normal exhaustion, including an empty iterator and callable objects falsy through __len__. Preserve the true callable and None controls, actual handle argument, item order, counts, single-use semantics, and no finalization on early close or an upstream iterator exception. Preserve all original tests and APIs. Add meaningful public unittest regressions failing on original and passing on the repair. No broader callback lifecycle, formatting, thread or terminal change is authorized.


# Supplied business material: disclosure/unavailable.md

The exact iterator usage, callback definition and exhaustion evidence cannot be supplied. No further local reproduction is available.

