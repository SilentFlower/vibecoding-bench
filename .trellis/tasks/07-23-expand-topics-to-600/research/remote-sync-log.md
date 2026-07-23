# Remote sync log — expand topics to 600

- Time (remote): 2026-07-23 ~00:59 UTC
- Host: 23.80.83.23
- Path: /root/vibecoding-bench
- topics.md: uploaded (backup `topics.md.bak-*` if present)
- sync script: scripts/sync-topics-db.py (validate set-based 1..N; cat re supports 十一+)
- dry-run: update 300, insert 300
- apply backup: `data/db.sqlite.bak-20260723-005928`
- result: enabled topics = 600, no range 1..600
- samples: 301 环境变量对比器 / 600 交付物验收检查器

## Fix-up sync (Check-All remediations)

- Time (remote): 2026-07-23 ~01:16 UTC
- Changed topics: 401, 419, 497, 537
- apply backup: `data/db.sqlite.bak-20260723-011618`
- enabled topics still 600
