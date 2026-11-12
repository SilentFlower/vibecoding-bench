# packaging 二十步迭代研究路线

固定[pypa/packaging@1a62a26afe0f4881593e31bed4f7753bd1c8fe27](https://github.com/pypa/packaging/tree/1a62a26afe0f4881593e31bed4f7753bd1c8fe27)。20项全为本地增强提案，未实施、未由上游承诺。历史兼容行为不武断称为BUG。原版场景结果与源码缺口均保存于本地observations-result.json。
已排除当前源码已有的Version.from_parts、VersionRange集合代数、Marker的&/|、Metadata.as_rfc822、DirectUrl、Pylock.select、Requirement.__replace__、interpreter_abi/platform_tags及兼容tag选择器。

## 01．版本对象可保留原始展示拼写

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/1418)；CalVer项目希望展示2026.01.01，同时按PEP440比较版本。
- **原版现状／已有替代**：Version实跑规范化为2026.1.1，无raw_version；当前可在应用另存原字符串。from_parts已经存在，不重复新增。
- **交付与模块**：增加只读原始拼写信息或独立展示包装器，并定义从parts/replace产生对象的原始值。；`src/packaging/version.py`。
- **兼容边界**：str/排序/相等/hash继续规范化；不把原始拼写写入比较键。
- **正常验收**：从2026.01.01构造后能取回原文且等于Version(2026.1.1)。
- **异常／边界验收**：空白、前导v、local大小写、pickle旧格式、from_parts和replace后无原文的明确表示。
- **原生回归**：`tests/test_version.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 02．Marker显式使用完整外部环境

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/431)；跨平台构建器只使用声明的目标环境，不能从研究主机补入未提供的Python信息。
- **原版现状／已有替代**：evaluate(environment)实为default_environment再覆盖，缺python_version仍读到宿主信息；没有替换模式。
- **交付与模块**：新增opt-in环境替换/严格模式，缺引用变量时抛UndefinedEnvironmentName。；`src/packaging/markers.py`。
- **兼容边界**：默认覆盖模式保持；context的extra/extras默认值规则另行明确；不改变允许的标准变量集合。
- **正常验收**：严格模式只给os_name却引用python_version时拒绝，完整目标环境得到稳定结果。
- **异常／边界验收**：空映射、None、Python dev版本修复、lock_file集合变量及调用方映射不被修改。
- **原生回归**：`tests/test_markers.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 03．公开只读Marker语法树和遍历协议

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/496)；工具从依赖声明提取Python条件并生成其他包系统的依赖说明。
- **原版现状／已有替代**：公开Marker只有字符串/evaluate/组合等入口，树位于私有_markers；没有稳定AST协议。
- **交付与模块**：增加不可变节点模型与只读访问/visitor，表达变量、值、比较和布尔分组。；`src/packaging/markers.py`、`src/packaging/_parser.py`。
- **兼容边界**：不暴露可修改内部缓存；保持字符串与pickle契约；节点不允许任意Python表达式。
- **正常验收**：遍历嵌套marker能得到python_version与os_name条件及准确分组。
- **异常／边界验收**：左右变量、in/not in、extras规范化、冗余括号、Unicode值和未知节点版本。
- **原生回归**：`tests/test_markers.py`、`tests/test_requirements.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 04．Marker可按已知环境部分化简

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/496)；知道目标OS但Python版本尚未选定时，把跨平台依赖条件化为剩余Python表达式。
- **原版现状／已有替代**：evaluate只返回bool并补齐宿主环境；&/|组合已存在，不等同部分求值。
- **交付与模块**：新增partial_evaluate返回恒真/恒假或剩余Marker，不用主机变量填空。；`src/packaging/markers.py`。
- **兼容边界**：不把字符串规范相等当语义等价；仅依据已给变量做确定化简，不尝试无限布尔求解。
- **正常验收**：os_name=posix将os条件与Python条件的and化为剩余Python条件。
- **异常／边界验收**：or分支真值、未知变量、空输入、右侧变量、集合条件、原始marker不变。
- **原生回归**：`tests/test_markers.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；[3]。

