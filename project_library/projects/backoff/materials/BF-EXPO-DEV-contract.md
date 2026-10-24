# Engineering contract: BF-EXPO-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair expo for finite positive increasing bases/factors with a finite positive max_value so an intermediate exponentiation overflow does not terminate the sequence. Compute the true capped result, including cases where base**n overflows but factor*base**n is still below the cap. Preserve exact ordinary float outputs, priming, stable saturation, zero-factor and decreasing-base behavior. Unbounded and unsupported-domain overflow must remain explicit; do not blindly turn every OverflowError into max_value.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bf_expo_dev.py and concise English compatibility documentation at library/docs/development-bf-expo-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/backoff/_wait_gen.py
- library/tests/test_development_bf_expo_dev.py
- library/docs/development-bf-expo-dev.md
