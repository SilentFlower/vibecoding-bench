"Public regression tests for TN-IDLE-BUDGET-DEV; the complete business contract is in materials/TN-IDLE-BUDGET-DEV-contract.md."
import asyncio
from datetime import timedelta
from types import SimpleNamespace
import pytest
from tenacity import Retrying,AsyncRetrying,RetryError,wait_fixed,stop_after_attempt
from tenacity.stop import stop_before_idle_budget

def test_budget_uses_idle_and_upcoming_not_execution_time():
    policy=stop_before_idle_budget(timedelta(seconds=5))
    assert not policy(SimpleNamespace(idle_for=2,upcoming_sleep=2,seconds_since_start=1000))
    assert policy(SimpleNamespace(idle_for=2,upcoming_sleep=3,seconds_since_start=0))

def test_real_retry_stops_before_spending_the_budget():
    sleeps=[];calls=[]
    def fail():
        calls.append(1)
        raise ValueError()
    with pytest.raises(RetryError):
        Retrying(wait=wait_fixed(2),stop=stop_before_idle_budget(5),sleep=sleeps.append)(fail)
    assert sleeps==[2,2] and len(calls)==3

def test_async_controller_and_combined_stop_work():
    async def scenario():
        sleeps=[]
        async def sleeping(value):
            sleeps.append(value)
        async def fail():
            raise ValueError()
        with pytest.raises(RetryError):
            await AsyncRetrying(wait=wait_fixed(1),stop=stop_before_idle_budget(2)|stop_after_attempt(9),sleep=sleeping)(fail)
        return sleeps
    assert asyncio.run(scenario())==[1]

def test_invalid_and_zero_budgets_have_defined_behavior():
    for value in (-1,float('nan'),float('inf'),True):
        with pytest.raises(ValueError):
            stop_before_idle_budget(value)
    assert stop_before_idle_budget(0)(SimpleNamespace(idle_for=0,upcoming_sleep=0))
