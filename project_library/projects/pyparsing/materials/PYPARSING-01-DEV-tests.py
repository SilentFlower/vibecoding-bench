"""语法图静态风险可定位且不会执行业务动作。"""
import pyparsing as pp
from pyparsing.grammar_tools import lint_grammar

def test_empty_repetition_undefined_forward_and_shadowed_literal():
    """三类可证明问题各自有节点路径。@return None。"""
    forward=pp.Forward();grammar=pp.MatchFirst([pp.Literal('a'),pp.Literal('ab')])+pp.ZeroOrMore(pp.Empty())+forward
    issues=lint_grammar(grammar);codes={x.code for x in issues}
    assert codes=={'empty-repetition','undefined-forward','shadowed-literal'}
    assert all(isinstance(x.path,tuple) for x in issues)

def test_recursive_shared_graph_and_actions_are_read_only():
    """递归/共享节点只访问一次，不执行动作或改图。@return None。"""
    events=[];leaf=pp.Word(pp.alphas).set_parse_action(lambda t:events.append(t))
    recursive=pp.Forward();recursive <<= leaf+pp.Optional('('+recursive+')')
    before=recursive.expr
    assert lint_grammar(recursive)==() and events==[] and recursive.expr is before

