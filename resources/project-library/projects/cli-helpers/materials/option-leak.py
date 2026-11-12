from cli_helpers.tabular_output import TabularOutputFormatter

first = TabularOutputFormatter("simple")
print("\n".join(first.format_output([[None]], ["value"], missing_value="N/A")))
second = TabularOutputFormatter("simple")
print("\n".join(second.format_output([[None]], ["value"])))
