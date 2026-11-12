# Business scope

Implement the complete public synchronous Iterator enhancement. Preserve the exact existing input, error, callback and namespace contracts, and avoid whole-source buffering. Modify only the authorized implementation and public test file; add meaningful public original-failing tests.

# Investigation topics

- Diagnose input dispatch for an ordinary chunk iterator.

# Supplied business material: materials/chunk-input.py

from xmltodict import parse

chunks = ["<orders>", "<order id='A'><qty>2</qty></order>", "</orders>"]
print(parse(chunk for chunk in chunks))
print(parse(iter(chunks)))


# Supplied business material: materials/iterator-contract.md

Extend parse to accept ordinary synchronous Iterator objects of XML text or byte chunks (including list_iterator, map and a custom __iter__/__next__ object), preserving existing generator behavior. This is an explicit input enhancement, not a claim that every iterable was already supported.
Keep the public signature and dependencies. Preserve complete str/bytes/bytearray/memoryview inputs, file-like read precedence, namespace options and existing defaults. Decode UTF-8 split across byte chunks through the existing parser. Do not first join or materialize the complete source.
Preserve TypeError for invalid chunks, source iteration exceptions, finalization errors for truncated XML, and immediate ParsingInterrupted when item_callback returns false. Do not consume later chunks after that rejection. Ordinary list containers and asynchronous inputs are outside this enhancement.
Only library/xmltodict.py and library/tests/test_xmltodict.py may change. Add meaningful public tests that fail on the pinned original and pass after the enhancement. Preserve all frozen original regression tests and pytest controls.

