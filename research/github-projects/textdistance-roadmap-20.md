# textdistance：二十步真实工程迭代路线

固定 [life4/textdistance@d6a68d61088a40eef5c88191ccf79323dbf34850](https://github.com/life4/textdistance/tree/d6a68d61088a40eef5c88191ccf79323dbf34850)，原生证据见 [单仓审查](./textdistance.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．LCS自定义相等谓词一致

- **来源／场景**：忽略字母大小写比较最长公共子序列；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/sequence_based.py)。
- **原版缺口**：LCSSeq两输入_dynamic直接用==而三输入_recursive用test_func；实测A/a为无公共序列，A/a/A为A
- **交付及模块**：让两条实现路径遵守同一公开test_func合同，并定义等价字符返回哪方原字符；`textdistance/algorithms/sequence_based.py:LCSSeq`。
- **兼容与实际依赖**：默认==结果保持；不把相等类代表值强行转小写；同一hook错误一次修复；步骤依赖：无。
- **正常验收**：大小写不敏感谓词下两/多序列都得到一致长度及正确原字符子序列
- **异常／边界验收**：非传递谓词、重复字符、空输入、numpy可选路径与重建阶段均按约定处理
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 02．词与qgram序列结果合同

- **来源／场景**：qval=2比较文档片段，希望LCS返回匹配单位；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/sequence_based.py)。
- **原版缺口**：LCSSeq把tuple与str相加报错；LCSStr短输入返回qgram列表、长输入join tuple报错，实测均保留
- **交付及模块**：统一序列类算法的准备后单位与结果重建，明确字符/词/qgram输出形式；`textdistance/algorithms/sequence_based.py:LCSSeq`, `textdistance/algorithms/sequence_based.py:LCSStr`, `textdistance/algorithms/base.py:_get_sequences`。
- **兼容与实际依赖**：这是准备/重建合同的一项完整修复，不拆长短或两种算法测试维度；默认字符字符串输出保持；步骤依赖：无。
- **正常验收**：词级与qgram级LCS产生声明的序列结果，长短路径一致且similarity按单位数计
- **异常／边界验收**：空gram、长度跨200路径边界、列表token及不可拼接token不发生隐式str转换
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 03．单词排列助手可调用

- **来源／场景**：用公开words_combinations配合内建Levenshtein比较颠倒词序；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/utils.py)。
- **原版缺口**：助手访问f.equality，但内建距离类没有该属性；实跑AttributeError
- **交付及模块**：定义标准callable/方向/等长政策并移除不存在属性假设，同时提供排列预算；`textdistance/utils.py:words_combinations`。
- **兼容与实际依赖**：不把穷举默认称为可扩展检索；兼容显式自定义callable；不能把相似度直接当最小距离；步骤依赖：无。
- **正常验收**：guide archive与archive guide用距离函数得到0，普通callable也能运行
- **异常／边界验收**：空文本、重复词、超过排列预算、相似度方向和多文本组有明确结果/停止状态
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 04．带权编辑距离

- **来源／场景**：OCR整理中插入、删除和某些替换代价不同；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/edit_based.py)。
- **原版缺口**：Levenshtein只有布尔test_func，不能表达不同非零编辑成本；NeedlemanWunsch是已有评分替代但非同一距离合同
- **交付及模块**：新增WeightedLevenshtein，支持明确插入/删除/替换成本或受限回调；`textdistance/algorithms/edit_based.py:Levenshtein`。
- **兼容与实际依赖**：默认Levenshtein单位成本不变；非对称成本不标为metric；归一化需单独定义上界；步骤依赖：无。
- **正常验收**：手算小例与动态规划最小成本相符，单位成本等于原函数
- **异常／边界验收**：负成本拒绝、零成本、浮点容差、非对称与自定义相等谓词有完整边界
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 05．可重放编辑操作

- **来源／场景**：文档差异展示不能只有距离整数；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/edit_based.py)。
- **原版缺口**：编辑算法返回分数，无edit_script/alignment操作列表；调用方可另用其他库
- **交付及模块**：新增确定性编辑脚本，首版支持Levenshtein与明确的转置模式，保留源/目标区间；`textdistance/algorithms/edit_based.py:Levenshtein`, `textdistance/algorithms/edit_based.py:DamerauLevenshtein`。
- **兼容与实际依赖**：距离接口不变；相同最小分数的多脚本采用公开tie-break，不声称唯一答案；步骤依赖：无。
- **正常验收**：脚本重放可把原文变目标文，操作成本和对应距离一致
- **异常／边界验收**：重复字符、空串、转置与相等谓词、Unicode及多个最优解各有稳定结果
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 06．带截断阈值的距离

