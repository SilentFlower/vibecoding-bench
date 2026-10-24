# Business scope

Avoid computing an irrelevant exponential contribution when the multiplier is zero in wait_exponential and wait_exponential_jitter. Preserve min/max ordering, random-exponential bounds, one jitter draw and all non-zero behavior. Cover integer and float zero/base cases without changing public signatures or sleeping.

# Investigation topics

- Locate overflow at large retry numbers when the floating-point multiplier is zero.

# Supplied business material: materials/zero-reproducer.py

from tenacity import RetryCallState, Retrying, wait_exponential, wait_exponential_jitter, wait_random_exponential
from unittest.mock import patch

state = RetryCallState(Retrying(), None, (), {})
state.attempt_number = 1025
for multiplier, base in ((0.0, 2), (0, 2.0), (0, 2)):
    print(multiplier, base, wait_exponential(multiplier=multiplier, exp_base=base, max=60)(state))
    with patch('tenacity.wait.random.uniform', side_effect=lambda low, high: low + (high - low) / 4):
        print(wait_random_exponential(multiplier=multiplier, exp_base=base, max=60)(state))
        print(wait_exponential_jitter(multiplier=multiplier, exp_base=base, max=60, jitter=1)(state))


# Supplied business material: materials/zero-contract.md

# Zero exponential contribution contract

For valid positive finite bases and attempt >=1, multiplier 0 or 0.0 contributes zero even at attempts 1024, 1025 and 2049. Preserve the original max(max(0,min), min(result,max)) ordering, non-zero minima, random-exponential uniform bounds, and additive jitter. Jitter draws exactly once in the original order, even when the exponent is irrelevant; a zero multiplier must not erase its sampled contribution. Test integer-zero/float-base and float-zero/integer-base overflow routes plus integer-zero/integer-base normal control, early positive-multiplier capping, ordinary positive growth and an actual bounded controller using a sleep spy. No real waiting, public signature, dependency or unrelated lifecycle changes. Add public regression tests only in the authorized path. This scene starts independently from the original checkout.

