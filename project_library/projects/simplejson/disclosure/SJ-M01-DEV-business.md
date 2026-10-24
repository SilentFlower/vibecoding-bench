# Business scope

Implement only the explicitly authorized parse-before-output-open repair and public regressions. Preserve all listed CLI and engine compatibility boundaries.

# Investigation topics

- Check CLI arguments and paths before diagnosing lost output.

# Supplied business material: materials/cli-repair.md

Explicit repair authorization: change only library/simplejson/tool.py and add app/test_tool_output.py. With malformed input JSON and an existing output file, the pinned CLI opens output for writing before parsing and truncates it even though parsing fails. With the same valid path as input/output, it truncates its own input. Parse and validate the complete input before opening a named output for writing. Keep prior output bytes unchanged on input JSON errors and support formatting a valid file in place. Preserve stdin/stdout and separate-file formatting, four-space sorted output with one final newline, Decimal handling, original tests and signatures in both C and pure-Python modes. This does not require universal atomicity for output write/encoding failures. Add meaningful public unittest regressions.


# Supplied business material: disclosure/unavailable.md

The exact CLI arguments, input bytes and output-path relationship cannot be supplied. No further local reproduction is available.

