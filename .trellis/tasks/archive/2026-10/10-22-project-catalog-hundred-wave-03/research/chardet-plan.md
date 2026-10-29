# Chardet5.2字节检测任务表

固定fa905b359cbcaba93a35fd6429ba9ec4b156c1c1，源码版5.2.0、LGPL-2.1-or-later，完整505个Git文件与历史语料保留。已读detect/detect_all、UniversalDetector状态/BOM/feed/close/reset及codec映射边界。目标完整764项中754通过、10项上游xfail，不混用后续重写版本。

| 任务 | 独立业务边界与控制 | 授权 |
| --- | --- | --- |
| CD-U01 理解 | ASCII置信1不识别原始编码 | 三种codec相同文本；只读 |
| CD-U02 理解 | 检测完成不等于全流有效 | BOM后done，后续非法字节未再检；严格完整解码失败；只读 |
| CD-C01 咨询 | 跨文件必须reset | 完成后feed被忽略，reset后ASCII重新检测；只读 |
| CD-C02 咨询 | 检测标签不是Python codec保证 | 特殊UCS4标签真实检测成功但lookup失败；只读，拒绝随意重命名 |
| CD-P01 方案 | 转码归档须保留原件和歧义 | latin1/cp1252同Café且均可往返，不能证明源标签；只读方案 |
| CD-D01 诊断 | 一字节分块与整份BOM结果不同 | 追问完整原字节/分块/重置/关闭，披露后核BOM仅首次非空chunk检查；只读，不授权修复，材料不足收口 |

四场景六任务。所有合成数据无真实账号或文件，五条业务独立期望、产品链和Git/Docker准入分开。
