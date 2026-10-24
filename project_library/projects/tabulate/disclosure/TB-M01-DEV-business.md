# Business scope

Repair the complete supplied tuple/list layout contract. Cover rowalign and maxheadercolwidths, preserve defaults and caller sequences, and deliver meaningful original-failing public tests. Modify only the two authorized files.

# Investigation topics

- Diagnose the difference between tuple and list formatting parameters.

# Supplied business material: materials/tuple-layout.py

from tabulate import tabulate

rows = [["coffee\nbeans", "ready"], ["tea", "packed"]]
headers = ["Product name", "Shipping note"]
print(tabulate(rows, headers=headers, tablefmt="grid", rowalign=["bottom"]))
print(tabulate(rows, headers=headers, tablefmt="grid", rowalign=("bottom",)))
print(tabulate(rows, headers=headers, tablefmt="grid", maxheadercolwidths=(6,)))


# Supplied business material: materials/tuple-contract.md

Repair tuple sequence handling in the existing argument-expansion path so rowalign and maxheadercolwidths tuples produce exactly the same output as equal lists. Preserve empty tuples, short-sequence defaults, existing longer-sequence behavior, scalar defaults and original list output. Do not mutate caller sequences. Keep the public signature and dependencies, and do not add unsized iterator support or change numeric/formatting policy. Only library/tabulate/__init__.py and library/test/test_api.py may change. Add meaningful public tests that fail on the original and pass after the repair; preserve original doctests and all pytest controls.

