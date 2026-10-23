# 冻结嵌套配置的YAML导出不再泄漏Box对象

固定源码：https://github.com/cdgriffith/Box @ a4c10e977b574114613431394b30412b50aaacce。

Repair Box.to_yaml for frozen configurations whose lists become tuples containing nested Box objects. Export those nested mappings and sequences as native YAML data through the existing backend, for both strings and files, without unfreezing or mutating the source. Preserve nested values, Unicode, empty sequences, None/bool/numbers, ordinary YAML and JSON behavior, caller serialization options, and meaningful backend errors. YAML sequences may use native lists; do not change to_dict/to_json or global YAML representers, monkeypatch the parser, or weaken frozen mutation guards.

公开测试见同目录 development-tests.py。请在授权测试路径交付能在原版失败的回归，不修改现有测试控制或依赖；文档路径需说明行为、边界和兼容政策。私有验收独立执行，公开样例不代表全部边界。
