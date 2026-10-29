# Charset Normalizer字节导入任务表

固定0a9201767e9d888b5a5ed7ca44400192474ad1b0，MIT，完整100个Git文件。已完整读取from_bytes、CharsetMatch／CharsetMatches及相关编码名规范化定义，CLI按原声明绑定normalizer。当前镜像完整620主项、16子项通过；默认纯Python，2GiB回归档案与256MiB业务分别记录。

| 任务 | 独立业务事实与目标 | 材料、授权及验收 |
| --- | --- | --- |
| CN-U01 理解 | BOM只参与检测流程，不是无条件强制解码 | 同一UTF-8 BOM的短Café €及较长英文控制；实际短样本误猜与长样本正确、raw与normalized output分开，已知UTF-8-sig来源合同使用严格解码；只读 |
| CN-U02 理解 | 相同解码文本不能证明原始代码页 | cp1252／latin_1隔离集合与同一café字节；真实候选合组及could_be_from_charset，不将主候选当唯一来源；只读 |
| CN-C01 咨询 | 限定UTF-8后的无候选不能证明二进制 | 完整cp1252字节与两种隔离控制；已知来源合同与统计猜测分开，不拿best=None删除文本；只读 |
| CN-C02 咨询 | ASCII输出会用替换符丢失字符 | 完整Café — €；当前output实际errors=replace与文档ignored描述分开，严格encode可明确失败；只读 |
| CN-P01 方案 | XML归一化还会改变声明，需要独立原件与语义验收 | Windows-1252 XML与真实UTF-8 output；raw保留，声明改写不等于XML校验／签名保真，规划原件及派生物归属；只读方案 |
| CN-D01 诊断 | 失败后后续探测意外持续输出详细日志 | 追问完整bytes/kwargs、异常与前后logger证据；隔离复现steps=0／explain=True触发除零且遗留handler/level，明确合法输入和调用者配置归属，不授权修库；无材料正常收口 |

四场景六任务，无人为依赖。首次宿主探索中“BOM必然强制UTF-8”的假设被原样保留为false；完整短／长反例见charset-normalizer-bom-observation-001.json。任务在冻结前改为真实业务问题，仍须用当前镜像逐项验证，不将宿主探索计为原生业务通过。全阶段正式准入、产品链与交付另验。
