from tenacity import RetryCallState, Retrying, wait_exponential, wait_exponential_jitter, wait_random_exponential
from unittest.mock import patch

state = RetryCallState(Retrying(), None, (), {})
state.attempt_number = 1025
for multiplier, base in ((0.0, 2), (0, 2.0), (0, 2)):
    print(multiplier, base, wait_exponential(multiplier=multiplier, exp_base=base, max=60)(state))
    with patch('tenacity.wait.random.uniform', side_effect=lambda low, high: low + (high - low) / 4):
        print(wait_random_exponential(multiplier=multiplier, exp_base=base, max=60)(state))
        print(wait_exponential_jitter(multiplier=multiplier, exp_base=base, max=60, jitter=1)(state))
