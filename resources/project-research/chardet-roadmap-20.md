# chardet（历史稳定5.2.0）：二十步真实工程迭代路线

固定 [chardet/chardet@fa905b359cbcaba93a35fd6429ba9ec4b156c1c1](https://github.com/chardet/chardet/tree/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1)，原生证据见 [单仓审查](./chardet.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．分块BOM识别一致

- **来源／场景**：同一UTF8 BOM文本按一字节分块读取；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/universaldetector.py)。
- **原版缺口**：5.2仅在首次非空feed检查完整BOM；整份识别UTF-8-SIG，一字节分块变utf-8；实证保存
- **交付及模块**：在初始小缓冲中等待BOM前缀完整或确定不匹配，再启动prober；`chardet/universaldetector.py:UniversalDetector.feed`。
- **兼容与实际依赖**：只针对冻结5.2修复；后续分支不同流水线是否仍有同一症状本轮未验证；普通无BOM不延迟整份输入；步骤依赖：无。
- **正常验收**：任意分块UTF8/16/32完整BOM与整份输入识别一致
- **异常／边界验收**：BOM只有前缀、空块、无BOM但前几个字节相似及reset复用都不丢字节
- **原生回归**：`test.py`。

## 02．结果的Python解码可用性

- **来源／场景**：调用方检测后直接用Python codec解码；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/universaldetector.py)。
- **原版缺口**：5.2可返回X-ISO-10646-UCS-4-3412，codecs.lookup实测不支持；README列过这种BOM，不能称识别本身错误
- **交付及模块**：增加结构化结果详情，区分原始BOM身份、字节序及Python可用codec/额外转换需求；`chardet/universaldetector.py:UniversalDetector.feed`, `chardet/resultdict.py`。
- **兼容与实际依赖**：保留旧encoding标签，不能把特殊字节序假标成可直接解码UTF32；额外解码器单独声明；步骤依赖：无。
- **正常验收**：普通UTF8返回可用codec，特殊UCS4保留身份且明确不能直接Python解码
- **异常／边界验收**：未知标签、别名、空输入、BOM冲突和可选转换步骤有明确状态
- **原生回归**：`test.py`。

## 03．编码名表示选择