- **来源／场景**：只需判断距离是否大于2，不想计算完整长矩阵；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/edit_based.py)。
- **原版缺口**：公开调用没有score_cutoff，外部后端虽可能支持但adapter未透传
- **交付及模块**：新增bounded_distance，对支持算法用正确下界剪枝，返回精确值或明确超过阈值状态；`textdistance/algorithms/edit_based.py:Levenshtein`, `textdistance/algorithms/base.py:Base`。
- **兼容与实际依赖**：不支持剪枝的算法可明确回退全算；不能把截断哨兵当真实距离；默认接口保持；步骤依赖：无。
- **正常验收**：阈内距离与原版相同，阈外明确greater-than而非随意分数
- **异常／边界验收**：阈值0/负数、长度差下界、归一化阈值、backend差异及边界恰等均验收
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 07．文档内近似片段定位

- **来源／场景**：在较长正文里定位有一处拼写差异的短标题；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/edit_based.py)。
- **原版缺口**：已有LCSStr找精确公共子串，不等于模糊子串匹配；无best_substring
- **交付及模块**：新增明确编辑距离模式的近似子串定位，返回区间、匹配文字和分数；`textdistance/algorithms/edit_based.py:Levenshtein`, `textdistance/algorithms/sequence_based.py:LCSStr`。
- **兼容与实际依赖**：不改变精确LCSStr；空模式与多个并列最佳位置有显式政策；步骤依赖：无。
- **正常验收**：短标题在前后有正文且一字误写时找到正确范围
- **异常／边界验收**：多个同分位置、无阈内命中、Unicode、词级单位和超预算文本不伪造完整最优
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 08．可说明的Unicode预处理

- **来源／场景**：同一文档标题有NFC/NFD、大小写或可见字素差异；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/base.py)。
- **原版缺口**：算法默认比较原序列，调用方可手动normalize/casefold，qval处理码点/空格词，缺统一审查式管线
- **交付及模块**：增加opt-in预处理配置，支持NFC、casefold与可选字素分段，并记录变换；`textdistance/algorithms/base.py:_get_sequences`, `textdistance/utils.py`。
- **兼容与实际依赖**：默认逐码点结果保持；不默认去音调或改变词义；字素依赖版本单列；步骤依赖：无。
- **正常验收**：预组合/组合é在NFC模式一致，字素模式不拆emoji序列
- **异常／边界验收**：土耳其字母、德文ß、零宽字符、空输入和归一化改变长度时保留原文映射
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 09．可复用已准备序列

- **来源／场景**：同一个标题要与几千个候选比较，不应反复切qgram/建Counter；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/base.py)。
- **原版缺口**：每次_get_sequences/_get_counters重新准备，无PreparedSequence公共合同
- **交付及模块**：新增不可变准备对象，保存单位策略与可懒建的Counter/表示，供明确兼容的算法复用；`textdistance/algorithms/base.py:_get_sequences`, `textdistance/algorithms/base.py:_get_counters`。
- **兼容与实际依赖**：不能把qval不同的表示串用；原字符串/序列入口保持；不强制安装numpy；步骤依赖：无。
- **正常验收**：准备查询后批量分数与逐次原API相同，可观察准备次数减少
- **异常／边界验收**：外部原列表修改、as_set差异、不可hash token、不同预处理配置与版本都要验证
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 10．显式后端策略与执行说明

- **来源／场景**：可复现研究需知道使用纯Python还是哪个可选库；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/base.py)。
- **原版缺口**：external=True只自动尝试已注册库，异常被静默略过；没有按名称固定与解释的合同
- **交付及模块**：新增BackendPolicy，支持auto/pure/指定库及严格或回退模式，返回实际选择原因；`textdistance/algorithms/base.py:external_answer`, `textdistance/libraries.py:LibrariesManager`。
- **兼容与实际依赖**：external布尔接口兼容；自定义test_func不支持外部时不能绕过；不改变默认分数；步骤依赖：无。
- **正常验收**：指定rapidfuzz时实际执行该适配，pure时不导入外部后端，结果符合原语义
- **异常／边界验收**：库缺失/版本不兼容、输入条件不符、后端抛错及fallback都清楚区分
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 11．有序TopK候选检索

