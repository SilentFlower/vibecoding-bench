from decimal import Decimal
from cli_helpers.tabular_output import format_output

print(list(format_output([[1, 2]], ["id", "id"], format_name="jsonl")))
value = Decimal("0.12345678901234567890123456789")
print(list(format_output([[value]], ["price"], format_name="jsonl")))
