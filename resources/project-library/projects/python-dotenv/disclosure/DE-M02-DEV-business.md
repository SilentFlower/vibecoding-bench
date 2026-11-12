# Business scope

Make set_key raise ValueError for a key containing CR or LF before opening rewrite or creating a destination file. Existing files must remain byte-identical and missing destination files must remain absent on rejection. Preserve normal keys, values, return values and other editing behavior. Add focused tests; do not broaden the accepted-key policy. This scene starts independently from the original baseline and the attachments are self-contained.

# Investigation topics

- Diagnose the mismatch between writing and parsing multiline keys.

# Supplied business material: materials/key-reproduction.md

# Synthetic field-name reproduction
In a dedicated temporary file initially COLOR=blue\n, set_key(path, "REPORT\nREGION", "ready") reports success but get_key(path, "REPORT\nREGION") returns None; the writer emits the line break into separate records. Repeat with CR. A normal REPORT_REGION and a Unicode key remain ordinary valid controls. This is a local form-data integrity issue. Do not use any real configuration.


# Supplied business material: materials/key-contract.md

# Rejection contract
set_key must raise ValueError for any key containing CR or LF before opening rewrite or creating a destination. Existing files stay byte-identical; missing targets stay absent; no temporary file is created. Do not silently trim, replace or truncate the key, or write then restore. Do not broaden normal key policy or change unset_key. Valid underscore/dot/hyphen/Unicode keys, quoted values containing line breaks, escaping, return tuples and ordinary missing-file creation keep existing behavior. Add meaningful focused tests in library/tests/test_main.py. No new exception message or CLI exception protocol is specified.

