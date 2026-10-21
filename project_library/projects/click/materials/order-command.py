import json
import click

@click.command()
@click.option("--tag", multiple=True)
@click.option("--mode", type=click.Choice(["dev", "prod"], case_sensitive=False), default="dev")
@click.option("--copies", type=click.IntRange(1, 5), default=1)
def ship(tag, mode, copies):
    """输出实际参数。@param tag 标签。@param mode 模式。@param copies 数量。@return None。"""
    click.echo(json.dumps({"tag": tag, "mode": mode, "copies": copies}))

if __name__ == "__main__":
    ship()
