"Public regression tests for PYPARSING-01-DEV; the complete business contract is in materials/PYPARSING-01-DEV-contract.md."
import pyparsing as pp
from pyparsing.grammar_tools import lint_grammar

def test_empty_repetition_undefined_forward_and_shadowed_literal():
    "Verify empty repetition undefined forward and shadowed literal."
    forward=pp.Forward();grammar=pp.MatchFirst([pp.Literal('a'),pp.Literal('ab')])+pp.ZeroOrMore(pp.Empty())+forward
    issues=lint_grammar(grammar);codes={x.code for x in issues}
    assert codes=={'empty-repetition','undefined-forward','shadowed-literal'}
    assert all(isinstance(x.path,tuple) for x in issues)

def test_recursive_shared_graph_and_actions_are_read_only():
    "Verify recursive shared graph and actions are read only."
    events=[];leaf=pp.Word(pp.alphas).set_parse_action(lambda t:events.append(t))
    recursive=pp.Forward();recursive <<= leaf+pp.Optional('('+recursive+')')
    before=recursive.expr
    assert lint_grammar(recursive)==() and events==[] and recursive.expr is before

