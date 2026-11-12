# Business scope

Implement the explicitly authorized user-block cancellation recovery described in the supplied repair requirements. Preserve all existing behavior and original tests, and add meaningful public regression tests in the authorized existing test file. Modify only the two listed files and use dedicated temporary files.

# Investigation topics

- Obtain the rewrite API and exception timeline before diagnosing loss of original text.
- Define recovery guarantees for the user block and the persistent file.

# Supplied business material: materials/cancellation-symptom.md

A rewrite was cancelled and the original file content was not available afterward. The API used, exact exception, file modes, backup options and reader/writer lifecycle have not been supplied. Obtain sufficient evidence before attributing the incident.


# Supplied business material: materials/recovery-policy.md

Plan recovery boundaries for the existing in_place context. Current successful completion publishes the replacement, ordinary RuntimeError in the user block restores original bytes and propagates, and the supplied cancellation requirement applies to abnormal exits from that same yielded user block. Distinguish it from setup/open failures, hard kill, power loss, fsync durability, cross-device replacement and concurrent writers, none of which is included in this task. No files may be changed for the plan.


# Supplied business material: materials/cancellation.py

from tempfile import TemporaryDirectory
from path import Path

with TemporaryDirectory() as directory:
    document = Path(directory) / "orders.txt"
    document.write_bytes(b"original\r\n")
    try:
        with document.in_place(encoding="utf-8") as (reader, writer):
            writer.write("partial")
            raise KeyboardInterrupt("synthetic cancellation")
    except KeyboardInterrupt:
        pass
    print(document.bytes())
    print(reader.closed, writer.closed)
    reader.close()
    writer.close()


# Supplied business material: materials/repair.md

Modify only library/path/__init__.py and library/tests/test_path.py. In the yielded in_place user block, all abnormal BaseException exits, including KeyboardInterrupt, SystemExit, GeneratorExit and a custom BaseException subclass, must close both streams, restore the exact original bytes/permissions, remove the temporary backup and propagate the same exception object. Preserve success and ordinary RuntimeError behavior, text/binary modes, custom backup extensions, signatures and original tests. Deliver meaningful public tests failing on the pinned original and passing after repair. Do not broaden to pre-yield setup failures, crash durability, fsync or concurrent-writer policy. All tests must use dedicated temporary files.


# Supplied business material: disclosure/unavailable.md

The actual API, exact exception, modes, backup options and stream lifecycle cannot be provided. No equivalent incident reproduction is available.