## 05．针对一组已选择extras求依赖适用性

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/452)；Requirement的extra==test需判断调用方选择test/docs任一extra时是否适用。
- **原版现状／已有替代**：向singular extra传set实跑AttributeError；当前可any逐个evaluate；lock_file的extras集合membership已存在。
- **交付与模块**：提供明确的selected-extras辅助API，按标准singular extra语义逐选项求值并定义空集合基线。；`src/packaging/markers.py`、`src/packaging/requirements.py`。
- **兼容边界**：不改变extra变量str类型，不替换现有extras membership；不是把集合传入旧参数的bug修复。
- **正常验收**：选择test/docs时extra==test生效，只有docs时不生效，非extra条件按同一目标环境求值。
- **异常／边界验收**：无extra条件、空选集、否定条件、规范化名称与多个条件的同一extra绑定。
- **原生回归**：`tests/test_markers.py`、`tests/test_requirements.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 06．元数据消费者可选择前向次版本策略

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/1404)；离线索引检查工具遇到2.99元数据仍希望读取已知字段并报告警告。
- **原版现状／已有替代**：Metadata.from_email(2.99)实跑ExceptionGroup，from_raw只接validate布尔；validate=False访问version仍可能失败。
- **交付与模块**：增加明确的consumer版本策略，允许未知同major minor并收集未知字段诊断，未知major继续拒绝。；`src/packaging/metadata.py`。
- **兼容边界**：严格生产者验证保持默认；不能忽略已知字段真正错误；保留原版本与未识别字段。
- **正常验收**：2.99包含有效name/version时可按consumer模式读取并取得结构化警告，3.0拒绝。
- **异常／边界验收**：无版本、非数字版本、重复字段、未知字段、已知字段非法与懒验证一致。
- **原生回归**：`tests/test_metadata.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 07．元数据校验可加入应用字段策略

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/732)；本地包管理规范除核心标准外还要求摘要长度或维护信息，想一次返回全部错误。
- **原版现状／已有替代**：Metadata的_Validator及ErrorCollector为内部实现；可在from_email后追加检查，但核心错误抛出后应用错误难统一。
- **交付与模块**：提供受限外部validation policy协议，在字段和整体两个阶段合并应用诊断。；`src/packaging/metadata.py`、`src/packaging/errors.py`。
- **兼容边界**：不把应用规则冒充核心规范；明确warning/error级别；懒字段访问只执行相关策略。
- **正常验收**：核心version错误和应用summary规则同时出现在一份报告，单字段懒验证不跑无关规则。
- **异常／边界验收**：策略异常、重复错误、未知字段、跨字段约束、严格/consumer模式及策略不修改输入。
- **原生回归**：`tests/test_metadata.py`、`tests/test_errors.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 08．旧Description续行的显式语义解码

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/867)；展示历史发行包的Description字段时去掉规范的续行前缀。
- **原版现状／已有替代**：parse_email实跑保留one后换行七空格|two；原版只把头字符串原样放入description。
- **交付与模块**：提供明确的legacy描述解码入口或选项，解释规范续行并保留原始值供诊断。；`src/packaging/metadata.py`。
- **兼容边界**：默认原始解析是否保持需兼容决定；非标准无竖线旧格式只按显式宽容模式处理。
- **正常验收**：合规旧Description解码成one换行two，正文描述保持不被多次解码。
- **异常／边界验收**：空行、行首真实竖线、混合换行、header/body冲突和License字段不同续行语义。
- **原生回归**：`tests/test_metadata.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 09．RECORD文件的标准模型与读写

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/708)；离线工具读取已安装分发包的文件清单，编辑后按同一格式保存。
- **原版现状／已有替代**：src没有RECORD专用模块或公开模型；目前调用方自行用csv/base64解析，pylock哈希模型不是RECORD。
- **交付与模块**：新增独立record模块，解析路径/hash/size三列并提供稳定序列化与逐项诊断。；`src/packaging/utils.py`、`src/packaging/metadata.py`。
- **兼容边界**：使用csv处理带逗号路径；空hash/size是合法状态；不在解析阶段自动读磁盘。
- **正常验收**：带逗号路径与sha256条目读写往返，缺hash/size的RECORD自身项保留。
- **异常／边界验收**：列数错误、非法大小、算法名和无padding编码、重复路径、Unicode和换行。
- **原生回归**：`tests/test_utils.py`、`tests/test_metadata.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 10．离线wheel归档的本地读取与重写API

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/697)；构建工具在本地wheel添加元数据后，需要读取归档并重新生成一致的RECORD。
- **原版现状／已有替代**：已有wheel文件名解析和Metadata解析，但没有wheel归档管理模块；zipfile与外部wheel包可替代。
- **交付与模块**：新增受限wheel归档API，把成员读取、单一dist-info核对、确定性写入及RECORD重建作为一次完整交付。；`src/packaging/utils.py`、`src/packaging/metadata.py`。
- **兼容边界**：只处理本地归档，不安装、不执行归档代码；不把wheel ABI改写成可兼容其他平台。
- **正常验收**：读取小wheel、更新一份metadata后写新文件，RECORD与成员内容一致并可重新读取。
- **异常／边界验收**：多个dist-info、重复成员、缺元数据、保留压缩/时间策略、流式对象与原文件不被部分写坏。
- **原生回归**：`tests/test_utils.py`、`tests/test_metadata.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；[9]。