- **来源／场景**：从文档标题集合找最相近的几项；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/base.py)。
- **原版缺口**：只提供距离/相似度原语，无extract的ID、阈值、tie-break与错误政策
- **交付及模块**：新增extract/topK接口，保留候选ID/原值/分数，允许惰性输入和工作预算；`textdistance/algorithms/base.py:Base`, `textdistance/utils.py`。
- **兼容与实际依赖**：不改变底层评分；明确距离越低/相似度越高；不把集合重复项默默合并；步骤依赖：无。
- **正常验收**：三个候选按所选metric准确排名，k=1与手动穷举一致
- **异常／边界验收**：同分顺序、k=0/负数、坏记录、重复值、空候选及取消明确处理
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 12．分块两两比较

- **来源／场景**：本地数据清理需要相似度矩阵，但大矩阵不能一次分配；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/base.py)。
- **原版缺口**：无pairwise_blocks，调用方只能双重循环并自管内存/索引
- **交付及模块**：新增分块矩阵迭代，支持上三角优化、明确输出dtype和可选numpy；`textdistance/algorithms/base.py:Base`, `textdistance/algorithms/token_based.py`。
- **兼容与实际依赖**：只有声明对称的metric才复用三角；不强制计算全量；默认单比较不变；步骤依赖：无。
- **正常验收**：拼接小块矩阵与手工所有配对一致，行列ID保持
- **异常／边界验收**：非对称metric、空集合、尾块、浮点NaN与预算中断不把未算格填成合法零值
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 13．满足度量条件的索引

- **来源／场景**：大量固定标题要反复进行小半径搜索；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/edit_based.py)。
- **原版缺口**：当前没有MetricIndex，算法也不都满足三角不等式
- **交付及模块**：新增明确受限的度量索引，首版支持可证明的单位Levenshtein，结果可用穷举对照；`textdistance/algorithms/edit_based.py:Levenshtein`, `textdistance/algorithms/base.py`。
- **兼容与实际依赖**：不把Jaro等相似度直接塞入度量剪枝；索引保存metric配置与token策略；步骤依赖：无。
- **正常验收**：半径搜索结果与相同库/阈值穷举完全一致，支持重复值不同ID
- **异常／边界验收**：空索引、插入删除、metric变更、非度量配置和距离边界均明确拒绝/重建
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 14．重复文档分组

- **来源／场景**：清单里需要把相似标题组织成可审查组；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/base.py)。
- **原版缺口**：距离原语无duplicate_groups的分组语义，连通分量与两两相似不是一回事
- **交付及模块**：提供显式single-link/complete-link政策的重复组提案，保留每条边证据；`textdistance/algorithms/base.py`, `textdistance/utils.py`。
- **兼容与实际依赖**：不自动删除文档；不声称A近B且B近C就证明A近C；阈值由调用方选择；步骤依赖：无。
- **正常验收**：简单近似组与独立项按政策分开，组内对应比较可查询
- **异常／边界验收**：链式相似、同分、重复ID、阈值极端和不完整预算组都有明确状态
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 15．多字段记录比较

- **来源／场景**：文档元数据的标题、作者、年份需不同权重比较；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/base.py)。
- **原版缺口**：库只比较序列，不提供字段映射/缺失值/权重解释的RecordMatcher
- **交付及模块**：新增声明式记录匹配器，逐字段选metric与预处理，输出总分及分项；`textdistance/algorithms/base.py`, `textdistance/algorithms/token_based.py`。
- **兼容与实际依赖**：不把缺字段直接当空串，权重归一化和非对称方向明确；不自动合并记录；步骤依赖：无。
- **正常验收**：标题相近、作者一致、年份不同的合成记录得到可手算分项和总分
- **异常／边界验收**：全缺字段、权重为零/负数、非法字段值和字段metric范围不兼容有精确错误
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 16．语料权重的词向量比较

