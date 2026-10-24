"""公开列表选项真实命令回归。"""
import pytest
import click
from click.testing import CliRunner
from click.delimited import DelimitedList

def test_quoted_separator_and_empty_fields_are_preserved():
    assert DelimitedList().convert('"a,b",,"c""d"',None,None)==('a,b','','c"d')

def test_real_option_uses_underlying_type_and_preserves_multiple_values():
    @click.command()
    @click.option('--ids',type=DelimitedList(int),multiple=True)
    def command(ids):
        click.echo(repr(ids))
    result=CliRunner().invoke(command,['--ids','1,2','--ids','3'])
    assert result.exit_code==0 and result.output.strip()=='((1, 2), (3,))'

def test_bad_item_reports_position_and_prevents_callback():
    calls=[]
    @click.command()
    @click.option('--ids',type=DelimitedList(int))
    def command(ids):
        calls.append(ids)
    result=CliRunner().invoke(command,['--ids','1,bad'])
    assert result.exit_code==2 and '第2项' in result.output and calls==[]

def test_bounds_typed_sequences_and_invalid_quotes_are_checked():
    assert DelimitedList(int,min_items=1).convert([1,'2'],None,None)==(1,2)
    with pytest.raises(click.BadParameter):
        DelimitedList(max_items=1).convert('a,b',None,None)
    with pytest.raises(click.BadParameter):
        DelimitedList().convert('"unclosed',None,None)
