# Existing leaf editing

The original name is a single-line literal string and server.port already exists as an integer. Keep all unrelated text and existing comments. update_config receives the complete source, a replacement name and port; it returns text only. Names may contain Unicode, backslashes, an apostrophe or a newline. Retain literal quoting only when it is representable; otherwise use a valid basic string.
