# Three separate requirements
1. One local writer builds a daily report from synthetic CSV and reads a local SQLite file.
2. Browser users need login, row editing, conflict handling and a shared HTTP application.
3. Distributed workers need scheduling, leases and durable execution across hosts.
Assess this pinned project rather than inventing components it does not include. SQLite can have multiple connections; distinguish database capabilities from application features.