- **来源／场景**：历史客户端需要旧标签，新工具需要规范Python codec名；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/__init__.py)。
- **原版缺口**：5.2只有should_rename_legacy的超集重命名；没有compat_names。[后续固定分支API](https://github.com/chardet/chardet/blob/88107b4ab8abc8b202fd145bc457b8b481557c87/src/chardet/__init__.py)已提供compat_names，本项是冻结版兼容升级方案
- **交付及模块**：提供显式旧名称/规范codec名称模式，并保存映射来源；`chardet/__init__.py:detect`, `chardet/universaldetector.py:UniversalDetector`。
- **兼容与实际依赖**：承认后续已有能力，不称当前上游新缺口；超集改名与纯别名规范化区分；步骤依赖：无。
- **正常验收**：UTF8/windows/ISO标签在所选模式稳定，均保留原始推断标签
- **异常／边界验收**：Python别名未知、旧特殊UCS4名称、None与大小写不能被错误归一成其他编码
- **原生回归**：`test.py`。

## 04．候选编码允许排除集合

- **来源／场景**：已知档案只来自少数编码，想减少无关候选；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/__init__.py)。
- **原版缺口**：5.2方便API没有编码集合过滤；lang_filter是语言组而非编码白名单。[后续固定分支API](https://github.com/chardet/chardet/blob/88107b4ab8abc8b202fd145bc457b8b481557c87/src/chardet/__init__.py)已有include/exclude，本项是兼容升级
- **交付及模块**：新增可校验的允许/排除集合并在prober选择前应用，结果报告实际集合；`chardet/__init__.py:detect_all`, `chardet/universaldetector.py:UniversalDetector`。
- **兼容与实际依赖**：不将旧lang_filter冒充新编码级过滤；不复制未核对许可的后续实现；默认ALL保持；步骤依赖：无。
- **正常验收**：只允许UTF8/cp1252时最终候选只在该集合内
- **异常／边界验收**：别名重复、同时包含排除、空允许集、所有候选被排除和未知名字立即明示
- **原生回归**：`test.py`。

## 05．输入检查字节预算

- **来源／场景**：交互式工具只想检查文件的前N字节并知道覆盖范围；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/__init__.py)。
- **原版缺口**：5.2无max_bytes；调用方可自行切片。[后续固定分支API](https://github.com/chardet/chardet/blob/88107b4ab8abc8b202fd145bc457b8b481557c87/src/chardet/__init__.py)已有max_bytes，属于冻结版升级适配
- **交付及模块**：新增检查预算和覆盖信息，方便API与UniversalDetector一致受控；`chardet/__init__.py:detect`, `chardet/universaldetector.py:UniversalDetector.feed`。
- **兼容与实际依赖**：预算判定只证明已检查范围，不把前缀可解码当全文可解码；默认旧行为保持；步骤依赖：无。
- **正常验收**：N字节预算准确记录consumed/remaining，足够预算与原结果一致
- **异常／边界验收**：0/负数、BOM恰跨预算、多块累计与过量feed不越预算或伪称完整
- **原生回归**：`test.py`。

## 06．空输入与无匹配政策

- **来源／场景**：批量导入需区分空文件和没有可信候选；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/__init__.py)。
- **原版缺口**：5.2固定None/0.0结果，调用方自行fallback。[后续固定分支API](https://github.com/chardet/chardet/blob/88107b4ab8abc8b202fd145bc457b8b481557c87/src/chardet/__init__.py)已有empty_input_encoding/no_match_encoding，本项为明确兼容升级
- **交付及模块**：增加显式sentinel/fallback选项与原因，保留是否验证过候选；`chardet/__init__.py:detect`, `chardet/universaldetector.py:UniversalDetector.close`。
- **兼容与实际依赖**：默认None合同保持；fallback不能以高confidence伪装探测结果；不推断数据一定属于默认编码；步骤依赖：无。
- **正常验收**：空文件与非空无匹配得到不同状态，调用方fallback被明确标注
- **异常／边界验收**：非法fallback codec、空允许集、只有空块与reset后无数据不混淆
- **原生回归**：`test.py`。

## 07．文本类型与非文本结果

- **来源／场景**：目录中混有普通图片与文本，不想把所有字节都当文字；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/resultdict.py)。
- **原版缺口**：5.2ResultDict只有encoding/confidence/language。[后续固定分支API](https://github.com/chardet/chardet/blob/88107b4ab8abc8b202fd145bc457b8b481557c87/src/chardet/__init__.py)新增mime_type等，本项是冻结版升级兼容研究
- **交付及模块**：增加明确non-text/unknown/text状态及有限类型详情，保留旧三字段输出可选；`chardet/resultdict.py`, `chardet/__init__.py:detect`。
- **兼容与实际依赖**：不宣称完整文件格式识别；MIME类型来源与编码来源分开；后续能力已存在不重称新发明；步骤依赖：无。
- **正常验收**：显式已知PNG头与UTF8文本的状态区分，旧模式字段保持
- **异常／边界验收**：短文件、截断签名、只含零字节、ASCII数据文件和未知格式不能过度确定
- **原生回归**：`test.py`。

## 08．检测过程结构化解释

- **来源／场景**：归档人员需知道为何选择一个候选；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/universaldetector.py)。
- **原版缺口**：prober confidence和状态可内部查看，没有detect_with_trace稳定报告
- **交付及模块**：提供prober启用/排除/置信变化、BOM捷径和最终选择的结构化轨迹；`chardet/universaldetector.py:UniversalDetector`, `chardet/charsetgroupprober.py`。
- **兼容与实际依赖**：默认无轨迹开销；confidence不是经校准概率；不更改原排名；步骤依赖：无。
- **正常验收**：UTF8早停及多单字节候选可看到真实选择路径
- **异常／边界验收**：无候选、异常prober、reset、多块输入与被过滤编码各有有序原因
- **原生回归**：`test.py`。

## 09．选中编码的全文验证

- **来源／场景**：只用前缀检测后仍需确认所选codec能解码整份文档；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/universaldetector.py)。
- **原版缺口**：5.2.done可提前停止，检测不是严格全文解码证明；没有validate_result助手
- **交付及模块**：新增独立验证入口，使用增量codec检查全文并返回首个错误字节区间；`chardet/universaldetector.py:UniversalDetector.done`, `chardet/__init__.py:detect`。
- **兼容与实际依赖**：检测与验证状态分列；不把检测高分当验证通过；用户流位置/关闭归属明确；步骤依赖：无。
- **正常验收**：完整合法UTF8文件通过，尾部不完整字符被准确定位
- **异常／边界验收**：BOM、跨块错误、特殊不支持codec、不可seek流与验证取消均可区分
- **原生回归**：`test.py`。

## 10．低信息输入暂缓决定

