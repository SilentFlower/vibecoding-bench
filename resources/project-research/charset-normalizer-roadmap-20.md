# charset-normalizer：二十步真实工程迭代路线

固定 [jawah/charset_normalizer@0a9201767e9d888b5a5ed7ca44400192474ad1b0](https://github.com/jawah/charset_normalizer/tree/0a9201767e9d888b5a5ed7ca44400192474ad1b0)，原生证据见 [单仓审查](./charset-normalizer.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．有界读取文件流

- **来源／场景**：读取较大的本地文本，不想先把整个文件复制进RAM；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：from_fp实际调用fp.read()，实测read_size=-1；steps/chunk_size控制评分抽样而非输入读取大小
- **交付及模块**：增加from_stream，声明可seek/不可seek策略并在受控缓冲下评分与验证；`src/charset_normalizer/api.py:from_fp`, `src/charset_normalizer/utils.py:cut_sequence_chunks`。
- **兼容与实际依赖**：现有from_fp不关调用方流的合同保持；不能把仅抽样判断宣称完整验证；步骤依赖：无。
- **正常验收**：可seek文本分块读取并给出与原版相同可用候选，记录实际读取范围
- **异常／边界验收**：不可seek、短读、BOM跨块、尾部无效字节和取消明确处理，峰值缓冲符合上限
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 02．常用字节缓冲输入

- **来源／场景**：本地mmap或memoryview数据希望直接检查编码；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：from_bytes声明bytes/bytearray，未提供from_buffer或明确缓冲所有权
- **交付及模块**：增加支持只读连续buffer的入口，明确何时复制与视图生命周期；`src/charset_normalizer/api.py:from_bytes`, `src/charset_normalizer/models.py:CharsetMatch`。
- **兼容与实际依赖**：bytes/bytearray默认行为保持；不声称所有Python codec可零复制；步骤依赖：无。
- **正常验收**：同一bytes及memoryview得到相同候选/文字，并记录是否复制
- **异常／边界验收**：非连续view、已释放view、可变底层数据、非字节格式和mmap关闭有确定错误
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 03．结构化检测解释

- **来源／场景**：归档导入失败需要知道某个codec为何被排除；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：explain=True输出日志；硬失败/软失败/采样信息是局部变量，没有稳定报告对象
- **交付及模块**：提供detect_with_report，记录候选顺序、过滤理由、抽样范围、评分和提前结束原因；`src/charset_normalizer/api.py:from_bytes`, `src/charset_normalizer/models.py`。
- **兼容与实际依赖**：不改变默认排名；chaos/coherence不冒充校准概率；日志继续可选；步骤依赖：无。
- **正常验收**：有声明、BOM与多候选的文本报告可解释最终选择
- **异常／边界验收**：解码失败、cp_exclusion排除、无候选、fallback和提前停止各有不同机器状态
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 04．歧义时明确暂不选择

- **来源／场景**：短的单字节文本可由多种codec输出合理文字；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/models.py)。
- **原版缺口**：CharsetMatches.best总取排序第一；could_be_from_charset已有等价文字组，但无abstain政策
- **交付及模块**：新增显式select_or_abstain，按最小信息量、候选差距和可接受等价组给决定；`src/charset_normalizer/models.py:CharsetMatches`, `src/charset_normalizer/models.py:CharsetMatch`。
- **兼容与实际依赖**：best默认不变；拒绝选择不等于判二进制，等价文字组不强猜原始charset；步骤依赖：无。
- **正常验收**：信息充分文本选候选，极短歧义文本返回ambiguity与候选摘要
- **异常／边界验收**：空文件、全ASCII、等价解码、近分数非等价及用户指定允许集分别验收
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 05．目录文本审查清单

- **来源／场景**：档案目录含多层文本，需要保留相对路径和局部错误；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：CLI支持多个显式文件，API只有单文件；无scan_directory的递归/过滤/结果流合同
- **交付及模块**：新增本地目录扫描器，选择后缀、遍历顺序、错误策略并生成逐文件结果；`src/charset_normalizer/api.py:from_path`, `src/charset_normalizer/cli/__main__.py:cli_detect`。
- **兼容与实际依赖**：默认只读不归一化文件；不自动跟随目录外链接；单文件API保持；步骤依赖：无。
- **正常验收**：多个目录文本逐个给候选，失败文件不使已经成功结果丢失
- **异常／边界验收**：空目录、不可读文件、重复路径、链接循环、不同后缀与路径编码有明确结果
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 06．有损输出与BOM策略

