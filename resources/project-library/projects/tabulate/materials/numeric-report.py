from tabulate import tabulate

rows = [["00123", "2.50"], ["1e3", "3.00"]]
print(tabulate(rows, headers=["sku", "price"], tablefmt="plain"))