- **来源／场景**：很短的文本多候选分数接近时希望返回歧义；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/universaldetector.py)。
- **原版缺口**：5.2取最高超过固定阈值的prober，detect_all可列更多候选但无abstain政策
- **交付及模块**：新增显式最小证据与候选差距决策，返回候选和不确定原因；`chardet/universaldetector.py:UniversalDetector.close`, `chardet/__init__.py:detect_all`。
- **兼容与实际依赖**：旧detect默认不变；暂缓不等于判二进制；阈值不是概率保证；步骤依赖：无。
- **正常验收**：充分证据文本选中，极短近分候选保留歧义而不强行fallback
- **异常／边界验收**：同分、等价解码、全ASCII、用户过滤后唯一候选与空输入分别定义
- **原生回归**：`test.py`。

## 11．文件对象便利检测

- **来源／场景**：调用方希望检测后文件仍在原位置并可继续读取；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/universaldetector.py)。
- **原版缺口**：已有UniversalDetector增量feed和CLI文件读取，没有detect_file的流归属/位置合同
- **交付及模块**：增加薄文件/流入口，支持显式保留位置、读取块大小及结果覆盖信息；`chardet/universaldetector.py:UniversalDetector`, `chardet/cli/chardetect.py:description_of`。
- **兼容与实际依赖**：不把已有增量核心当新能力；不隐式关闭调用方流；文件路径与bytes输入分开；步骤依赖：无。
- **正常验收**：对同一文件检测后位置按选项恢复，结果与手动feed一致
- **异常／边界验收**：不可seek、短读、文件读错、空文件与用户关闭的流有明确状态
- **原生回归**：`test.py`。

## 12．带标识批量记录

- **来源／场景**：离线导入希望逐条得到检测结果和局部错误；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/__init__.py)。
- **原版缺口**：CLI能读多个文件，API只有单bytes/手动循环；没有detect_many结果流合同
- **交付及模块**：新增保留id/顺序/错误的惰性批量API，配置按记录隔离；`chardet/__init__.py:detect`, `chardet/universaldetector.py:UniversalDetector.reset`。
- **兼容与实际依赖**：不复用未reset的状态；默认出错是否继续明确；不把bytes当iterable记录；步骤依赖：无。
- **正常验收**：三条输入中一条类型错误时另两条正常且标识保持
- **异常／边界验收**：空批次、重复id、输入生成器异常、取消及fail-fast之后未执行项不记成功
- **原生回归**：`test.py`。

## 13．可复用不可变检测配置

- **来源／场景**：不同档案来源要固定过滤/预算/fallback且避免手改类常量；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/universaldetector.py)。
- **原版缺口**：5.2配置分散在构造参数、属性与MINIMUM_THRESHOLD常量，没有DetectorConfig
- **交付及模块**：提供版本化不可变配置与校验，显式创建独立检测会话；`chardet/universaldetector.py:UniversalDetector.__init__`, `chardet/__init__.py:detect`。
- **兼容与实际依赖**：不把全局模型修改当每调用配置；先完成相关新选项的实际合同，再汇总配置；步骤依赖：04、05、06。
- **正常验收**：同一配置多次/多会话结果一致，不同来源配置互不污染
- **异常／边界验收**：无效阈值、冲突过滤、未知配置版本、并发与配置拷贝保持明确错误
- **原生回归**：`test.py`。

## 14．自定义prober正式扩展点

- **来源／场景**：组织有一类本地历史编码模型，希望作为本地候选扩展；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/charsetprober.py)。
- **原版缺口**：prober类存在但UniversalDetector固定创建，修改内部列表没有稳定注册合同
- **交付及模块**：增加会话级本地prober registry，声明名字、输入条件、结果codec与生命周期；`chardet/charsetprober.py:CharSetProber`, `chardet/universaldetector.py:UniversalDetector`。
- **兼容与实际依赖**：不从输入装载代码；默认内建prober不变；注册不代表模型准确率已经验证；步骤依赖：无。
- **正常验收**：本地确定性示例prober可参与评分并在trace中标明来源
- **异常／边界验收**：重复名、结果codec无效、feed/close异常、reset与不同会话注册不串用
- **原生回归**：`test.py`。

## 15．候选业务校验

- **来源／场景**：已知文本应是某种本地表格，可用表头区分可读候选；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/__init__.py)。
- **原版缺口**：detector只用字节统计，没有调用级候选文字验证器
- **交付及模块**：增加只读CandidateValidator，按可解码候选返回接受/拒绝和原因；`chardet/__init__.py:detect_all`, `chardet/resultdict.py`。
- **兼容与实际依赖**：不绕过严格codec失败；没有验证器时原排名保持；业务匹配不证明原始编码唯一；步骤依赖：无。
- **正常验收**：选中能保留已知表头的候选，拒绝理由可审查
- **异常／边界验收**：全部拒绝、回调异常、预算超限、相同解码去重与非文本输入有确定行为
- **原生回归**：`test.py`。