- **来源／场景**：转换成ASCII时不能悄悄把中文变成问号；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/models.py)。
- **原版缺口**：CharsetMatch.output固定encode(errors=replace)，实测中文输出??；说明文字却称忽略；无可选错误/BOM策略
- **交付及模块**：增加显式transcode策略：strict/replace/ignore、替换统计与BOM保留/去除/添加；`src/charset_normalizer/models.py:CharsetMatch.output`。
- **兼容与实际依赖**：默认output旧行为可保留并明确；新严格入口默认不丢字，声明头重写能力复用已有实现；步骤依赖：无。
- **正常验收**：Unicode可表示目标编码无损输出；中文转ASCII strict明确失败，replace报告两个替换
- **异常／边界验收**：无法编码字符、目标codec未知、UTF16/UTF8 BOM、空输出和缓存键涵盖策略
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 07．可变输入快照一致性

- **来源／场景**：调用方传bytearray后继续复用缓冲区；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/models.py)。
- **原版缺口**：CharsetMatch保留payload引用且缓存str；实测raw变XYZ而cached_text仍ABC
- **交付及模块**：增加明确snapshot/borrowed所有权策略，默认安全快照或在borrowed模式禁止复用后查询；`src/charset_normalizer/models.py:CharsetMatch.__init__`, `src/charset_normalizer/api.py:from_bytes`。
- **兼容与实际依赖**：bytes无额外复制；选择默认变更时说明内存代价，不伪称零复制；步骤依赖：无。
- **正常验收**：修改原bytearray后快照对象raw/str/output仍一致
- **异常／边界验收**：部分slice修改、延迟解码、submatch、fingerprint与外部释放均不形成前后矛盾
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 08．声明编码的优先策略

- **来源／场景**：旧HTML的声明与实际字节不符，导入需要记录信任程度；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：preemptive_behaviour只有布尔优先，不提供明确trust/validate/ignore政策
- **交付及模块**：新增DeclarationPolicy，把声明识别、别名归一化、验证及冲突回退分开报告；`src/charset_normalizer/api.py:from_bytes`, `src/charset_normalizer/utils.py:any_specified_encoding`。
- **兼容与实际依赖**：原默认优先行为保持；BOM与文档声明冲突不能静默覆盖实际解码结果；步骤依赖：无。
- **正常验收**：正确cp1252声明得到同结果，错误声明在validate下记录失败并回退
- **异常／边界验收**：多声明、未知别名、声明超探测窗口、冲突BOM和ignore模式有精确结果
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 09．显式语言先验

- **来源／场景**：本地馆藏已知主要是希腊文，需要在歧义候选间使用该信息；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/cd.py)。
- **原版缺口**：API有language_threshold但无preferred languages参数；内部根据codec推语言集
- **交付及模块**：增加有界可解释LanguagePrior，用于排序加权而不绕过字节有效性；`src/charset_normalizer/cd.py:coherence_ratio`, `src/charset_normalizer/api.py:from_bytes`。
- **兼容与实际依赖**：无先验排名不变；不是确定语言标签或置信概率；不因此接受解码失败codec；步骤依赖：无。
- **正常验收**：希腊候选在等价可用候选中按先验排序，并报告影响
- **异常／边界验收**：不存在语言、矛盾语言、混合文字及只有一个合法codec时不被先验强改
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 10．分段编码不一致报告

- **来源／场景**：几个历史文本片段被直接拼成同一个文件；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：整个from_bytes只返回整份payload的codec候选，无带区间的混合编码报告
- **交付及模块**：新增detect_segments，对明确窗口与边界输出局部候选、变化点和未知区间；`src/charset_normalizer/api.py:from_bytes`, `src/charset_normalizer/utils.py:cut_sequence_chunks`。
- **兼容与实际依赖**：显式启用，不把混合编码结果塞入原CharsetMatch；不承诺任意无边界字节均可恢复；步骤依赖：无。
- **正常验收**：UTF8段与cp1252段有足够文字和给定边界时分别识别并解码
- **异常／边界验收**：多字节跨窗口、短段、ASCII公共段、无稳定变化点和重叠窗口不能伪造确定分割
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 11．一组文件的共同编码选择

