# cssselect：二十步真实工程迭代路线

固定 [scrapy/cssselect@3069b6da75e1adf27939ca541dcc9fb9b961abc6](https://github.com/scrapy/cssselect/tree/3069b6da75e1adf27939ca541dcc9fb9b961abc6)，原生证据见 [单仓审查](./cssselect.md)。以下均为逐仓分析提出的本地工程增强提案，尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．选择器列表取反

- **来源／场景**：文档转存时排除广告节点或导航节点，需要 :not(aside, nav)；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/parser.py)。
- **原版缺口**：parse_simple_selector 只接收一个 :not 参数；原版 :not(a, b) 抛 SelectorSyntaxError，文档明确限制；可用多个 :not 串联替代
- **交付及模块**：将 :not 列表作为一个完整能力，解析各分支并对匹配条件取反，canonical 和 specificity 同步；`cssselect/parser.py:Negation`, `cssselect/xpath.py:xpath_negation`。
- **兼容与实际依赖**：旧单参数输出保持；不同时开放嵌套 :not 或伪元素；步骤依赖：无。
- **正常验收**：给含 a、b、p 的 XML，:not(a,b) 只保留 p 及匹配作用域中其他元素
- **异常／边界验收**：空列表、末尾逗号和伪元素参数稳定拒绝；组合复杂分支不改变原有单参数语义
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 02．is 与 where 的复杂分支

- **来源／场景**：文档模板合并 main > p、article p 两套结构；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/parser.py)。
- **原版缺口**：公开说明只允许 compound selector；:is(main > p, article p) 原版解析失败；可改写成顶层选择器并集
- **交付及模块**：让 is/where 参数可含组合符，复用反向匹配条件而非把前向 XPath 填入谓词；保留二者不同 specificity；`cssselect/parser.py:parse_simple_selector_arguments`, `cssselect/xpath.py:_xpath_add_selector_list_condition`。
- **兼容与实际依赖**：不改变顶层 union、既有 compound 分支和 where 零 specificity；步骤依赖：无。
- **正常验收**：混合 main 子节点和 article 后代的实际树匹配与展开并集一致
- **异常／边界验收**：相邻／兄弟分支、无命中、空参数及非法伪元素按明确定义处理；未开放的 scope 仍拒绝
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 03．按筛选子集计算 nth-child

- **来源／场景**：目录中只对 class=active 的列表项编号；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/parser.py)。
- **原版缺口**：li:nth-child(2 of .active) 在 parse_arguments 遇到点时失败；原版 nth-child 按所有兄弟计数
- **交付及模块**：增加 of selector-list 的结构节点并按已筛选的兄弟集合计数，含 nth-last-child 对称能力；`cssselect/parser.py:parse_arguments`, `cssselect/xpath.py:xpath_nth_child_function`。
- **兼容与实际依赖**：没有 of 的所有 An+B 结果不变；首版仅接收可嵌入 XPath1 谓词的 compound 列表；步骤依赖：无。
- **正常验收**：交错 active 与非 active 的列表准确选择第二个 active 项并验证倒数方向
- **异常／边界验收**：0、负系数、无符合项、多分支去重与不支持复杂筛选明确验收；不默默按全体兄弟计数
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 04．多语言范围匹配

- **来源／场景**：离线站点抽取希望一个 :lang(en, zh-*) 覆盖多语内容；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/parser.py)。
- **原版缺口**：HTML xpath_lang_function 只接受单一 IDENT/STRING；原版逗号触发语法错误；可顶层并集替代
- **交付及模块**：一次交付语言范围列表与扩展通配范围匹配，解析范围后按最近继承 lang 合并判断；`cssselect/parser.py:parse_arguments`, `cssselect/xpath.py:HTMLTranslator.xpath_lang_function`。
- **兼容与实际依赖**：单一 en 对 en-US 的旧行为不变；XML xml:lang 与 HTML lang 各用对应属性；步骤依赖：无。
- **正常验收**：en、zh-Hant 与继承 zh-CN 节点按范围入选
- **异常／边界验收**：空 lang 覆盖继承、大小写、无属性、非法范围、空列表和 xml:lang 使用各有断言
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 05．静态文档方向选择

- **来源／场景**：排版转换从含 dir 属性的 HTML 提取从右向左段落；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：原版 :dir(rtl) 抛 ExpressionError，只有普通属性选择器可用，不能表达继承
- **交付及模块**：提供 HTMLTranslator 的静态 dir 继承实现，明确 dir=auto 不依赖浏览器布局；auto 按文本首个强方向字符计算或明确排除；`cssselect/xpath.py:HTMLTranslator`, `cssselect/parser.py:Function`。
- **兼容与实际依赖**：GenericTranslator 仍报不支持；首版仅支持 ltr/rtl 和显式可推导的静态快照，auto 的完整 Unicode 算法不伪装成 XPath1 能力；步骤依赖：无。
- **正常验收**：显式 rtl、继承 rtl、子级 ltr 覆盖及无方向默认策略均正确
- **异常／边界验收**：未知参数、dir=auto 和无强方向文字明确返回不支持范围诊断；不静默命中错误方向
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 06．静态链接集合伪类

