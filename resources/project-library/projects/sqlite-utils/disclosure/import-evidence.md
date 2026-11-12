# Requested incident evidence
All data is synthetic. Command:
`python -m sqlite_utils insert isolated/orders.db orders -`
Stdin bytes: `id,qty\nA,1\nB,2\n`
Complete stderr:
```text
Error: Invalid JSON - use --csv for CSV or --tsv for TSV files

JSON error: Expecting value: line 1 column 1 (char 0)
```
Exit status: 1. The default input format was not explicitly changed. Validate the explanation against the actual CLI and a correct JSON input, and recommend a supported invocation. No library edit is authorized.