- **来源／场景**：同一批导出文件应使用一个共同编码，单文件短样本不够；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/models.py)。
- **原版缺口**：可分别检测但无公共候选交集与批次选择助手
- **交付及模块**：新增detect_common_encoding，综合各文件有效候选、等价解码组和共同评分；`src/charset_normalizer/models.py:CharsetMatches`, `src/charset_normalizer/api.py:from_bytes`。
- **兼容与实际依赖**：不对不同来源硬设共同编码；无交集返回分组建议；不代替第05步遍历；步骤依赖：无。
- **正常验收**：同源cp1252长短文件合并信息后选共同可用codec
- **异常／边界验收**：一文件UTF8而另一无兼容codec、全ASCII批次、空文件和局部坏文件有明确结论
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 12．候选文字业务校验回调

- **来源／场景**：CSV导入可用表头/字段数来区分两份都可读的解码；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：现有chaos/coherence不接业务校验器，调用方需全部解码再另选
- **交付及模块**：新增只读CandidateValidator，给候选解码文字返回接受/拒绝及理由，排名调整显式可见；`src/charset_normalizer/api.py:from_bytes`, `src/charset_normalizer/models.py:CharsetMatch`。
- **兼容与实际依赖**：没有校验器输出不变；回调不改原payload，不将业务校验通过冒充原始编码证明；步骤依赖：无。
- **正常验收**：已知表头的候选通过校验，乱码表头被拒并保留理由
- **异常／边界验收**：回调异常、全部拒绝、回调耗时预算与多候选等价内容避免重复调用有断言
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 13．压缩本地文本入口

- **来源／场景**：归档文件为gzip/bz2/xz压缩文本；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：from_path直接读取压缩字节，没有from_compressed_path；调用方可先用stdlib解压
- **交付及模块**：新增显式压缩格式入口，解压后调用检测并报告压缩/解压大小；`src/charset_normalizer/api.py:from_path`。
- **兼容与实际依赖**：不自动把任意二进制猜成压缩文本；不增加远程读取；解压预算必需；步骤依赖：无。
- **正常验收**：三种标准压缩的同一文本得到相同文字候选
- **异常／边界验收**：损坏流、空内容、截断、多成员gzip和解压大小超预算有独立错误，保留原文件
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 14．截断尾字符的显式诊断模式

- **来源／场景**：日志最后一次写入被中断，只差末尾半个UTF8字符；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：默认严格codec解码可能排除整体可读候选；无带损失边界的partial模式
- **交付及模块**：增加opt-in partial_text，只容许明确末尾不完整码单元，返回可读前缀和未解码尾字节；`src/charset_normalizer/api.py:from_bytes`, `src/charset_normalizer/utils.py`。
- **兼容与实际依赖**：默认严格行为保持；不忽略中间任意坏字节，不声称无损恢复；步骤依赖：无。
- **正常验收**：UTF8末尾缺一字节时给正确前缀及准确尾区间
- **异常／边界验收**：内部坏字节、UTF16奇数字节、只有残片和BOM残片需区分不可推断状态
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 15．可声明抽样计划

- **来源／场景**：文件前半是ASCII数字，末尾才有关键自然语言；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/utils.py)。
- **原版缺口**：当前steps/chunk_size提供固定抽样，cut_sequence_chunks没有公开采样策略合同
- **交付及模块**：增加SamplingPlan，可选择头/尾/均匀/调用方给定区间并记录覆盖度；`src/charset_normalizer/utils.py:cut_sequence_chunks`, `src/charset_normalizer/api.py:from_bytes`。
- **兼容与实际依赖**：默认抽样不变；评分样本更换不跳过完整字节解码验证；区间归一化可复现；步骤依赖：无。
- **正常验收**：指定尾段采样时可观察其评分影响，重复计划结果稳定
- **异常／边界验收**：区间重叠、越界、多字节边界、空窗口和样本上限不重复计权或产生非法片段
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 16．检测工作预算与取消