- **来源／场景**：文档链接清单要同时选择可访问和未访问状态不相关的链接；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：原版 :any-link 未知；HTMLTranslator 已有 :link，缺少标准名称且历史状态不存在
- **交付及模块**：在 HTMLTranslator 提供 any-link，与静态 href 元素资格规则一致；文档说明不读取访问历史；`cssselect/xpath.py:HTMLTranslator.xpath_link_pseudo`。
- **兼容与实际依赖**：旧 :link、:visited 的结果完全不变；XML translator 不猜测链接语义；步骤依赖：无。
- **正常验收**：a、area、link 具有 href 时按定义选中，非链接元素 href 不误选
- **异常／边界验收**：缺少 href、空 href、命名空间 XHTML、大小写属性及非 HTML 文档分别验证
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 07．表单必填状态

- **来源／场景**：离线表单盘点要区分 required 与 optional 控件；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：原版 :required 抛未知伪类；单纯 [required] 会误包含不适用 input 类型和任意元素
- **交付及模块**：一次增加 required/optional 互补静态状态，并实现 input、select、textarea 的 HTML 资格；`cssselect/xpath.py:HTMLTranslator`。
- **兼容与实际依赖**：不推断浏览器即时校验有效性；已有 enabled/disabled/checked 不变；步骤依赖：无。
- **正常验收**：普通文本、checkbox、select 与 textarea 的 required 状态正确
- **异常／边界验收**：hidden/button 等不适用类型、禁用字段及任意 div required 不误判；缺失 type 按 text
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 08．静态可编辑状态

- **来源／场景**：编辑器导出需要识别文本输入和 contenteditable 区域；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：原版 :read-write 未知；普通属性筛选不足以表达继承和 readonly
- **交付及模块**：一次提供 read-write/read-only，并明确 contenteditable 的继承、false 覆盖及表单类型规则；`cssselect/xpath.py:HTMLTranslator`。
- **兼容与实际依赖**：只基于文档静态属性；不模拟设计模式或运行中脚本；XML 保持未知；步骤依赖：无。
- **正常验收**：可编辑容器后代、readonly 文本输入与 textarea 互补结果符合定义
- **异常／边界验收**：contenteditable=false 嵌套覆盖、disabled、非文本 input、未知属性值和 XHTML 有边界用例
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 09．占位文字显示的快照策略

- **来源／场景**：表单截图预处理要提取当前只显示 placeholder 的文本控件；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：原版 :placeholder-shown 未知；无 live value 入口，只能从属性近似，不能声称完整浏览器状态
- **交付及模块**：增加显式 snapshot 模式，可从调用方提供的控件 value 映射判断 placeholder-shown；未提供时仅支持注明属性快照近似模式；`cssselect/xpath.py:HTMLTranslator`。
- **兼容与实际依赖**：默认 translator 不自动假定 DOM 属性等于运行时值；新增模式与普通 XPath字符串接口分离；步骤依赖：无。
- **正常验收**：给 text input 与 textarea 的明确值快照，空值且非空占位文本入选
- **异常／边界验收**：缺失快照值、空 placeholder、非适用 input、value 与 text 冲突明确报告；不把不确定状态当命中
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 10．表单初始默认项

- **来源／场景**：表单差异报告要标出初始 checkbox、option 和默认提交按钮；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：原版 :default 未知；:checked 只表达 checked/selected 资格而非默认按钮
- **交付及模块**：一次交付静态默认状态，规则包含初始选中项和按 form owner 关联的默认提交按钮；`cssselect/xpath.py:HTMLTranslator`。
- **兼容与实际依赖**：当前 checked 结果保持；不模拟点击和运行后状态；需要节点关联时使用明确选择计划接口；步骤依赖：无。
- **正常验收**：同 form 的首个 submit 与初始 selected、checked 成员准确识别
- **异常／边界验收**：form 属性关联、外置按钮、禁用按钮、未显式选择的单选 select 与无表单控件按约定验证
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 11．不确定表单状态快照

