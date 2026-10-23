# 兼容UTF-8配置文件首BOM且保留真实值

固定源码：https://github.com/HBNetwork/python-decouple @ 0573e6f96637f08fb4cb85e0552f0622d36827d4。

Make RepositoryEnv and RepositoryIni accept an optional UTF-8 BOM only at the start of a UTF-8 encoded file, including standard UTF-8 codec aliases and utf-8-sig. Handle empty/BOM-only files and a BOM before a comment. Preserve every later U+FEFF in keys or values, existing Config precedence/casts/defaults, explicitly requested non-UTF8 encodings, and decoding errors. Apply the policy at the actual repository file-reading boundaries, not by global string replacement or modifying os.environ.

公开测试见同目录 development-tests.py。请在授权测试路径交付能在原版失败的回归，不修改现有测试控制或依赖；文档路径需说明行为、边界和兼容政策。私有验收独立执行，公开样例不代表全部边界。
