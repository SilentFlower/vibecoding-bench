from typing import Annotated

import typer


app = typer.Typer(add_completion=False)


@app.callback()
def root():
    """提供商品工具命令组。@return None。"""


@app.command()
def product(name: str, quantity: Annotated[int, typer.Option(min=0)] = 1):
    """显示商品数量。@param name 名称。@param quantity 数量。@return None。"""
    typer.echo(f"{name}:{quantity}")


if __name__ == "__main__":
    app()
