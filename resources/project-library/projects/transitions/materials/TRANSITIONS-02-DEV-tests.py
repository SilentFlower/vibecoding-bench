"Public regression tests for TRANSITIONS-02-DEV; the complete business contract is in materials/TRANSITIONS-02-DEV-contract.md."
from enum import Enum
from transitions import Machine,State

def test_state_object_source_and_destination_lists_remove_exact_edges():
    "Verify state object source and destination lists remove exact edges."
    machine=Machine(states=['a','b','c'],initial='a',auto_transitions=False)
    machine.add_transition('go','a','b');machine.add_transition('go','a','c');machine.add_transition('go','b','c')
    machine.remove_transition('go',source=[machine.get_state('a')],dest=[machine.get_state('b')])
    assert [(item.source,item.dest) for item in machine.get_transitions('go')]==[('a','c'),('b','c')]
    assert machine.go() and machine.state=='c'

def test_mixed_enum_name_state_and_final_binding_cleanup():
    "Verify mixed enum name state and final binding cleanup."
    class Phase(Enum):a=1;b=2;c=3
    machine=Machine(states=Phase,initial=Phase.a,auto_transitions=False)
    machine.add_transition('go','a','b');machine.add_transition('go','c','b')
    machine.remove_transition('go',source=[machine.get_state('a'),'c'],dest=[Phase.b])
    assert 'go' not in machine.events and not hasattr(machine,'go')

