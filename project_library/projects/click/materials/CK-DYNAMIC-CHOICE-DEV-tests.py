"""公开上下文动态选项回归。"""
import click
from click.testing import CliRunner
from click.dynamic import DynamicChoice

def test_distinct_contexts_do_not_share_choices():
    @click.command()
    @click.option('--target',type=DynamicChoice(lambda ctx:ctx.obj))
    def command(target):
        click.echo(target)
    runner=CliRunner()
    assert runner.invoke(command,['--target','one'],obj=['one']).exit_code==0
    assert runner.invoke(command,['--target','one'],obj=['two']).exit_code==2

def test_help_and_completion_use_current_values():
    type_=DynamicChoice(lambda ctx:ctx.obj)
    command=click.Command('tool');ctx=click.Context(command,obj=['alpha','beta']);param=click.Option(['--target'],type=type_)
    assert 'alpha' in type_.get_metavar(param,ctx)
    assert [item.value for item in type_.shell_complete(ctx,param,'b')]==['beta']

def test_case_normalization_returns_original_choice_object():
    class Value:
        def __str__(self):
            return 'Ready'
    value=Value();type_=DynamicChoice(lambda ctx:[value],case_sensitive=False)
    assert type_.convert('READY',None,None) is value

def test_metadata_does_not_query_provider():
    calls=[];type_=DynamicChoice(lambda ctx:not calls.append(ctx) and ['a'])
    assert type_.to_info_dict()['dynamic'] and calls==[]