## 11．PEP621项目表的独立解析校验

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/647)；不同构建后端共用pyproject的project表读取与错误报告。
- **原版现状／已有替代**：src包含dependency_groups/metadata/pylock，但没有PEP621 project表解析模块；可使用外部pyproject-metadata。
- **交付与模块**：新增mapping到受限标准project模型的解析器，处理name/version/dynamic、依赖和optional-dependencies。；`src/packaging/metadata.py`、`src/packaging/requirements.py`。
- **兼容边界**：只处理标准project表，不解释任意build-system或tool配置；动态字段保留为待后端提供。
- **正常验收**：正常项目表形成已验证模型并能映射Metadata，错误收集有字段路径。
- **异常／边界验收**：静态/动态重复、无name、依赖错误、readme/license文件引用仅声明不隐式读取、未知键。
- **原生回归**：`tests/test_metadata.py`、`tests/test_requirements.py`、`tests/test_dependency_groups.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 12．从结构化信息构造标准分发文件名

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/408)；发布准备工具从name/version/build/tags构造wheel和sdist名称，避免各应用自行转义。
- **原版现状／已有替代**：utils公开parse_wheel_filename/parse_sdist_filename，没有compose/build逆向入口。
- **交付与模块**：增加成对文件名构造器，使用明确标准规范化、稳定压缩tag排序和build标签校验。；`src/packaging/utils.py`、`src/packaging/tags.py`。
- **兼容边界**：parse可接受的历史非规范拼写不承诺逐字往返；保证语义往返，不自动创建归档。
- **正常验收**：合法结构构造文件名后parse得到等价name/version/build/tag集合。
- **异常／边界验收**：空tag集、不合法name、local版本、build后缀、压缩tag顺序与wheel/sdist转义差别。
- **原生回归**：`tests/test_utils.py`、`tests/test_tags.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 13．wheel解析可选择规范拼写审查

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/873)；本地发行质量检查希望区分可读取文件名与完全规范的发行文件名。
- **原版现状／已有替代**：foo_bÁr-01.0.0文件名实跑接受，返回foo-bár且is_normalized_name为False；validate_order只检查tag顺序。
- **交付与模块**：新增显式规范性诊断/严格选项，合并name与version的同一文件名审查，返回具体非规范组件。；`src/packaging/utils.py`。
- **兼容边界**：默认历史兼容解析保持；Unicode wheel名字标准与ASCII项目名标准差异必须单独诊断，不武断称为bug。
- **正常验收**：宽容读取保留可用信息，严格审查对前导零版本和不合项目名规则给明确诊断。
- **异常／边界验收**：正常Unicode边界、大小写/下划线是否规范、版本post/local、build和tags诊断区分。
- **原生回归**：`tests/test_utils.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 14．历史sdist带连字符版本的显式解析模式

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/527)；旧归档cffi-1.0.2-2.tar.gz需要被审查为名称cffi、版本1.0.2.post2。
- **原版现状／已有替代**：当前parse_sdist_filename实跑解释为cffi-1-0-2和Version(2)；这是现代名称规则与旧文件名歧义。
- **交付与模块**：增加legacy审查入口，枚举有效名称/版本切分并在多解时返回候选或要求期望名称，不静默猜测。；`src/packaging/utils.py`、`src/packaging/version.py`。
- **兼容边界**：默认现代解析保持；新发行文件名仍要求规范；不把任意连字符都当post版本。
- **正常验收**：给定期望cffi时旧归档恢复1.0.2.post2，无期望且歧义时明确展示候选。
- **异常／边界验收**：包名自身含连字符、多段版本、zip/tar.gz、非法版本、预期名称不符与唯一现代切分。
- **原生回归**：`tests/test_utils.py`、`tests/test_version.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 15．完整目标解释器标签配置对象

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/602)；交叉构建器需要从一个显式目标描述稳定得到优先级tags，而不拼接宿主探测结果。
- **原版现状／已有替代**：cpython_tags/generic_tags/compatible_tags/mac_platforms等低级入口已存在；没有统一TargetEnvironment配置对象。
- **交付与模块**：增加目标配置模型，把implementation/version/ABI/platform信息校验后编排既有tag生成器。；`src/packaging/tags.py`。
- **兼容边界**：不是重复新增interpreter_abi/platform_tags或create_compatible_tags_selector；默认sys_tags继续探测当前环境。
- **正常验收**：显式CPython目标生成标签序列与手工低级组合一致，不随研究主机改变。
- **异常／边界验收**：PyPy、free-threading、debug ABI、mac多架构、无法从给定信息推断平台时明确缺项。
- **原生回归**：`tests/test_tags.py`、`tests/test_manylinux.py`、`tests/test_musllinux.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 16．Requirement可选择展示和规范化渲染

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/654)；依赖配置编辑器显示易读空格，同时缓存键使用规范名称且不改变原始对象。
- **原版现状／已有替代**：str实跑Demo_Name[Dev]>=1.0，无format入口；相等/hash已做名称/extra/等价specifier规范化，__replace__也已存在。
- **交付与模块**：提供独立显式渲染策略：readable和canonical，统一处理name/extras/specifier/URL/marker。；`src/packaging/requirements.py`。
- **兼容边界**：默认str和hash不改；canonical不宣称对任意不同marker实现语义合并；URL不改变。
- **正常验收**：readable输出清楚组件间距；canonical统一名称与extras但重新解析语义相等。
- **异常／边界验收**：仅URL要求、多个extras、marker括号、任意相等===、空specifier和Unicode显示。
- **原生回归**：`tests/test_requirements.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 17．离线Simple索引文档标准模型

