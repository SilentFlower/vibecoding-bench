"""公开含用法的命令元数据回归。"""
import pytest
import click

def test_top_level_usage_and_existing_info_are_preserved():
    command=click.Command('tool',params=[click.Option(['--name'])]);ctx=click.Context(command,info_name='actual')
    original=command.to_info_dict(ctx);description=command.describe(ctx)
    assert description['usage']==command.get_usage(ctx) and description['command_path']=='actual'
    assert all(description[key]==value for key,value in original.items()) and 'usage' not in original

def test_nested_alias_path_and_custom_usage_are_respected():
    group=click.Group('root');parent=click.Context(group,info_name='app')
    class CustomUsage(click.Command):
        def get_usage(self,ctx):
            return 'Usage: CUSTOM INPUT'
    command=CustomUsage('internal');ctx=click.Context(command,info_name='alias',parent=parent)
    result=command.describe(ctx)
    assert result['command_path']=='app alias' and 'CUSTOM INPUT' in result['usage']

def test_metadata_does_not_invoke_business_callback():
    calls=[];command=click.Command('tool',callback=lambda:calls.append(1));ctx=click.Context(command)
    command.describe(ctx)
    assert calls==[]

def test_context_identity_and_subclass_metadata_are_preserved():
    class Custom(click.Command):
        def to_info_dict(self,ctx):
            return {**super().to_info_dict(ctx),'business':'metadata'}
    command=Custom('tool');ctx=click.Context(command)
    assert command.describe(ctx)['business']=='metadata'
    with pytest.raises(TypeError):
        command.describe(click.Context(click.Command('other')))
