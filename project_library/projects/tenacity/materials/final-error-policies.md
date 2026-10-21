# Explicit caller interfaces

Compare three intentional interfaces after three missing-file attempts: default RetryError (inspect last_attempt), reraise=True exposing the original FileNotFoundError, and an explicit retry_error_callback returning {"fallback": true}. A non-retryable malformed JSON error must propagate immediately; it is not exhaustion. A first-attempt success must not invoke fallback. Select a policy for an application caller instead of patching the library.
