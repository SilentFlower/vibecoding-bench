A local process reads a small validated configuration JSON file repeatedly.
Publishing a new version must not expose a partially written file. Bound the cache,
choose an explicit invalidation/version policy, and propagate invalid JSON on a cache miss.
Do not promise that TTLCache watches the filesystem, caches exceptions, or makes returned
mutable objects independent. Prefer existing library APIs and application design.
