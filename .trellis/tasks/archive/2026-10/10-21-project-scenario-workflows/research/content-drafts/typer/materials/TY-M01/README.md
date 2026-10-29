# 本地商品工具

在 `app/` 中运行应用；Typer 来自固定的 `library/` 源码及冻结依赖。

```bash
python shop.py product 咖啡 --quantity 3
python shop.py product 咖啡
```

当前应用只提供 `product`，尚未提供清单导出。`catalog.json` 是用户业务输入，不能修改。
