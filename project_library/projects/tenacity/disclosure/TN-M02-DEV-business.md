# Business scope

Evaluate deeply nested built-in wait_combine trees without relying on Python recursion. Preserve each node's original float(sum(...)) grouping, left-to-right leaf calls, callable argument convention, custom subclasses and changes visible when a node is entered. Do not flatten opaque strategies or raise the global recursion limit. Reject cyclic built-in combination graphs with a clear ValueError while allowing shared acyclic subtrees. Add focused tests.

# Investigation topics

- Explain stack overflow in deeply composed strategies and why flattening them directly is unsafe.

# Supplied business material: materials/combine-reproducer.py

from tenacity import RetryCallState, Retrying, wait_combine, wait_fixed

state = RetryCallState(Retrying(), None, (), {})
items = [wait_fixed(1) for _ in range(1000)]
try:
    print(sum(items)(state))
except RecursionError as error:
    print(type(error).__name__)
print(wait_combine(*items)(state))
print((wait_fixed(1e16) + wait_fixed(1) + wait_fixed(-1e16))(state))
print(wait_combine(wait_fixed(1e16), wait_fixed(1), wait_fixed(-1e16))(state))
class Custom(wait_combine):
    def __call__(self, current):
        return float(sum(child(current) for child in self.wait_funcs)) + 7
print(wait_combine(Custom(wait_fixed(1), wait_fixed(2)), wait_fixed(4))(state))


# Supplied business material: materials/combine-contract.md

# Built-in wait_combine tree contract

Evaluate 1000/2000-deep built-in combination trees without relying on Python recursion or changing its global limit. Preserve each node's original float(sum(...)) with Python's builtin sum, including float grouping and shallow non-finite behavior. Call leaves left-to-right once per occurrence with the RetryCallState passed positionally; ordinary and falsy callables work. Custom wait_combine subclasses are opaque callable strategies: preserve overridden __call__, do not flatten them. Only exact built-in nodes are traversed by the new evaluator. When entering a node, retain the iterator of its then-current wait_funcs: an earlier leaf can change a not-yet-entered child, but rebinding an already-entered node's wait_funcs does not replace its current tuple iterator. Shared acyclic subtrees are evaluated once per occurrence, not globally deduplicated. Self and mutual cycles among built-in nodes must raise a clear bounded ValueError. A leaf exception stops before later leaves. Keep public signatures and tests/config controls unchanged. This independent original scene does not inherit the zero-multiplier repair.

