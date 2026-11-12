# Synthetic local order import
Pinned sqlite-utils 4.2.1; use a dedicated temporary directory, never a production file.
CSV orders.csv: `id,qty\nA,1\nB,2\n`.
Run `python -m sqlite_utils insert /tmp/isolated-demo/orders.db orders orders.csv --csv --pk id`.
A subsequent Python process uses `Database('/tmp/isolated-demo/orders.db')` and `list(db['orders'].rows)`.
Explain the actual entry and persistence path. No service, network connection or library edit is requested.
