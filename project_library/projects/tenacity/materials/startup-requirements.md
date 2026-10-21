# Local startup boundary

Only a missing file is transient; malformed JSON and application field validation failures are final. Use at most three total attempts with bounded waits. Do not create a startup-complete marker or repeat a completed initialization side effect until reading and validation both succeed. These are synthetic local files, not remote requests. State reraise/RetryError policy explicitly. No library change is requested.
