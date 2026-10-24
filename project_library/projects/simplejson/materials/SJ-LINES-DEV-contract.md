# Engineering contract: SJ-LINES-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement simplejson.lines.iterloads(lines,*,errors="raise",use_decimal=False,max_chars=None), iterdumps(records), dump(records,stream) and frozen LineResult(line,status,value,error). Inputs are physical text/UTF-8 byte lines, optional BOM only on first line, blank lines ignored but counted. Validate options before consuming data. Reuse strict_loads duplicate/finite policy; collect returns a result per nonblank or invalid line and keeps later records, raise reports the physical line. Bound character size before parsing. Output uses stable_dumps, exactly one LF per record, validates each full record before its write, stays lazy and does not buffer all records. Detect short writes.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sj_lines_dev.py and concise English compatibility documentation at library/docs/development-sj-lines-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/simplejson/lines.py
- library/development_tests/test_development_sj_lines_dev.py
- library/docs/development-sj-lines-dev.md
