# Publishing requirements

The editor uses this pinned TOMLKit, whose README declares TOML 1.1 support. Every downstream consumer remains Python 3.12 tomllib. Human files may already use TOML 1.1 syntax. Preserve semantic values, review explicit conversion, and reject invalid or incompatible output before replacing the published configuration. Publication failure must retain the previous bytes. This is a plan, not an implemented converter.
