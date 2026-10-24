# 业务确认

对应路线06：同步without context include在宏/捕获帧必须走simple_write写buffer；顶层仍yield流式，隔离、ignore missing及异步转义语义保持。

方案确认后实施真实源码改动，公开样例不是全部验收边界。禁止修改原始测试、环境或独立验收器。
