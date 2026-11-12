from more_itertools import chunked
committed = []
try:
    for batch in chunked(iter(range(5)), 2, strict=True):
        committed.extend(batch)
except ValueError as error:
    print(type(error).__name__)
print(committed)
