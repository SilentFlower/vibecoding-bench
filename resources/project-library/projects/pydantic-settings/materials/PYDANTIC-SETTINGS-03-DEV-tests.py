"Public regression tests for PYDANTIC-SETTINGS-03-DEV; the complete business contract is in materials/PYDANTIC-SETTINGS-03-DEV-contract.md."
from collections import deque
from enum import Enum
from pydantic_settings import BaseSettings,CliApp

def test_frozen_and_queue_containers_roundtrip_real_cli():
    "Verify frozen and queue containers roundtrip real cli."
    class Config(BaseSettings):
        frozen:frozenset[str]
        queue:deque[str]
    expected=['first','x,y','a"b','\n','\\','last']
    value=Config(frozen=frozenset(['茶','x,y']),queue=deque(expected))
    argv=CliApp.serialize(value);copy=CliApp.run(Config,cli_args=argv)
    assert copy==value and isinstance(copy.frozen,frozenset) and isinstance(copy.queue,deque)
    assert list(copy.queue)==expected

def test_empty_containers_and_enum_elements_keep_types():
    "Verify empty containers and enum elements keep types."
    class Color(str,Enum):RED='red';BLUE='blue'
    class Config(BaseSettings):
        frozen:frozenset[Color]=frozenset([Color.RED])
        queue:deque[int]=deque([8])
    empty=Config(frozen=frozenset(),queue=deque())
    assert CliApp.run(Config,cli_args=CliApp.serialize(empty))==empty
    full=Config(frozen=frozenset([Color.BLUE]),queue=deque([3,1,3]))
    assert CliApp.run(Config,cli_args=CliApp.serialize(full))==full

def test_optional_queue_and_existing_repeated_shorthand_keep_policy():
    "Verify optional queue and existing repeated shorthand keep policy."
    class Config(BaseSettings):
        plain:list[str]
        frozen:frozenset[str]
        queue:deque[int]|None=None
    value=CliApp.run(Config,cli_args=['--plain','1,2','--frozen','1','--frozen','2','--queue','[3,2,3]'])
    assert value.plain==['1','2'] and value.frozen==frozenset(['1','2']) and list(value.queue)==[3,2,3]
    assert CliApp.run(Config,cli_args=CliApp.serialize(value))==value