- **来源／场景**：文档集合中常见词不应与独特术语有同样权重；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/token_based.py)。
- **原版缺口**：Cosine对提供token频率比较，库没有拟合语料IDF的TfidfScorer
- **交付及模块**：新增可冻结的语料词表/IDF模型及相似度接口，明确平滑、未知词和版本；`textdistance/algorithms/token_based.py:Cosine`, `textdistance/algorithms/base.py:_get_counters`。
- **兼容与实际依赖**：不改变现有Cosine公式；不是语言模型训练；模型只由显式本地语料统计构成；步骤依赖：无。
- **正常验收**：小语料手算TF-IDF与输出一致，冻结模型重复得分相同
- **异常／边界验收**：空文档、全未知词、零向量、重复文档与更新语料后模型版本变化均可检验
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 17．算法能力元数据

- **来源／场景**：用户选择算法时需知道范围、方向及能否用于索引；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/base.py)。
- **原版缺口**：Base有distance/similarity/normalized接口，但各算法范围/metric性质与多输入支持分散在实现
- **交付及模块**：增加只读能力registry，说明支持输入、方向、范围、对称性、metric条件和backend；`textdistance/algorithms/base.py`, `textdistance/algorithms/edit_based.py`, `textdistance/algorithms/token_based.py`。
- **兼容与实际依赖**：不把所有normalized方法视为经过概率校准；有条件性质必须携带条件，不凭少量测试宣称数学性质；步骤依赖：无。
- **正常验收**：标准Levenshtein、非对称Tversky及压缩距离各得到符合实现的能力说明
- **异常／边界验收**：自定义test_func、权重、qval及用户算法无法证明时标unknown，不错误放行索引
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 18．词级匹配解释

- **来源／场景**：MongeElkan分数需说明每个查询词对应哪个候选词；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/algorithms/token_based.py)。
- **原版缺口**：MongeElkan内部取最大词相似度，公开只给聚合分数，没有token_alignment结果
- **交付及模块**：增加可选词对齐解释，保留每个词的候选、分数、并列规则与聚合方式；`textdistance/algorithms/token_based.py:MongeElkan._calc`。
- **兼容与实际依赖**：不改变原MongeElkan方向性或把多词匹配误当一对一；字符编辑脚本是另一种结果；步骤依赖：无。
- **正常验收**：给两个多词标题，解释分项聚合等于原分数
- **异常／边界验收**：重复词、一词匹配多个位置、空集合、对称模式和并列最佳均明确标记
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 19．安装与运行版本一致

- **来源／场景**：诊断兼容问题时module版本和包元数据需一致；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/__init__.py)。
- **原版缺口**：固定源码__version__=4.6.2而setup.py version=4.6.3，实跑两者不同
- **交付及模块**：统一版本来源，构建元数据与导入值一致并保留现有VERSION别名；`textdistance/__init__.py`, `setup.py`。
- **兼容与实际依赖**：不把新版本号自动用于发布；本路线只修一致性，不提交tag或包分发；步骤依赖：无。
- **正常验收**：从固定工程构建/安装后importlib.metadata.version等于__version__/VERSION
- **异常／边界验收**：源码未安装、无git标签构建、sdist/wheel与editable安装均有明确版本策略
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。

## 20．普通文本比较CLI

- **来源／场景**：文档维护者希望终端比较两份显式文本或本地文件；[固定源码](https://github.com/life4/textdistance/blob/d6a68d61088a40eef5c88191ccf79323dbf34850/textdistance/__init__.py)。
- **原版缺口**：公开API没有用户比较CLI，README示例需Python调用
- **交付及模块**：新增明确输入模式、metric/单位配置和机器可读结果的本地命令；`textdistance/__init__.py`, `textdistance/algorithms/base.py`, `setup.py`。
- **兼容与实际依赖**：不将输入字符串当代码执行；默认不读隐含路径；API与metric公式不变；步骤依赖：无。
- **正常验收**：显式两文本或两UTF8文件得到和原API相同分数及配置摘要
- **异常／边界验收**：未知metric、解码错、阈值错误、空输入、stdin冲突和输出格式都给稳定退出码
- **原生回归**：`tests/test_common.py`, `tests/test_external.py`, `tests/test_edit/test_levenshtein.py`, `tests/test_sequence/test_lcsseq.py`, `tests/test_sequence/test_lcsstr.py`, `tests/test_token/test_monge_elkan.py`。