## 16．指定范围的编码差异检查

- **来源／场景**：一个归档文件由多个明确记录段拼接，想逐段查编码；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/universaldetector.py)。
- **原版缺口**：一个UniversalDetector面向同一文档，没有区间化detect_segments
- **交付及模块**：增加由调用方边界或受限窗口定义的分段结果，保留字节范围和不确定区间；`chardet/universaldetector.py:UniversalDetector`, `chardet/__init__.py:detect`。
- **兼容与实际依赖**：不宣称自动恢复任意混合编码；原单文档入口保持；相邻相同结果是否合并明确；步骤依赖：无。
- **正常验收**：给定两段UTF8/cp1252文字分别得到对应可读候选与正确范围
- **异常／边界验收**：多字节跨边界、短段、全ASCII共用段、无候选及重叠窗口不伪造确定分界
- **原生回归**：`test.py`。

## 17．增量会话检查点

- **来源／场景**：长的本地读取暂停后希望继续同一次统计；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/universaldetector.py)。
- **原版缺口**：UniversalDetector有reset但没有稳定snapshot/restore合同，任意pickle不算公开协议
- **交付及模块**：增加受限且版本化检查点，保存状态机、计数、待定BOM与输入覆盖摘要；`chardet/universaldetector.py:UniversalDetector`, `chardet/codingstatemachine.py`。
- **兼容与实际依赖**：不反序列化任意Python对象；模型版本必须匹配；不把只保存result当完整恢复；步骤依赖：无。
- **正常验收**：在多个分块点暂停恢复后与连续feed结果一致
- **异常／边界验收**：不同模型/配置、已close、截断检查点、重复恢复和BOM中途均及时拒绝或明确处理
- **原生回归**：`test.py`。

## 18．CLI机器可读结果

- **来源／场景**：目录工具不能解析自然语言with confidence输出；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/cli/chardetect.py)。
- **原版缺口**：冻结5.2 CLI只输出描述或minimal；后续已取证CLI同样未提供JSON选项
- **交付及模块**：增加JSON/JSONL输出及明确状态字段，保留原文本模式；`chardet/cli/chardetect.py:main`, `chardet/cli/chardetect.py:description_of`。
- **兼容与实际依赖**：不把无法检测作为执行崩溃；stdout只放所选格式，诊断走stderr；步骤依赖：无。
- **正常验收**：两个文件产生两条带路径/候选/状态的可解析结果
- **异常／边界验收**：Unicode路径、None编码、stdin、读取失败和不同输出模式冲突给明确退出码
- **原生回归**：`test.py`。

## 19．本地目录筛选扫描

- **来源／场景**：档案目录多层且含无关文件，需要稳定筛选；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/cli/chardetect.py)。
- **原版缺口**：CLI接受显式文件列表，无递归目录、排除模式和逐文件失败汇总合同
- **交付及模块**：增加只读目录扫描，按路径顺序与大小/后缀规则产出结果；`chardet/cli/chardetect.py:main`。
- **兼容与实际依赖**：已有显式文件行为保持；不跟随目录外链接作为默认；不写归档内容；步骤依赖：无。
- **正常验收**：递归只选择指定文本后缀，结果顺序与筛选计数正确
- **异常／边界验收**：空目录、不可读文件、符号链接循环、重复路径及取消保留已完成项
- **原生回归**：`test.py`。

## 20．经验证的本地转码助手

- **来源／场景**：检测后需把归档转UTF8并保留原文件；[固定源码](https://github.com/chardet/chardet/blob/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1/chardet/__init__.py)。
- **原版缺口**：核心只给编码结果，调用方自行decode/encode及管理文件；没有transcode_file
- **交付及模块**：新增显式目标路径/codec/错误策略的本地转码，记录检测、验证与写入三个状态；`chardet/__init__.py:detect`, `chardet/cli/chardetect.py`。
- **兼容与实际依赖**：默认strict不丢字符；不覆盖输入，显式原子替换才允许改目标；不承诺猜测永远准确；步骤依赖：09。
- **正常验收**：已验证cp1252文件转UTF8后文字一致，原文件不变
- **异常／边界验收**：未知codec、低置信、全文验证失败、BOM策略、写满与路径冲突不留下假成功文件
- **原生回归**：`test.py`。
