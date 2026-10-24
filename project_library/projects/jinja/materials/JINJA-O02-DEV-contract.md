# 让宏和捕获帧中的无上下文include真正写入当前输出

对应路线06：同步without context include在宏/捕获帧必须走simple_write写buffer；顶层仍yield流式，隔离、ignore missing及异步转义语义保持。

请先阅读实际源码和公开复现，完成调查、澄清和兼容方案，获得确认后在同一工作区实现。失败时依据独立反馈返工；测试和说明不是单独目标。
