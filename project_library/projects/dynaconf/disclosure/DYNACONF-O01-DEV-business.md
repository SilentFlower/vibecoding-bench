# 业务确认

对应路线01：load_file先整体验证str/文本PathLike/list/tuple并fspath规范化，非法参数任何silent都TypeError；None/空/模块名/glob旧可选路径保持，不任意str对象。

方案确认后实施真实源码改动，公开样例不是全部验收边界。禁止修改原始测试、环境或独立验收器。