- **来源／场景**：交互式导入需要在用户取消后结束尚未完成的codec遍历；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/api.py)。
- **原版缺口**：API只有抽样参数，没有DetectionBudget、deadline或cancel合同
- **交付及模块**：新增可选codec尝试数/解码字节/期限与取消预算，返回未完成状态和已有证据；`src/charset_normalizer/api.py:from_bytes`。
- **兼容与实际依赖**：未完成不能包装成完整best判断；默认无预算保持；参数非法立即拒绝；步骤依赖：无。
- **正常验收**：充足预算与原版结果一致，取消后不再启动新候选工作
- **异常／边界验收**：边界预算恰好用完、采样阶段取消、无候选与超时区分，所有流资源按归属关闭
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 17．增量归一化输出

- **来源／场景**：大文件转换为UTF8时不希望output先生成完整str和bytes副本；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/models.py)。
- **原版缺口**：output懒解码后一次encode并缓存完整目标bytes，无iter_output
- **交付及模块**：新增iter_output，以增量解码/编码器向file-like写块并保持声明头处理；`src/charset_normalizer/models.py:CharsetMatch.output`。
- **兼容与实际依赖**：原output结果保持；与检测是否流式分开；不能切断多字节或重复BOM；步骤依赖：无。
- **正常验收**：分块输出拼接逐字节等于选定策略的一次输出，大文本额外缓冲受限
- **异常／边界验收**：异常写入、取消、目标不支持字符、空文本和声明跨块均保持准确错误位置
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 18．跨进程稳定文本摘要

- **来源／场景**：归档去重摘要需在不同Python进程之间一致；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/models.py)。
- **原版缺口**：fingerprint是hash(str)，适合当前进程比较但不稳定；无stable_digest
- **交付及模块**：新增明确算法/编码/归一化选项的稳定摘要，区分原始字节摘要与解码文本摘要；`src/charset_normalizer/models.py:CharsetMatch.fingerprint`。
- **兼容与实际依赖**：原fingerprint仍可用；默认不做Unicode归一化，不把等外观字符偷偷合并；步骤依赖：无。
- **正常验收**：同一解码文字由不同编码输入、不同进程得到相同text摘要，不同raw摘要
- **异常／边界验收**：BOM、NFC/NFD、换行差异、空文本及未知算法的行为明确
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 19．归一化文件原子保存

- **来源／场景**：CLI replace模式写入失败时需要保留原归档；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/cli/__main__.py)。
- **原版缺口**：当前直接open目标wb再write，输出失败可留下截断内容
- **交付及模块**：新增normalize_file_atomic，以同目录临时文件完成编码与写入后replace；`src/charset_normalizer/cli/__main__.py:cli_detect`, `src/charset_normalizer/models.py:CharsetMatch.output`。
- **兼容与实际依赖**：默认只检测不写；显式替换才写入；不改变output编码猜测策略；步骤依赖：无。
- **正常验收**：成功替换后文件内容可按UTF8读取，成功前原文件保持
- **异常／边界验收**：编码失败、写满、替换失败和取消保留原文件，清理仅本次临时文件
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。

## 20．可预览输出路径策略

- **来源／场景**：批量归一化希望输出到新目录并避免同名覆盖；[固定源码](https://github.com/jawah/charset_normalizer/blob/0a9201767e9d888b5a5ed7ca44400192474ad1b0/src/charset_normalizer/cli/__main__.py)。
- **原版缺口**：CLI默认在文件名插入检测到的原编码，没有输出root/template/冲突策略
- **交付及模块**：增加OutputPathPolicy，预览相对目录、扩展名、目标编码标记和存在时处理；`src/charset_normalizer/cli/__main__.py:cli_detect`。
- **兼容与实际依赖**：旧命名默认保持；只处理显式输入目录边界，用户可选跳过/报错/覆盖；步骤依赖：无。
- **正常验收**：多目录同名文件在新root保持相对路径，预览与实际路径一致
- **异常／边界验收**：无扩展名、多个点、已存在文件、Unicode文件名和大小写等价冲突均不悄悄覆盖
- **原生回归**：`tests/test_base_detection.py`, `tests/test_edge_case.py`, `tests/test_large_payload.py`, `tests/test_full_detection.py`, `tests/test_cli.py`, `tests/test_cli_json.py`, `tests/test_thread_safety.py`。
