The candidate includes tabulate/__main__.py and tabulate/cli.py.
CSV stdin: name,qty followed by a row with the quoted first field "coffee, beans" and qty 2.
Use --read csv -1 --format github --output <local-file>.
JSONL stdin: {"name":"coffee","qty":2}. Use --read jsonl --format plain.
Also inspect --format no_such_table_format. No network or external service is required.
