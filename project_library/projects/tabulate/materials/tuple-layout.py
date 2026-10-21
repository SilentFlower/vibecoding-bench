from tabulate import tabulate

rows = [["coffee\nbeans", "ready"], ["tea", "packed"]]
headers = ["Product name", "Shipping note"]
print(tabulate(rows, headers=headers, tablefmt="grid", rowalign=["bottom"]))
print(tabulate(rows, headers=headers, tablefmt="grid", rowalign=("bottom",)))
print(tabulate(rows, headers=headers, tablefmt="grid", maxheadercolwidths=(6,)))
