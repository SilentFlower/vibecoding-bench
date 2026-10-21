# Caller-side safe editing plan

Use one synthetic regular local file and cooperating writers. Existing LF, CRLF or mixed line endings matter. A failed serialization, validation, temporary write or replacement must retain the old published file bytes. Detect a stale edit while writers cooperate. Explain permissions, temporary cleanup, locking around check and replace, and the distinct limits of atomicity, conflict detection and crash durability. The library itself is unchanged.
