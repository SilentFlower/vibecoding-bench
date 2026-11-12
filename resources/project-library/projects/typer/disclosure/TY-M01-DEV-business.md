# Business scope

Now modify this product application to add an `export` subcommand. Use `python shop.py export catalog.json --output result.json` to export the product list as JSON: preserve product order and the sku, name, and quantity fields, ignore other fields, and save Chinese characters as actual characters. The input must be an array of objects, each with non-empty string sku and name fields and a non-negative integer quantity (booleans do not count as integers). Reject duplicate sku values; an empty array is allowed. Invalid JSON or any invalid record must result in a nonzero exit with an explanation, and must not leave a partial export file. Refuse to overwrite an existing output file, and do not modify the input file. Also preserve the existing `product` command, add tests of business behavior, and provide brief usage documentation. Modify only this user application and its tests and documentation; do not change Typer or the dependency environment.

# Investigation topics



# Supplied business material: materials/TY-M01/shop.py

from typing import Annotated

import typer


app = typer.Typer(add_completion=False)


@app.callback()
def root():
    """Provide the product command group. @return None."""


@app.command()
def product(name: str, quantity: Annotated[int, typer.Option(min=0)] = 1):
    """Display the product quantity. @param name Product name. @param quantity Product quantity. @return None."""
    typer.echo(f"{name}:{quantity}")


if __name__ == "__main__":
    app()


# Supplied business material: materials/TY-M01/catalog.json

[{"sku":"SKU-0001","name":"咖啡","quantity":3},{"sku":"SKU-0002","name":"茶","quantity":0}]


# Supplied business material: materials/TY-M01/README.md

# Local product tool

Run the application from `app/`. Typer comes from the fixed `library/` source and frozen dependencies.

```bash
python shop.py product 咖啡 --quantity 3
python shop.py product 咖啡
```

The current application provides only `product`; list export is not yet available. `catalog.json` is user business input and must not be modified.

