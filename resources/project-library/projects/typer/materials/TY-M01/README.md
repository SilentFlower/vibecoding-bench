# Local product tool

Run the application from `app/`. Typer comes from the fixed `library/` source and frozen dependencies.

```bash
python shop.py product 咖啡 --quantity 3
python shop.py product 咖啡
```

The current application provides only `product`; list export is not yet available. `catalog.json` is user business input and must not be modified.