- **来源／场景**：[来源](https://github.com/pypa/packaging/issues/1088)；已有下载的HTML或JSON simple-index页面需要统一提取文件候选。
- **原版现状／已有替代**：packaging.index模块不存在；本库不提供HTML到JSON索引模型，调用方可用mousebender.simple。
- **交付与模块**：新增纯数据解析模块，接受文档内容与基准URL，输出文件名/url/hash/requires-python/yanked等统一记录。；`src/packaging/utils.py`、`src/packaging/requirements.py`。
- **兼容边界**：不发HTTP请求、不登录、不下载文件；不实现依赖解析器；保持未知标准扩展字段。
- **正常验收**：等价HTML和JSON文档得到等价候选，relative URL按给定base解析且requires-python可验证。
- **异常／边界验收**：非标准页面、缺文件名、Unicode、重复链接、yanked值、未知版本与无效requires-python诊断。
- **原生回归**：`tests/test_utils.py`、`tests/test_specifiers.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 18．依赖组解析附带包含路径来源

- **来源／场景**：[来源](https://github.com/pypa/packaging/blob/1a62a26afe0f4881593e31bed4f7753bd1c8fe27/src/packaging/dependency_groups.py)；dev通过test包含pytest，工具需解释每个最终需求由哪个组和第几项引入。
- **原版现状／已有替代**：DependencyGroupResolver只有lookup/resolve；实跑dev得到pytest/ruff，源路径丢失。
- **交付与模块**：新增独立resolve_with_provenance，返回Requirement及完整include链和条目位置，保留重复需求的各自来源。；`src/packaging/dependency_groups.py`。
- **兼容边界**：不改变resolve顺序/重复保留语义；缓存的来源必须按请求根重新建立，不能串组。
- **正常验收**：dev的pytest来源为dev->test及test条目，ruff来源为dev本地条目。
- **异常／边界验收**：菱形包含、重复组、规范化名、循环错误链、空组和同一需求出现两次。
- **原生回归**：`tests/test_dependency_groups.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 19．SPDX表达式的结构化只读检查

- **来源／场景**：[来源](https://github.com/pypa/packaging/blob/1a62a26afe0f4881593e31bed4f7753bd1c8fe27/src/packaging/licenses/__init__.py)；包信息页面想分别显示表达式中的许可证选择和WITH例外，并保留AND/OR分组。
- **原版现状／已有替代**：licenses仅公开canonicalize_license_expression返回规范字符串，没有可遍历表达式模型；_spdx事实表为私有数据。
- **交付与模块**：提供只读表达式节点/标识访问器，复用现有语法校验，不推断许可证兼容性或法律结论。；`src/packaging/licenses/__init__.py`、`src/packaging/licenses/_spdx.py`。
- **兼容边界**：现有规范化输出保持；LicenseRef保持用户拼写规则；不把列表名称对应许可证自动视作本项目许可。
- **正常验收**：MIT OR (Apache-2.0 AND BSD-2-Clause)形成正确树，WITH例外与对应license关联。
- **异常／边界验收**：LicenseRef、deprecated标识、重复标识、括号、未知标识、仅字符串读取与节点不可变。
- **原生回归**：`tests/test_licenses.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

## 20．Pylock本地选择结果提供原因报告

- **来源／场景**：[来源](https://github.com/pypa/packaging/blob/1a62a26afe0f4881593e31bed4f7753bd1c8fe27/src/packaging/pylock.py)；同一离线lock在不同目标标签下选出不同wheel，开发者需要知道其余包为何略过。
- **原版现状／已有替代**：Pylock.select已完成marker/版本/标签/源码选择，但只yield选中二元组或抛错，未提供explain/trace接口。
- **交付与模块**：新增独立选择解释记录：包marker结果、Python限制、兼容tag排名、所选来源和未选原因，复用同一选择引擎。；`src/packaging/pylock.py`、`src/packaging/tags.py`。
- **兼容边界**：不重复实现已有select或改变优先级；解释模式不访问URL，不读取被选安装文件。
- **正常验收**：报告指出marker不满足被略过的包、最佳wheel命中tag及sdist回退原因，选中集合与select完全一致。
- **异常／边界验收**：重复包冲突、未知extra/group、目标不兼容、prefer_sdist_predicate抛错、无候选与空lock。
- **原生回归**：`tests/test_pylock_select.py`、`tests/test_pylock.py`。
- **实际依赖／步骤依赖**：Python标准库；生产仍无必需外部依赖。原生测试使用已冻结pytest/hypothesis/pretend/tomli_w/coverage。；无。

每步包含实现/测试/文档/失败修复；同一真实工程累计推进，不能把测试矩阵或格式维度另拆步。未来控制端冻结正反例、核对实际候选路径、调用本库原生API及本地文件效果，并回归原生集合和此前接受能力。研究完成不等于冻结验收就绪。
