# Engineering contract: FT-PIPELINE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement ftfy.pipeline.TextRepairPipeline(paths,config=None,*,missing="raise") with process(record,*,index=0), run(records,*,errors="raise") and frozen RecordResult(index,status,value,changes,error). Compose completed fix_fields and real audit.repair: retain only actual changed paths and replayable RepairResult summaries, preserve nonselected fields and original records. Reuse immutable config and normalized paths, stay lazy and independent between streams. Collect per-record domain/type/path errors and continue, retaining index and error type/text without exception objects; source iterator errors must propagate. Validate errors before consuming source and do not execute content as code.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ft_pipeline_dev.py and concise English compatibility documentation at library/docs/development-ft-pipeline-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/ftfy/pipeline.py
- library/development_tests/test_development_ft_pipeline_dev.py
- library/docs/development-ft-pipeline-dev.md
