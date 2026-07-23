# Implement：扩充题库到 600 条并同步远程

## Implementation Checklist

- [x] 固化现有 300 题清单到 `research/existing-300-titles.md`（含敏感审计表）
- [x] 按 21 类配额起草 301–600（本地文件分批写入 `topics.md`）
- [x] 更新文首「300→600」与各分类「（N 题）」数量、文末进度统计
- [x] 运行解析校验：`python3 scripts/sync-topics-db.py --validate-only`
- [x] 去重扫描：301–600 vs 1–300 标题/关键词
- [x] 禁区扫描：生物/金融/敏感
- [x] 同步远程 `topics.md`
- [x] 远程 dry-run → `--apply`（确认备份路径）
- [x] 远程 SQL 验证 COUNT=600、MAX(no)=600
- [x] 记录同步结果到 `research/remote-sync-log.md`

## Validation

```bash
# 本地
python3 scripts/sync-topics-db.py --topics topics.md --validate-only
# 期望：题库校验通过: 600 条，编号 1..600

# 自定义去重/禁区（实现时内联 python 即可）
# - 无重复 no / 无空字段
# - 新题标题 ∉ 旧题标题集合
# - 禁区 regex 零命中（301-600）

# 远程（示例）
python3 scripts/sync-topics-db.py --topics /root/vibecoding-bench/topics.md \
  --db /root/vibecoding-bench/data/db.sqlite   # dry-run
python3 scripts/sync-topics-db.py --topics ... --db ... --apply
```

## Review Gates

- planning brief 经用户确认后才 `task.py start`
- 远程 `--apply` 前在对话中展示 dry-run 的 update/insert 数字并获确认（若用户已全局授权「一并同步」则 apply 可直接执行，但仍打印备份路径）
- 不同时改动 oauth 修复任务代码

## Notes

- 写作量约 300 条 brief：可分批追加（每类一段），每批后跑 validate。
- 优先使用现有分类内「工程/工具/运营/教育/内容」场景，避开医疗与二级市场交易。
