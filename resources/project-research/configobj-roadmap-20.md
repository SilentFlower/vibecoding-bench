# ConfigObj：二十步真实工程迭代路线

固定 [DiffSK/configobj@b7707c94c0317b8f89b704a01525a68eb6c72521](https://github.com/DiffSK/configobj/tree/b7707c94c0317b8f89b704a01525a68eb6c72521)，原生证据见 [单仓审查](./configobj.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．字符串值可安全往返

- **类型与来源**：修复；[官方 #271](https://github.com/DiffSK/configobj/issues/271) 与固定源码／原版观察。
- **原版现状与收益**：#269／270／271 的同一引号族问题均实测：hash、前空格、空值和混合三引号改变数据。
- **交付及模块**：统一解析与写入的字符串语法，选择不在值内的合法引号，无法表示时写入前拒绝；ConfigObj._quote／_handle_value／_get_triple_quote。
- **兼容与依赖**：list_values=True／False 与 _inspec 各自语义明确；同一缺陷矩阵合为一步，不新增通用 Python repr 解析；步骤依赖：无。
- **正常验收**：正常、hash、前后空白和两种引号组合 write→read 完全相等。
- **异常／边界验收**：两种三引号同时出现、换行和空列表；不能把 literal quotes 不兼容地全部自动剥除。
- **原生回归**：src/tests/test_configobj.py、configobj_doctests.py。

## 02．含等号键名正确保留引号

- **类型与来源**：修复；[官方 #273](https://github.com/DiffSK/configobj/issues/273) 与固定源码／原版观察。
- **原版现状与收益**：原版读取 x <a='b'> 键后写出未引用键，第二次 ParseError。
- **交付及模块**：独立的 key 引号规则，保留使赋值边界可唯一解析的键；ConfigObj._write_line／_quote、_parse。
- **兼容与依赖**：普通键输出保持；不把值的多行引号能力误用于键；步骤依赖：无。
- **正常验收**：包含 =、#、首尾空白和 Unicode 的有效键往返不变。
- **异常／边界验收**：换行键或无法表示的组合在发布前失败；不改写键名或意外创建第二字段。
- **原生回归**：src/tests/test_configobj.py、configobj_doctests.py。

## 03．深拷贝保留插值表达式

- **类型与来源**：修复；[官方 #188](https://github.com/DiffSK/configobj/issues/188) 与固定源码／原版观察。
- **原版现状与收益**：deepcopy 后 raw baz 已成 bar.txt；改复制品 foo 不能重新计算。
- **交付及模块**：拷贝原始存储与元数据，重新连接复制品 parent/main，不通过求值后的 items 固化；Section.__reduce__／__setstate__、items、dict。
- **兼容与依赖**：显式 .dict() 的求值语义保持；只修复制对象的表达式与隔离；步骤依赖：无。
- **正常验收**：复制品改 foo 后 baz=abc.txt，源仍 bar.txt。
- **异常／边界验收**：嵌套节、列表插值、注释和循环错误独立；pickle 兼容和共享引用策略清楚。
- **原生回归**：src/tests/test_configobj.py、configobj_doctests.py。

## 04．合并时保留新增节注释

- **类型与来源**：修复；[官方 #171](https://github.com/DiffSK/configobj/issues/171) 与固定源码／原版观察。
- **原版现状与收益**：原版 merge 接受数据但实际丢失新增子节的 # 子节注释。
- **交付及模块**：合并 Section 时复制必要 comments／inline_comments 与子节元数据，按显式覆盖策略处理冲突；Section.merge、Section.__setitem__。
- **兼容与依赖**：普通 dict 没注释时不发明注释；现有递归值覆盖保持；步骤依赖：无。
- **正常验收**：两份带注释配置合并写出新增节及其注释，值不丢。
- **异常／边界验收**：同名键注释冲突、空注释、默认值与重复 merge 不无限叠加。
- **原生回归**：src/tests/test_configobj.py、configobj_doctests.py。

## 05．类型验证后仍可插值标量

- **类型与来源**：修复；[官方 #156](https://github.com/DiffSK/configobj/issues/156) 与固定源码／原版观察。
- **原版现状与收益**：a 转为 integer 后，template 引用 $a 触发 TypeError。
- **交付及模块**：对已验证可表示标量使用明确字符串视图做插值，保留最终 validation 转换；InterpolationEngine.interpolate／_fetch、ConfigObj.validate。
- **兼容与依赖**：普通字符串和 raw 访问不变；list/section 不静默任意 str 化；步骤依赖：无。
- **正常验收**：先验证 a 再验证 b 引用 a，b 得预期字符串或目标类型。
- **异常／边界验收**：bool、None、float、列表和自循环有明确规则，未验证引用仍遵守原错误类型。
- **原生回归**：src/tests/test_configobj.py、src/tests/test_validate.py。

## 06．文件写入可原子发布

- **类型与来源**：增强；[官方 #180](https://github.com/DiffSK/configobj/issues/180) 与固定源码／原版观察。
- **原版现状与收益**：write(filename) 直接 wb 截断，现有 outfile 只是调用者流。
- **交付及模块**：增加 atomic=True 的同目录临时发布，保留目标模式并清理本轮临时文件；ConfigObj.write。
- **兼容与依赖**：普通 outfile 流写保持；atomic 不保证断电持久性，symlink 策略显式；步骤依赖：无。
- **正常验收**：更新后重新读取值／注释完整，替换期间读者只看旧或新完整文件。
- **异常／边界验收**：序列化、写入、replace 失败保留可确定状态；临时文件唯一，不改未知路径。
- **原生回归**：src/tests/test_configobj.py、configobj_doctests.py。

## 07．公开的内联注释控制

- **类型与来源**：增强；[官方 #268](https://github.com/DiffSK/configobj/issues/268) 与固定源码／原版观察。
- **原版现状与收益**：没有 disable_inline_comments，只有私有 _inspec 间接关掉且改变列表／引号语义。
- **交付及模块**：增加 inline_comments=True／False 配置，分离文件注释和 inline 注释；ConfigObj.__init__、_parse／_handle_value／_handle_comment。
- **兼容与依赖**：默认 hash 注释保持；_inspec 用于 spec 的规则仍兼容；步骤依赖：01。
- **正常验收**：关闭后 hello # world 当值，整行 # comment 仍是注释。
- **异常／边界验收**：引号内 hash、列表成员 hash、嵌套节和 write→reload 往返。
- **原生回归**：src/tests/test_configobj.py、configobj_doctests.py。

## 08．配置赋值分隔排版

- **类型与来源**：增强；[官方 #159](https://github.com/DiffSK/configobj/issues/159) 与固定源码／原版观察。
- **原版现状与收益**：_write_line 固定使用空格等号空格。
- **交付及模块**：新增 assignment_spacing 仅控制 = 两侧空白，满足现有消费方严格排版；ConfigObj._write_line、构造与 reload 选项传递。
- **兼容与依赖**：默认保持 = 的原排版；首版不支持任意新语法分隔符；步骤依赖：无。
- **正常验收**：compact 模式输出 key=value 且本库与标准消费者读回一致。
- **异常／边界验收**：引号键、inline 注释、空值和多行值不误删内部空白。
- **原生回归**：src/tests/test_configobj.py。

## 09．公开插值引擎扩展入口

- **类型与来源**：增强；[官方 #205](https://github.com/DiffSK/configobj/issues/205) 与固定源码／原版观察。
- **原版现状与收益**：只支持内建引擎和私有全局映射，构造器拒绝 interpolation_engine。
- **交付及模块**：显式 engine factory 接收 section，返回实现受控 interpolate 协议的实例；InterpolationEngine、Section._interpolate、ConfigObj.__init__。
- **兼容与依赖**：默认 configparser/template 不变；工厂不暗中接云服务，本轮验收纯本地映射；步骤依赖：无。
- **正常验收**：本地 env-like 自定义占位通过新引擎解析。
- **异常／边界验收**：错误引擎类型、异常传播、循环／深度限制和嵌套配置实例不互串。
- **原生回归**：src/tests/test_configobj.py、configobj_doctests.py。

## 10．跨节引用插值

- **类型与来源**：增强；[官方 #101](https://github.com/DiffSK/configobj/issues/101) 与固定源码／原版观察。
- **原版现状与收益**：template 模式 ${a.x} 已实测 MissingInterpolationOption。
- **交付及模块**：提供显式 extended 模式，按定义的节路径解析而非扩展所有旧变量名；InterpolationEngine 子类、_fetch、Section。
- **兼容与依赖**：默认含点键名保持原解释；与自定义引擎分开，不依赖任意网络；步骤依赖：09。
- **正常验收**：a.x→b.x→c.x 的引用链得到完整值。
- **异常／边界验收**：点字符键的转义、节不存在、循环、自引用与嵌套同名节定位清楚。
- **原生回归**：src/tests/test_configobj.py、configobj_doctests.py。

## 11．未知字段校验策略

- **类型与来源**：增强；[官方 #125](https://github.com/DiffSK/configobj/issues/125) 与固定源码／原版观察。
- **原版现状与收益**：validate 对 extra 字段实际返回 True；已记录 extra_values 但不决定允许与否。
- **交付及模块**：增加 unknown=allow／warn／error 的显式验证策略，输出完整节路径；ConfigObj.validate、get_extra_values、flatten_errors。
- **兼容与依赖**：默认 allow；__many__ 的允许范围不被误拒，不能仅检查顶层；步骤依赖：无。
- **正常验收**：error 拒绝未定义选项和节，allow 保留扩展字段。
- **异常／边界验收**：重复节路径、空节、__many__、默认注入和 preserve_errors 格式统一。
- **原生回归**：src/tests/test_validate_errors.py、src/tests/test_configobj.py。

## 12．可选节验证

- **类型与来源**：增强；[官方 #131](https://github.com/DiffSK/configobj/issues/131) 与固定源码／原版观察。
- **原版现状与收益**：configspec 支持字段默认与重复节，但无公开可选节标记。
- **交付及模块**：定义可选节元数据：不存在通过，存在时全部适用字段照常验证；ConfigObj._set_configspec／validate。
- **兼容与依赖**：现有必需节默认行为保持；首版选结构化元数据避免与真实节名碰撞；步骤依赖：无。
- **正常验收**：可选 TLS 节缺失通过、提供合法证书路径字符串时通过。
- **异常／边界验收**：提供空节却缺必需键应失败，嵌套可选与 __many__ 不绕过校验。
- **原生回归**：src/tests/test_validate_errors.py、src/tests/test_configobj.py。

## 13．非法值显式回退到已验证默认

- **类型与来源**：增强；[官方 #136](https://github.com/DiffSK/configobj/issues/136) 与固定源码／原版观察。
- **原版现状与收益**：当前 defaults 可恢复，但 validate 没有一轮内 invalid→default 的公开策略。
- **交付及模块**：增加 invalid=error／default，默认值也通过同一 Validator 后才采用并记录修复诊断；ConfigObj.validate、Validator.get_default_value。
- **兼容与依赖**：默认保留原错误；不把缺失和显式非法等同，调用者 opt-in；步骤依赖：无。
- **正常验收**：超出范围的端口回退到合法 spec default，并报告键路径。
- **异常／边界验收**：默认也非法、无默认、None 默认、custom validator 抛错时不能掩盖问题。
- **原生回归**：src/tests/test_validate.py、src/tests/test_validate_errors.py。

## 14．显式环境覆盖映射

- **类型与来源**：增强；[官方 #144](https://github.com/DiffSK/configobj/issues/144) 与固定源码／原版观察。
- **原版现状与收益**：构造器拒绝 use_env_vars；用户要外部手动层叠 os.environ。
- **交付及模块**：提供 opt-in 环境映射输入与前缀／节名编码，先校验再覆盖，不回写进程环境；ConfigObj、Section 查询或独立 overlay helper、validate。
- **兼容与依赖**：默认只用文件；只接调用者明确映射，禁止文件自己启用读取全环境；步骤依赖：无。
- **正常验收**：APP_SERVER__PORT 覆盖目标且经 integer 校验，其他键不受影响。
- **异常／边界验收**：环境名归一化冲突、空字符串、未知键、嵌套节和 secret 不进入诊断。
- **原生回归**：src/tests/test_configobj.py、src/tests/test_validate.py。

## 15．无赋值键的兼容模式

- **类型与来源**：增强；[官方 #117](https://github.com/DiffSK/configobj/issues/117) 与固定源码／原版观察。
- **原版现状与收益**：不带 = 的 bare key 默认 ParseError，公开构造器无 allow_no_value。
- **交付及模块**：增加 allow_no_value=True，将无赋值字段表示为独立 None，写回仍无 =；ConfigObj._parse／_write_line、验证边界。
- **兼容与依赖**：默认语法保持；空字符串 key= 与 bare key 必须区分；步骤依赖：无。
- **正常验收**：MySQL 风格 quick／skip-external-locking 原样往返。
- **异常／边界验收**：bare key 旁注释、重复字段、列表值、必需验证和 None 策略明确。
- **原生回归**：src/tests/test_configobj.py、configobj_doctests.py。

## 16．强制列表并验证元素类型

- **类型与来源**：增强；[官方 #114](https://github.com/DiffSK/configobj/issues/114) 与固定源码／原版观察。
- **原版现状与收益**：force_list 只接 value/min/max，int_list 等拒绝标量；没有组合 convenience。
- **交付及模块**：新增 typed_list(item_check, force=True) 或等价受控检查，使单值归一化后逐项验证；validate.py:Validator、force_list、is_*_list。
- **兼容与依赖**：已有 force_list 返回字符串列表保持；不拆一个类型的每种元素为不同步骤；步骤依赖：无。
- **正常验收**：单个 42 与 1,2,3 都可按整数列表输出。
- **异常／边界验收**：非法第 N 元素报告位置，空列表、长度上下界和 custom check 明确。
- **原生回归**：src/tests/test_validate.py、src/tests/test_validate_errors.py。

## 17．验证器的空值许可可配置

- **类型与来源**：增强；[官方 #218](https://github.com/DiffSK/configobj/issues/218) 与固定源码／原版观察。
- **原版现状与收益**：Validator.check 在值 None 时提前返回，范围型 check 也不会拒绝 None。
- **交付及模块**：新增 allow_none 明确策略，区分字段缺失、默认 None 与显式值 None；validate.py:Validator.check、ConfigObj.validate。
- **兼容与依赖**：默认现有 None 规则保持；不能把字符串 None 与 Python None 一概混同；步骤依赖：无。
- **正常验收**：allow_none=False 的范围型拒绝 None，True 接受。
- **异常／边界验收**：缺失但有合法默认、无默认必需键、quoted None 和 bare key 全部覆盖。
- **原生回归**：src/tests/test_validate.py、src/tests/test_validate_errors.py。

## 18．从规范生成独立示例配置

- **类型与来源**：增强；[官方 #102](https://github.com/DiffSK/configobj/issues/102) 与固定源码／原版观察。
- **原版现状与收益**：copy=True 复制默认，无法指定与运行默认不同的示例值。
- **交付及模块**：提供示例元数据／生成入口，生成前验证样例且不改变运行 default；validate.py spec 元数据、ConfigObj 示例 helper。
- **兼容与依赖**：原 validator.check 不把 example 当未知函数参数直接失败；样例字段隔离；步骤依赖：无。
- **正常验收**：fruit 默认空但示例 apple，注释和顺序保留。
- **异常／边界验收**：示例非法、未给示例、敏感字段显式占位，不能从当前生产值推断模板。
- **原生回归**：src/tests/test_validate.py、src/tests/test_configobj.py。

## 19．结构化校验结果

- **类型与来源**：增强；[官方 #155](https://github.com/DiffSK/configobj/issues/155) 与固定源码／原版观察。
- **原版现状与收益**：validate 返回 True／False／dict 三种形状，非空失败 dict 容易被 bool 误判。
- **交付及模块**：提供独立 validate_report，固定 valid、issues、changed_paths 和默认应用信息；ConfigObj.validate、flatten_errors。
- **兼容与依赖**：原 validate 返回完全保持；不隐式改变 dict truthiness；步骤依赖：无。
- **正常验收**：有效和失败两种报告结构一致，路径含完整嵌套节。
- **异常／边界验收**：preserve_errors、重复节、missing 和 custom error 不打印配置值；结果可序列化。
- **原生回归**：src/tests/test_validate_errors.py、src/tests/test_configobj.py。

## 20．重新加载后验证且失败保留旧配置

- **类型与来源**：增强；[官方 #87](https://github.com/DiffSK/configobj/issues/87) 与固定源码／原版观察。
- **原版现状与收益**：reload 清空后直接 _load，不重跑既有 Validator；force_list 类型可能回到 str，坏文件可毁掉原已加载状态。
- **交付及模块**：增加 validated_reload(validator) 在新 ConfigObj 上读取和校验，成功后整体接管数据及元数据；ConfigObj.reload、_load、validate、Section parent/main 连接。
- **兼容与依赖**：现有 reload 行为保持；新入口明确重新校验，不能隐式保存任意旧 Validator 引用；步骤依赖：19。
- **正常验收**：标量 force_list reload 后仍为列表，合法修改替换全部旧配置。
- **异常／边界验收**：坏文件、验证失败、文件消失时旧数据／注释／配置选项不变，来源与 parent 正确。
- **原生回归**：src/tests/test_configobj.py、src/tests/test_validate.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
