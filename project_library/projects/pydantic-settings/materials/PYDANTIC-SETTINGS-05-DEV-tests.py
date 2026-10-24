"""未知CLI参数按原父子层级保留，不能都搬到末尾。"""
from pydantic_settings import BaseSettings,CliApp,CliSubCommand,CliUnknownArgs

def test_parent_and_child_unknowns_keep_ownership_after_roundtrip():
    """真实解析先建立归属，序列化后再解析核每层。@return None。"""
    class Child(BaseSettings):
        value:int=1
        unknown:CliUnknownArgs
    class Root(BaseSettings):
        name:str='old'
        unknown:CliUnknownArgs
        sub:CliSubCommand[Child]
    value=CliApp.run(Root,cli_args=['--name','now','--parent-extra=7','sub','--value','3','--child-extra=8'])
    assert value.unknown==['--parent-extra=7'] and value.sub.unknown==['--child-extra=8']
    for positionals_first in (False,True):
        copy=CliApp.run(Root,cli_args=CliApp.serialize(value,positionals_first=positionals_first))
        assert copy==value

def test_three_levels_and_child_end_marker_preserve_known_fields():
    """多层unknown各留原层，叶子--仍在已知参数之后。@return None。"""
    class Leaf(BaseSettings):
        value:int=0
        unknown:CliUnknownArgs
    class Middle(BaseSettings):
        unknown:CliUnknownArgs
        leaf:CliSubCommand[Leaf]
    class Root(BaseSettings):
        unknown:CliUnknownArgs
        mid:CliSubCommand[Middle]
    value=CliApp.run(Root,cli_args=['--root=x','mid','--middle=y','leaf','--value','9','--','--literal=z'])
    copy=CliApp.run(Root,cli_args=CliApp.serialize(value))
    assert copy==value and copy.mid.leaf.value==9
    assert copy.unknown==['--root=x'] and copy.mid.unknown==['--middle=y'] and copy.mid.leaf.unknown==['--','--literal=z']

