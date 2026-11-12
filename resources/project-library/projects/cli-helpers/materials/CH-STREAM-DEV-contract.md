# Engineering contract: CH-STREAM-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add TabularOutputFormatter.stream_output(data,headers,format_name=None,preprocessors=(),column_types=None,**kwargs) for registered CSV/TSV/JSONL formats only. Require explicit column types matching finite materialized headers to avoid whole-result inference; run the same registered/extra preprocessors lazily and return the original adapter iterator without list(data). Copy format defaults per call, preserve row errors/cancellation and Unicode/newline conventions, reject layout/table formats and invalid metadata before consuming a data row. Existing format_output remains unchanged.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ch_stream_dev.py and concise English compatibility documentation at library/docs/development-ch-stream-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cli_helpers/tabular_output/output_formatter.py
- library/development_tests/test_development_ch_stream_dev.py
- library/docs/development-ch-stream-dev.md
