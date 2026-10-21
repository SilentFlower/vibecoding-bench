from cli_helpers.tabular_output import format_output

values = [["coffee", 2], ["tea", 3]]
rows = (iter(row) for row in values)
print(list(format_output(rows, ["product", "quantity"], format_name="csv")))