- **来源／场景**：状态报告需标注无选中项的 radio 组、无 value 的 progress 与明确 indeterminate checkbox；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：原版 :indeterminate 未知，属性不存在不等于所有控件均确定
- **交付及模块**：增加静态可推导 radio/progress 状态与显式 checkbox 快照输入，形成一个完整状态选择能力；`cssselect/xpath.py:HTMLTranslator`。
- **兼容与实际依赖**：不凭 HTML checked 属性推测 checkbox 运行时 indeterminate；显式输入与第09步快照可复用但可独立实现；步骤依赖：无。
- **正常验收**：同 form 同 name radio 全部未选中、无 value progress 及显式 checkbox 状态命中
- **异常／边界验收**：不同 form 同 name 不混组，value=0 progress 不误选；缺失 checkbox 状态明确未知
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 12．可复用编译对象

- **来源／场景**：同一文档选择器在多个 XML 树执行，调用者希望一次处理解析、specificity 和翻译配置；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/__init__.py)。
- **原版缺口**：公开 parse 和 css_to_xpath 分开返回可变树／字符串，无 compile_selector；调用者可自行组合
- **交付及模块**：提供不可变编译结果，保存 canonical、specificity、XPath、模式和前缀，不隐式绑定 lxml 文档；`cssselect/__init__.py`, `cssselect/parser.py:Selector`, `cssselect/xpath.py:GenericTranslator`。
- **兼容与实际依赖**：既有字符串 API 不变，编译结果不强制引入 lxml 运行依赖；不包含第17步缓存策略；步骤依赖：无。
- **正常验收**：同一编译结果在两个不同树由调用者 XPath 求值，结果与原 API 一致
- **异常／边界验收**：不同 HTML/XML 模式和前缀不串用；伪元素仍按显式策略拒绝；对象不可被调用方改写共享状态
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 13．带源码位置的诊断

- **来源／场景**：模板作者需准确定位无效选择器字符，编辑器不能解析英文异常字符串；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/parser.py)。
- **原版缺口**：原版仅抛 SelectorSyntaxError/ExpressionError；Token 有 pos 但无 diagnose 结构化入口
- **交付及模块**：返回阶段、错误码、字符跨度与建议，翻译不支持与语法错误分开；保留异常 API；`cssselect/parser.py:TokenStream`, `cssselect/parser.py:SelectorSyntaxError`, `cssselect/xpath.py:ExpressionError`。
- **兼容与实际依赖**：旧异常类型与主要消息兼容；建议不自动改写用户规则；步骤依赖：无。
- **正常验收**：未闭合属性、错误组合符、未知伪类分别得到正确阶段和跨度
- **异常／边界验收**：多行、Unicode、EOF 零宽位置及空字符串可稳定定位；诊断成功不声称运行时一定有匹配
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 14．批量选择器翻译报告

- **来源／场景**：迁移几百条文档抽取规则时需一次获得全部成功和失败明细；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：css_to_xpath 面向一个 group，某一项异常即终止；没有 translate_many；可调用方循环
- **交付及模块**：增加有序逐记录批量结果，保留调用方标识与局部错误，不把多个输入简单拼成一个 CSS group；`cssselect/xpath.py:GenericTranslator`, `cssselect/__init__.py`。
- **兼容与实际依赖**：单输入 API 和 group 内语法保持；提供 fail-fast 选项且默认结果顺序稳定；步骤依赖：无。
- **正常验收**：三条规则一条失败仍交付其余两条 XPath 并保留原标识
- **异常／边界验收**：空批次、重复输入、惰性迭代器中断及 group 字符串内逗号不错误拆分
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 15．稳定的选择器树导出

- **来源／场景**：规则编辑器需展示层级并保存可版本化的 AST，不依赖 repr；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/parser.py)。
- **原版缺口**：Selector 暴露 parsed_tree/canonical/specificity 但没有 selector_to_json；内部树类型不是持久化协议
- **交付及模块**：提供只读、带 schema 版本的 AST 导出，包含组合符、命名空间、属性flags、伪函数及 specificity；`cssselect/parser.py:Selector`, `cssselect/parser.py:Attrib`, `cssselect/parser.py:Relation`。
- **兼容与实际依赖**：只做导出，首版不开放任意 JSON 反序列化；canonical 继续是 CSS 输出；步骤依赖：无。
- **正常验收**：复杂 :has、属性 i 标记和命名空间能完整导出并可由 JSON 序列化器编码
- **异常／边界验收**：转义 Unicode、伪元素、空名字空间和未知自定义节点明确标记，避免静默丢信息
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 16．可观测解析工作预算

