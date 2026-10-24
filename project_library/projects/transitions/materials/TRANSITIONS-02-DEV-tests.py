"""选中的State对象列表正确移除路径，不影响其他来源。"""
from enum import Enum
from transitions import Machine,State

def test_state_object_source_and_destination_lists_remove_exact_edges():
    """source与dest各元素规范化，列表本身没有name。@return None。"""
    machine=Machine(states=['a','b','c'],initial='a',auto_transitions=False)
    machine.add_transition('go','a','b');machine.add_transition('go','a','c');machine.add_transition('go','b','c')
    machine.remove_transition('go',source=[machine.get_state('a')],dest=[machine.get_state('b')])
    assert [(item.source,item.dest) for item in machine.get_transitions('go')]==[('a','c'),('b','c')]
    assert machine.go() and machine.state=='c'

def test_mixed_enum_name_state_and_final_binding_cleanup():
    """混合类型按每项name处理，最后路径删除后解绑事件。@return None。"""
    class Phase(Enum):a=1;b=2;c=3
    machine=Machine(states=Phase,initial=Phase.a,auto_transitions=False)
    machine.add_transition('go','a','b');machine.add_transition('go','c','b')
    machine.remove_transition('go',source=[machine.get_state('a'),'c'],dest=[Phase.b])
    assert 'go' not in machine.events and not hasattr(machine,'go')

