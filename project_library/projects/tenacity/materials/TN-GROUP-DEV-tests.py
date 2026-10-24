"Public regression tests for TN-GROUP-DEV; the complete business contract is in materials/TN-GROUP-DEV-contract.md."
import pytest
from tenacity import Future,Retrying,RetryCallState,stop_after_attempt
from tenacity.retry import retry_if_exception_group

def state(error):
    result=RetryCallState(Retrying(),None,(),{})
    result.outcome=Future.construct(1,error,True)
    return result

def test_nested_group_all_and_any_modes():
    error=ExceptionGroup('outer',[TimeoutError(),ExceptionGroup('inner',[ValueError()])])
    assert not retry_if_exception_group(lambda e:isinstance(e,TimeoutError))(state(error))
    assert retry_if_exception_group(lambda e:isinstance(e,TimeoutError),mode='any')(state(error))

def test_leaf_identity_order_and_short_circuit():
    first,second=TimeoutError(),ValueError();seen=[]
    policy=retry_if_exception_group(lambda error:not seen.append(error) and isinstance(error,TimeoutError),mode='any')
    assert policy(state(ExceptionGroup('x',[first,second]))) and seen==[first]

def test_real_controller_retries_group_then_returns_success():
    calls=[]
    def work():
        calls.append(1)
        if len(calls)==1:
            raise ExceptionGroup('temporary',[TimeoutError()])
        return 42
    assert Retrying(retry=retry_if_exception_group(lambda e:isinstance(e,TimeoutError)),stop=stop_after_attempt(3),sleep=lambda _:None)(work)==42
    assert len(calls)==2

def test_success_missing_outcome_and_invalid_mode():
    result=RetryCallState(Retrying(),None,(),{})
    policy=retry_if_exception_group(lambda error:True)
    with pytest.raises(RuntimeError):
        policy(result)
    result.set_result(1)
    assert not policy(result)
    with pytest.raises(ValueError):
        retry_if_exception_group(lambda error:True,mode='guess')