- **来源／场景**：交互式规则编辑器需要把解析延迟和表达式规模控制在约定的普通工作负载；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/parser.py)。
- **原版缺口**：parse 只有 css 参数；TokenStream 连续解析，没有 ParseBudget，调用方只能外部限制字符串长度
- **交付及模块**：可选预算同时覆盖 token、树节点与嵌套深度，返回专属资源边界错误并报告消耗；`cssselect/parser.py:parse`, `cssselect/parser.py:TokenStream`。
- **兼容与实际依赖**：不设置预算时保持现有正常输入；这不是独立安全产品或网络功能，只是本地可用性边界；步骤依赖：无。
- **正常验收**：预算恰好足够时结果与原版一致，超一单位时有一致错误及消耗
- **异常／边界验收**：简单选择器快速路径同样计量，嵌套函数和多分支累计共享预算，不因入口不同漏计
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 17．有界且可失效的翻译缓存

- **来源／场景**：大量相同模板选择规则在本地批处理反复转换，需要测量及控制缓存占用；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：原版 css_to_xpath 每次 parse，无公开 SelectorCache；调用方可 functools 缓存字符串
- **交付及模块**：独立缓存服务支持容量、统计、清空；缓存键包含 translator 类型、配置、前缀及扩展版本；`cssselect/xpath.py:GenericTranslator`, `cssselect/__init__.py`。
- **兼容与实际依赖**：默认 API 不强制启用缓存；自定义 translator 没有稳定配置指纹时拒绝共享缓存；步骤依赖：无。
- **正常验收**：重复规则命中，达到容量后淘汰最旧访问项，清空后重新翻译
- **异常／边界验收**：HTML/XML、xhtml、前缀和不同注册扩展不共享结果；失败结果默认不缓存
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 18．本地选择器检查命令

- **来源／场景**：文档维护者希望终端检查一个 CSS 选择器并获得 XPath 与 specificity；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/__init__.py)。
- **原版缺口**：包没有 __main__.py 及命令入口；需自行写 Python 小脚本
- **交付及模块**：增加 python -m cssselect 的本地 stdin/参数入口，可选 JSON 与 HTML/XML 模式，不下载页面；`cssselect/__init__.py`, `cssselect/xpath.py:GenericTranslator`, `pyproject.toml`。
- **兼容与实际依赖**：只处理显式输入文本，默认不抓取 URL；Python API 及默认安装依赖不变；步骤依赖：无。
- **正常验收**：参数输入与 stdin 同规则产生同 XPath，JSON 含 canonical 与 specificity，成功 exit0
- **异常／边界验收**：无输入、语法错误、未知伪类 exit 非零且错误只走 stderr；stdout 不夹日志
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 19．显式注册自定义伪类

- **来源／场景**：内部文档标记 :reviewed 的扩展要在多个 translator 之间独立配置；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/xpath.py)。
- **原版缺口**：现有替代方式是 subclass 覆盖 xpath_<name>；文档提示定制 API 不稳定；没有 register_pseudo
- **交付及模块**：提供实例级插件注册契约，分静态与函数伪类，带参数校验、能力声明和版本指纹；`cssselect/xpath.py:GenericTranslator.xpath_pseudo`, `cssselect/xpath.py:GenericTranslator.xpath_function`。
- **兼容与实际依赖**：不替换现有 subclass 机制；默认不能覆盖内建名字，实例间隔离，不加载远程插件；步骤依赖：无。
- **正常验收**：注册 reviewed 属性谓词，翻译后在 XML 上选出正确节点；函数插件收到已解析参数
- **异常／边界验收**：重复注册、内建冲突、插件返回错误类型及参数数量错误有一致诊断；旧实例不受新实例注册影响
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。

## 20．公开 CSS 标识符转义

- **来源／场景**：从文档实际 class 或 id 构造选择器时，维护者不应依赖下划线私有函数；[固定源码](https://github.com/scrapy/cssselect/blob/3069b6da75e1adf27939ca541dcc9fb9b961abc6/cssselect/parser.py)。
- **原版缺口**：内部 _serialize_ident 已实现转义并用于 canonical；公开 __all__ 无 escape_identifier，调用方可拼属性选择器或自行实现
- **交付及模块**：将现有算法以明确 public escape_identifier 合同开放并补类型、文档与往返保证；不重复实现另一算法；`cssselect/parser.py:_serialize_ident`, `cssselect/__init__.py`。
- **兼容与实际依赖**：只转义单个标识符，不接受整条选择器；保留原 canonical 输出以及现有 NUL 替换语义；步骤依赖：无。
- **正常验收**：空格、冒号、数字开头、中文等 ID 转义后交 parse，再由 XPath选中原始目标
- **异常／边界验收**：单横线、连续横线、控制字符、NUL 替换和后接十六进制字符有精确断言；空串明确拒绝或记录不可构成标识符
- **原生回归**：`tests/test_cssselect.py`, `docs/conftest.py`。
