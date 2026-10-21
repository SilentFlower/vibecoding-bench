import typer


app = typer.Typer(add_completion=False)


@app.callback()
def root(verbose: bool = False):
    """声明根选项。@param verbose 详细模式。@return None。"""


@app.command()
def export():
    """演示本地导出入口。@return None。"""
    typer.echo("exported")


if __name__ == "__main__":
    app()
