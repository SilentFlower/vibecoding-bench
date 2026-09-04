# run 继续对话版本漂移根因

## 现象

抓包时全局 Claude Code 版本设为 2.1.260，原始环境默认仍为 2.1.257。抓包 worker
关闭后，如果全局配置恢复到 2.1.257，再点击该 run 的“继续”，新 worker 会变成
2.1.257。

## 根因证据

- `runs` schema 没有 CLI 版本字段：`orchestrator/main.py:1323-1344`。
- 抓包 INSERT 只保存 `capture_model_override`：`orchestrator/main.py:6959-6972`。
- 初始 run 在真正启动容器时读取全局有效版本：`orchestrator/main.py:2469-2492`。
- continue worker 再次独立读取全局有效版本：`orchestrator/main.py:2781-2800`。
- continue API 读取完整 run 行后直接交给 `ContinueManager`，没有版本恢复逻辑：
  `orchestrator/main.py:7323-7358`。
- 现有测试只断言所有创建路径会读取同一个 mock 全局版本，没有覆盖“原 run 版本与当前
  全局版本不同”的场景：`orchestrator/test_main.py:448-517`。

## 结论

版本属于 run 的可恢复执行身份，不能只属于可变的全局设置。应在 run 创建时持久化
版本快照，初始 worker 和所有 continue worker 复用该值；历史空值才使用兼容回退。

## 修复结果

- `runs.claude_code_version` 已加入新库 schema 和旧库幂等补列。
- 普通、批量、养号和抓包 run 均在创建时保存并传递版本快照。
- continue 优先复用原 run 快照；历史 NULL 在首次继续前补写当前有效版本。
- 版本专项 11 个测试和完整后端 56 个测试均已通过。
