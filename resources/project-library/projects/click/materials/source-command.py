import click

@click.command()
@click.option("--copies", type=int, default=1, envvar="VB_CASE_COPIES")
@click.pass_context
def ship(ctx, copies):
    """输出值和来源。@param ctx 上下文。@param copies 数量。@return None。"""
    source = ctx.get_parameter_source("copies")
    click.echo((copies, source.name if source is not None else None))
