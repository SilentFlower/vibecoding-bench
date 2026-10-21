from cli_helpers.tabular_output import format_output

rows = [["coffee, beans", None], ["咖啡", 2]]
headers = ["product", "quantity"]
for name in ("simple", "csv", "jsonl"):
    print(name)
    print("\n".join(format_output(rows, headers, format_name=name)))
