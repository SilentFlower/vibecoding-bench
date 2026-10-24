"Public regression tests for JINJA-O03-DEV; the complete business contract is in materials/JINJA-O03-DEV-contract.md."
from jinja2 import Environment
from jinja2.sandbox import SandboxedEnvironment

def test_dynamic_negative_bases_and_constant_parity():
    "Verify dynamic negative bases and constant parity."
    for optimized in [False,True]:
        env=Environment(optimized=optimized)
        for base in [-3,-1,0,2]:
            for exponent in [0,1,2,3,-1]:
                if base==0 and exponent<0:continue
                dynamic=env.from_string('{{('+str(base)+')**power}}').render(power=exponent)
                constant=env.from_string('{{('+str(base)+')**('+str(exponent)+')}}').render()
                assert dynamic==constant==str(base**exponent)

def test_unparenthesized_negative_ast_and_left_associative_chain():
    "Verify unparenthesized negative ast and left associative chain."
    env=Environment()
    assert env.from_string('{{ -1**x}}').render(x=2)=='1'
    assert env.from_string('{{2**3**2}}').render()=='64'
    assert env.from_string('{{base**exponent}}').render(base=-2,exponent=2)=='4'

def test_sandbox_intercepted_binop_still_receives_real_operands():
    "Verify sandbox intercepted binop still receives real operands."
    class Sandbox(SandboxedEnvironment):
        "Public regression fixture: Sandbox."
        intercepted_binops=frozenset(['**'])
        def call_binop(self,context,operator,left,right):return f'{left}:{right}'
    assert Sandbox().from_string('{{ -3**x}}').render(x=2)=='-3:2'
