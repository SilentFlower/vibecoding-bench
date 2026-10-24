"""公开真实状态声明路径规划回归。"""
import pytest
from statemachine.transition_graph import TransitionGraph
from statemachine import StateMachine,State

class Flow(StateMachine):
    draft=State(initial=True)
    ready=State()
    done=State(final=True)
    advance=draft.to(ready)
    finish=ready.to(done)
    reset=ready.to(draft)

def test_shortest_candidate_path_and_cycle_are_stable():
    graph=TransitionGraph(Flow)
    assert graph.shortest_path('draft','done')==('advance','finish') and graph.shortest_path('ready','draft')==('reset',)
    assert graph.shortest_path('done','draft') is None and graph.shortest_path('draft','draft')==()

def test_budget_and_unknown_states_are_explicit():
    graph=TransitionGraph(Flow);assert graph.shortest_path('draft','done',max_depth=1) is None
    with pytest.raises(KeyError): graph.shortest_path('unknown','done')
    with pytest.raises(ValueError): graph.shortest_path('draft','done',max_depth=True)

def test_guard_and_initial_callbacks_are_never_executed():
    calls=[]
    class Guarded(StateMachine):
        start=State(initial=True);done=State(final=True)
        finish=start.to(done,cond=lambda:calls.append('guard') or False)
        def on_enter_start(self): calls.append('enter')
    assert TransitionGraph(Guarded).shortest_path('start','done')==('finish',) and calls==[]

def test_declaration_edges_are_detached_from_later_graph_queries():
    graph=TransitionGraph(Flow);before=tuple(Flow.draft.transitions)
    graph.shortest_path('draft','done');assert tuple(Flow.draft.transitions)==before
    assert [(edge.source,edge.target,edge.event) for edge in graph.edges]==[('draft','ready','advance'),('ready','done','finish'),('ready','draft','reset')]
