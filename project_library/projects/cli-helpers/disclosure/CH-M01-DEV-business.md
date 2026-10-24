# Business scope

Repair the complete per-call top-level option isolation contract for built-in and custom formatters. Preserve override priority, defaults, callers, preprocessors and output consumption. Modify only the authorized files and add meaningful original-failing public tests.

# Investigation topics

- Diagnose leakage of missing-value options across instances.

# Supplied business material: materials/option-leak.py

from cli_helpers.tabular_output import TabularOutputFormatter

first = TabularOutputFormatter("simple")
print("\n".join(first.format_output([[None]], ["value"], missing_value="N/A")))
second = TabularOutputFormatter("simple")
print("\n".join(second.format_output([[None]], ["value"])))


# Supplied business material: materials/option-contract.md

Repair per-call top-level option isolation in TabularOutputFormatter.format_output. Registered formatter defaults and the registration caller default dictionary must not be changed by call kwargs. Current overrides still win for that call; repeated calls, different instances, deferred output consumption, built-in formats and custom registered handlers must remain independent. Preserve signatures, preprocessors, iterator results and dependencies. This is not recursive cloning of arbitrary nested style objects or control of a third-party handler mutating its own nested objects. Only library/cli_helpers/tabular_output/output_formatter.py and library/tests/tabular_output/test_output_formatter.py may change. Add meaningful original-failing public tests and preserve the complete original suite and controls. Do not bundle color-state, Decimal-policy or row-iterator repairs.

