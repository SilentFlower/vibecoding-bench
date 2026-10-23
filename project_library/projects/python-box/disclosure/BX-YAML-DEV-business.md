# 交付验收边界

Repair Box.to_yaml for frozen configurations whose lists become tuples containing nested Box objects. Export those nested mappings and sequences as native YAML data through the existing backend, for both strings and files, without unfreezing or mutating the source. Preserve nested values, Unicode, empty sequences, None/bool/numbers, ordinary YAML and JSON behavior, caller serialization options, and meaningful backend errors. YAML sequences may use native lists; do not change to_dict/to_json or global YAML representers, monkeypatch the parser, or weaken frozen mutation guards.

必须完成源码与公开回归交付，不能只报告调查结论。先调查与提出方案，确认后在同一原会话实施，依据真实失败返工。原版失败、参考实现通过和冻结完整上游回归分别核对，不把参考成绩算作模型成绩。
