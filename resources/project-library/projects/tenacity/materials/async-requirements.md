# Async local startup

Use existing AsyncRetrying or the async decorator, retry only FileNotFoundError, at most three total attempts and an outer asyncio timeout. Every local read is bounded. Sleep must be awaitable and let the event loop run. Cancelling during an awaited retry wait must propagate CancelledError without another attempt. Do not swallow cancellation or promise interruption of arbitrary synchronous work; no new per_attempt_timeout API is requested.
