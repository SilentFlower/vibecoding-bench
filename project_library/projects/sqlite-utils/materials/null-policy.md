# Empty cell policy and runnable example interface
The only empty-to-NULL rule concerns zero-length CSV cells. A single space stays text and numeric 0 stays numeric 0.
Example CSV: `id,note,qty\n1,,0\n2, ,3\n3,north,2\n`.
Return exactly one complete Python fenced block. The script accepts an empty SQLite database file path as argv[1] and a UTF-8 CSV file path as argv[2]. It must invoke the pinned CLI (`sys.executable -m sqlite_utils` is suitable), import into table orders, and leave the actual file available for inspection. Use existing CLI options, not manual SQL repair or a bespoke CSV parser. Explain the default versus the requested option outside the block; include an invocation. No repository edit.
