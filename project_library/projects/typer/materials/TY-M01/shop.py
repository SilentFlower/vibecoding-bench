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
