from tabulate import tabulate

print(tabulate([["<b>商品</b>"]], tablefmt="html"))
print(tabulate([["<b>商品</b>"]], tablefmt="unsafehtml"))
print(tabulate([["咖啡咖啡咖啡", "长期订阅订单"]], headers=["Product", "Delivery"], tablefmt="grid", maxcolwidths=[4, 4]))
