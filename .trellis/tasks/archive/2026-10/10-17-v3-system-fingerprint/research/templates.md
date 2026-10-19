# 画像模板来源与支持范围

模板 ID 是已持久化的契约，只能追加，不得将旧 ID 指向新的内容。

## 内核

- `debian-6.1.0-31`：release 为 `6.1.0-31-amd64`，build 为 `#1 SMP PREEMPT_DYNAMIC Debian 6.1.128-1 (2025-02-07)`。Debian 内核邮件中的实际 uname 记录：https://lists.debian.org/debian-kernel/2025/02/msg01152.html 。搜索索引返回了这组完整字段；页面直接打开失败，不将其它未返回信息推作事实。
- `debian-6.1.0-32`：release 为 `6.1.0-32-amd64`，build 为 `#1 SMP PREEMPT_DYNAMIC Debian 6.1.129-1 (2025-03-06)`。Debian bug 1100746 的实际内核启动信息同时给出 proc version 中的编译器/维护者格式：https://bugs-devel.debian.org/cgi-bin/bugreport.cgi?bug=1100746%3Bmsg%3D19 。
- proc version 按相同 release/build 与该 Debian 编译格式渲染；这是软件显示画像，不表示容器运行了这些真实内核，也不判断真实宿主的补丁状态。

## CPU 型号文本

- 当前服务器只读实测为 `AuthenticAMD` / family 23 / model 1 / stepping 2 / `AMD EPYC Processor`。Naples 模板选 7301、7351、7401、7451；型号及代际产品资料来自 AMD 官方发布：https://ir.amd.com/news-events/press-releases/detail/773/amd-epyc-datacenter-processor-launches-with-record-setting-performance-optimized-platforms-and-global-server-ecosystem-support 、https://ir.amd.com/news-events/press-releases/detail/788/amd-epyc-momentum-grows-with-datacenter-commitments-from-tencent-and-jd-com-new-product-details-from-sugon-and-lenovo 。
- 本地 Docker 实测为 family 25 / model 80，原始品牌为 Ryzen 5800H。Cezanne 模板选 5800H、5900HX；两者均为 Zen 3，同代产品规格来自 AMD：https://ir.amd.com/news-events/press-releases/detail/986/amd-announces-worlds-best-mobile-processors-in-ces-2021-keynote 。family 19h/model 50h 的 Cezanne 映射亦可见 LLVM 的 CPU 分类源码：https://llvm.googlesource.com/llvm-project/+/a15532d7647a8a4b7fd2889bd97f6f72f273c4bf/compiler-rt/lib/builtins/cpu_model/x86.c 。
- CPU 型号格式为有限文本模板，并非整套物理 SKU 仿真。CPUID 品牌、实际 flags/频率/数量/缓存/拓扑不替换；不能据此宣称底层字段全都与该 SKU 一致。
- 当前没有 Intel、其它 AMD 代际或 ARM 候选；遇到不支持/混合代际明确拒绝创建，不自动迁移画像。扩大支持范围须添加核验过的模板及测试。
