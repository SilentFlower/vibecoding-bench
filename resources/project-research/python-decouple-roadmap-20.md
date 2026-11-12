# python-decouple：二十步真实工程迭代路线

固定 [HBNetwork/python-decouple@0573e6f96637f08fb4cb85e0552f0622d36827d4](https://github.com/HBNetwork/python-decouple/tree/0573e6f96637f08fb4cb85e0552f0622d36827d4)，原生证据见 [单仓审查](./python-decouple.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．CSV值的字面数据保真

- **类型与来源**：修复；[官方 #102](https://github.com/HBNetwork/python-decouple/issues/102) 与固定源码。
- **原版现状与收益**：Csv使用shell shlex，实测regex反斜杠被去掉、#截断、连续逗号丢空字段。
- **交付及模块**：提供真正CSV语义解析和明确legacy_shell兼容模式，统一处理引号、转义与空项；decouple.py:Csv.__call__。
- **兼容与依赖**：格式语义变化须显式模式迁移；已有cast/post_process仍逐项一次，不能把三种症状拆步；步骤依赖：无。
- **正常验收**：regex、含#的值、带逗号引用项和空项可精确往返。
- **异常／边界验收**：未闭引号、双引号转义、反斜杠结尾、多字符delimiter含义明确。
- **原生回归**：tests/test_helper_csv.py。

## 02．Repository存在性与读取一致

- **类型与来源**：修复；[官方 #176](https://github.com/HBNetwork/python-decouple/issues/176) 与固定源码、#175。
- **原版现状与收益**：RepositoryEnv/Ini/Secret的contains包含os.environ而getitem不返回环境值；Empty缺键None。
- **交付及模块**：明确仓库只代表底层源，contains/getitem一致，环境优先级只由Config负责；Empty缺键KeyError；所有Repository的__contains__/__getitem__。
- **兼容与依赖**：Config正常环境优先不变；直接依赖旧不一致contains的代码有迁移说明；步骤依赖：无。
- **正常验收**：每类仓库对缺失key contains=False且getitem KeyError，对存在key取相同值。
- **异常／边界验收**：环境存在而源缺失、空字符串与None、INI缺section和自定义组合仓库。
- **原生回归**：tests/test_env.py、test_ini.py、test_secrets.py、test_autoconfig.py。

## 03．UTF-8 BOM文件正常读取

- **类型与来源**：增强；decouple.py公开定义与observe.py合成配置场景。
- **原版现状与收益**：RepositoryEnv以utf-8读取把BOM当首键字符，实测REVIEW_BOM查不到。
- **交付及模块**：默认UTF-8兼容首BOM或提供明确utf-8-sig自动识别，统一INI／ENV读取入口；RepositoryEnv.__init__、RepositoryIni.__init__。
- **兼容与依赖**：仅文件开头BOM特殊，值内U+FEFF不能全局删；显式其他编码照常；步骤依赖：无。
- **正常验收**：带/不带BOM的同一文件配置一致，中文不损坏。
- **异常／边界验收**：空文件只有BOM、BOM位于注释前、解码错误和非UTF8显式编码。
- **原生回归**：tests/test_env.py、test_ini.py。

## 04．严格配置文件诊断

- **类型与来源**：增强；decouple.py公开定义与observe.py合成配置场景。
- **原版现状与收益**：ENV默默跳过无等号行，AutoConfig._load宽泛except会把查找错误伪装无文件。
- **交付及模块**：增加strict模式，文件发现／解析错误有路径与行号，正常缺文件与权限失败区分；RepositoryEnv、AutoConfig._load／_find_file。
- **兼容与依赖**：默认原容错行为保留，严格模式不读取真实祖先配置；错误默认不含值；步骤依赖：无。
- **正常验收**：合法.env正常读取；坏行或不可读目录严格失败可定位。
- **异常／边界验收**：重复键、裸export、坏编码、目录替换与找不到文件分别有明确结果。
- **原生回归**：tests/test_env.py、test_autoconfig.py。

## 05．有界且可预览的配置查找

- **类型与来源**：增强；[官方 #69](https://github.com/HBNetwork/python-decouple/issues/69) 与固定源码、#172、#126。
- **原版现状与收益**：仅search_path和固定递归终止规则；无公开find入口／stop_dir，Windows跨驱动风险未实机验证。
- **交付及模块**：提供find_config(start,stop,candidates)不加载值，以父==当前终止，可显式cwd模式支持交互／zipapp；AutoConfig._find_file／_caller_path。
- **兼容与依赖**：不默认扩大查找范围；现有search_path继续有效，默认不在文件系统根写入；步骤依赖：无。
- **正常验收**：临时树内找最近支持文件，到stop含边界停止。
- **异常／边界验收**：驱动根用ntpath模拟、POSIX根、空调用文件名、起点越界和循环路径有界。
- **原生回归**：tests/test_autoconfig.py。

## 06．组合多个有序仓库

- **类型与来源**：增强；[官方 #185](https://github.com/HBNetwork/python-decouple/issues/185) 与固定源码。
- **原版现状与收益**：用户自己写MultiRepository；内建只能Config接单仓库。
- **交付及模块**：提供RepositoryChain，按声明顺序首个存在值获胜，可选缺文件仓库；新RepositoryChain、Config。
- **兼容与依赖**：进程环境仍只在Config最高层，仓库内部不重复读环境；空值算存在；步骤依赖：02。
- **正常验收**：.env开发配置与合成secrets后备按指定顺序生效。
- **异常／边界验收**：缺源、权限错误strict、空仓、同名空值、重复源只按规则读取。
- **原生回归**：tests/test_env.py、test_secrets.py、test_autoconfig.py。

## 07．一次加载配置声明并聚合校验

- **类型与来源**：增强；[官方 #183](https://github.com/HBNetwork/python-decouple/issues/183) 与固定源码。
- **原版现状与收益**：各config(key,cast)独立，无法声明必需／默认／类型后一次报告全部问题。
- **交付及模块**：轻量字段schema接口，首版只支持明确Field集合或dataclass注解，并返回配置对象；Config、字段schema helper。
- **兼容与依赖**：旧按键读取不变；不隐式执行任意注解字符串或框架导入；步骤依赖：无。
- **正常验收**：PORT/int、DEBUG/bool和HOSTS/Csv一次生成正确字段。
- **异常／边界验收**：多个缺失和转换错误同时按键报告；禁止部分对象发布，不输出敏感值。
- **原生回归**：tests/test_env.py、test_helper_csv.py、新增schema集合。

## 08．字典值转换助手

- **类型与来源**：增强；[官方 #179](https://github.com/HBNetwork/python-decouple/issues/179) 与固定源码。
- **原版现状与收益**：没有mapping cast，用户手动split容易把含=的URL切坏。
- **交付及模块**：新增MappingCast，可选JSON对象或明确key=value dialect，支持key/value cast；helpers新类或decouple.py helper段。
- **兼容与依赖**：Csv仍列表；字典模式显式，不将任何字符串自动JSON解码；步骤依赖：无。
- **正常验收**：SQLite3=sqlite://:memory:和带=URL正确组成dict。
- **异常／边界验收**：重复键error/last策略、空key、引号内逗号、无分隔值及错误项定位。
- **原生回归**：tests/test_helper_csv.py、新增mapping helper测试。

## 09．环境映射可显式注入

- **类型与来源**：增强；decouple.py公开定义与observe.py合成配置场景。
- **原版现状与收益**：Config直接访问全局os.environ，测试和多租户配置需要patch全局。
- **交付及模块**：Config接environ Mapping或provider，默认os.environ，按键读取来源一次；Config.__init__／get、Repository去环境分支。
- **兼容与依赖**：默认行为保持；注入空映射必须真为空，不能用environ or os.environ回落；步骤依赖：02。
- **正常验收**：两个Config实例读取各自合成映射而不改进程环境。
- **异常／边界验收**：动态provider错误、只读Mapping、空字符串、None非法值和并发只读。
- **原生回归**：tests/test_env.py、test_ini.py。

## 10．前缀和命名空间配置

- **类型与来源**：增强；现有配置读取路径的实际使用分析（增强提案）。
- **原版现状与收益**：只有完整key字符串，应用配置需各处重复APP_。
- **交付及模块**：提供namespace/prefix视图，对环境键做显式映射，文件键映射策略可分开选；Config namespace helper。
- **兼容与依赖**：原无前缀不变；不自动全大写文件大小写键，返回新视图不改原对象；步骤依赖：09。
- **正常验收**：APP_PORT可通过view(PORT)读取并转换。
- **异常／边界验收**：嵌套前缀、已有前缀key、空前缀、非字符串key和大小写冲突明确。
- **原生回归**：tests/test_env.py、test_ini.py。

## 11．不含值的配置来源解释

- **类型与来源**：增强；现有配置读取路径的实际使用分析（增强提案）。
- **原版现状与收益**：get只返回值，无法说明环境／文件／默认哪层获胜。
- **交付及模块**：提供explain(key)，返回存在性、仓库来源、路径与转换类型元数据，默认无值；Config.get、Repository来源metadata。
- **兼容与依赖**：普通get返回类型不变；不得先执行cast两次或为诊断读取额外secret；步骤依赖：06、09。
- **正常验收**：ENV覆盖文件时来源为environment，chain能解释实际胜出源。
- **异常／边界验收**：default、缺失、转换失败、用户cast和敏感key均不暴露值。
- **原生回归**：tests/test_env.py、test_ini.py、test_secrets.py。

## 12．secret目录读取策略

- **类型与来源**：增强；decouple.py公开定义与observe.py合成配置场景。
- **原版现状与收益**：RepositorySecret构造遍历并open每项，遇子目录即IsADirectoryError，没有编码参数。
- **交付及模块**：新增encoding、目录/特殊文件与symlink策略，默认只接明确的普通文件集合；RepositorySecret.__init__。
- **兼容与依赖**：只使用调用者指定目录，不自动扫描真实/run/secrets；现有值尾换行保留默认；步骤依赖：无。
- **正常验收**：合成目录中普通secret正确读取，子目录可忽略或strict拒绝。
- **异常／边界验收**：悬空／越界链接、FIFO、不可读文件、坏编码、目录并发变化均有界。
- **原生回归**：tests/test_secrets.py。

## 13．secret按键惰性读取

- **类型与来源**：增强；现有配置读取路径的实际使用分析（增强提案）。
- **原版现状与收益**：构造读取全部secret，即便应用只要一键；也无法感知轮换后的新文件。
- **交付及模块**：提供lazy RepositorySecret模式，读取请求键时才打开，缓存／reload策略显式；RepositorySecret.__contains__／__getitem__。
- **兼容与依赖**：默认eager保持；key必须是单个有效文件名，不跟随../；不是远程secret服务；步骤依赖：12。
- **正常验收**：只读一键时其他文件未打开，轮换后按所选策略读新值。
- **异常／边界验收**：不合法key、已删文件、空内容、原子替换与权限失败不返回半份缓存。
- **原生回归**：tests/test_secrets.py。

## 14．INI节与插值行为可选择

- **类型与来源**：增强；decouple.py公开定义与observe.py合成配置场景。
- **原版现状与收益**：RepositoryIni固定[settings]和ConfigParser插值，实测URL里的%20抛错误。
- **交付及模块**：提供section和interpolation配置，让literal URL／DSN可读取；RepositoryIni.__init__／__getitem__。
- **兼容与依赖**：默认settings和现有插值保持；不能无条件把所有%替换成%%；步骤依赖：无。
- **正常验收**：选自定义节、literal模式读取含%20的URL。
- **异常／边界验收**：继承DEFAULT、同名大小写、缺section、合法%(name)s现有插值和注释。
- **原生回归**：tests/test_ini.py。

## 15．ENV常用语法的显式支持

- **类型与来源**：增强；decouple.py公开定义与observe.py合成配置场景。
- **原版现状与收益**：export REVIEW_EXPORT被实际解析成含export的键；不支持值内换行／注释策略。
- **交付及模块**：提供可选择的ENV dialect，支持字面export前缀和明确双/单引号转义，不执行shell；RepositoryEnv解析器。
- **兼容与依赖**：默认旧简单方言可兼容；不宣称完整Bash，不执行命令替换或source；步骤依赖：04。
- **正常验收**：export KEY=value与KEY=value得到相同key；引号值保持所选规则。
- **异常／边界验收**：值中等号、#、空白、多行与未闭引号strict有位置，不扩散成新的shell解释器。
- **原生回归**：tests/test_env.py。

## 16．显式值插值

- **类型与来源**：增强；现有配置读取路径的实际使用分析（增强提案）。
- **原版现状与收益**：ENV取值是字面字符串，无跨key引用；当前INI插值由另一个后端处理。
- **交付及模块**：增加opt-in ${NAME}与默认表达式解析器，使用Config已选来源策略；Config／RepositoryEnv插值helper。
- **兼容与依赖**：默认字面字符串保持；仅变量引用，不eval，不读取未授权额外环境映射；步骤依赖：09。
- **正常验收**：HOST/PORT组合为URL，来源优先和default一致。
- **异常／边界验收**：循环／深度和展开长度有界、缺失变量、字面转义、secret不写日志。
- **原生回归**：tests/test_env.py、test_ini.py。

## 17．受控重新加载

- **类型与来源**：增强；现有配置读取路径的实际使用分析（增强提案）。
- **原版现状与收益**：AutoConfig只初始化一次，ENV和secret都保存初始dict，修改文件需重建对象。
- **交付及模块**：增加reload()在候选仓库中读取成功后一次替换，发现路径是否重查由选项明确；AutoConfig、RepositoryEnv／Ini／Secret。
- **兼容与依赖**：现有懒加载保持；默认reload沿当前已绑定文件，避免意外换祖先源；步骤依赖：04、06。
- **正常验收**：文件删键／改值reload后体现，Config视图继续工作。
- **异常／边界验收**：strict失败保留旧可用仓库、文件消失、编码变更和lazysecret组合。
- **原生回归**：tests/test_autoconfig.py、test_env.py、test_secrets.py。

## 18．按需默认值工厂

- **类型与来源**：增强；现有配置读取路径的实际使用分析（增强提案）。
- **原版现状与收益**：default是值，不会作为工厂调用；昂贵后备需应用手工先判断缺失。
- **交付及模块**：增加default_factory显式参数，仅所有来源缺失时调用一次再cast；Config.get。
- **兼容与依赖**：default和default_factory同时给时报配置错误；现有可调用default仍是普通值；步骤依赖：无。
- **正常验收**：存在配置时工厂不执行，缺配置时执行一次并按目标类型转换。
- **异常／边界验收**：工厂异常附key安全上下文、返回None、空值来源不是缺失、递归工厂有界。
- **原生回归**：tests/test_env.py、test_ini.py。

## 19．可复用的cast注册与组合

- **类型与来源**：增强；[官方 #115](https://github.com/HBNetwork/python-decouple/issues/115) 与固定源码。
- **原版现状与收益**：cast可传callable但没有每实例可复用命名集合；插件需求不必先加完整pluggy。
- **交付及模块**：提供Config级cast registry与组合器，按名字注册路径／范围／枚举等项目cast；Config与helpers。
- **兼容与依赖**：直接callable仍最高兼容；不自动加载任意entrypoint，不引入必需第三方依赖；步骤依赖：无。
- **正常验收**：同一registry复用port范围cast，多个实例可有不同同名实现。
- **异常／边界验收**：重复注册策略、未知名、组合中途失败不泄漏值，bool既有快捷语义保持。
- **原生回归**：tests/test_env.py、test_helper_choices.py。

## 20．包含键上下文且可遮蔽值的转换错误

- **类型与来源**：增强；现有配置读取路径的实际使用分析（增强提案）。
- **原版现状与收益**：cast抛原ValueError，int等消息带输入，应用无法安全统一展示缺哪键。
- **交付及模块**：新增ConfigValueError包含option/source/cause_type，安全消息不含值，调试信息显式选择；Config.get、错误类。
- **兼容与依赖**：保留原异常cause，是否包裹通过显式策略开关；UndefinedValueError继续区分；步骤依赖：11。
- **正常验收**：坏PORT可定位键、源和目标cast，普通成功值不变。
- **异常／边界验收**：包含secret的Choices合法集合／输入、custom异常message、nested Csv项均不泄漏安全输出。
- **原生回归**：tests/test_env.py、test_helper_csv.py、test_helper_choices.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
