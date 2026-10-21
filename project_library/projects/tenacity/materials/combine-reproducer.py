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
