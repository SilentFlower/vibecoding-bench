# Typer：二十步真实工程迭代路线

固定 [fastapi/typer@a5882dedf0bc7a46cd861fdfca020f88519e0f21](https://github.com/fastapi/typer/tree/a5882dedf0bc7a46cd861fdfca020f88519e0f21)，见[单仓审查](./typer.md)。20项普通CLI增强，全部未实施；新API名均为拟议契约。

已有Literal/Enum、Optional、单层list/固定tuple、datetime、custom parser/click_type、Context资源清理、env/default_map、callback/result_callback、子命令/补全、Rich help/错误和同函数多名称注册均已排除。对不支持的注解、async awaitable返回及位置/覆盖策略均明确标增强，不冒充既有BUG。

## 01．可等待的命令及生命周期回调

- **类型与业务场景**：增强提案；商品命令本地异步读取/计算完成后再返回退出码。
- **原版观察**：async命令当前exit0但return_value仍awaitable且无输出；夹具显式close协程，未冒称业务执行成功。
- **交付目标**：新增明确async执行入口及callback/result_callback等待规则，与测试runner一致，确保关闭资源后才完成。
- **真实模块**：typer/main.py、typer/core.py、typer/testing.py。
- **兼容边界**：同步默认保持；已有运行loop时使用可await入口，不嵌套asyncio.run；不自动并发所有回调。
- **正常验收**：本地await sleep(0)后输出异步完成，返回实际值；sync/async回调按声明阶段执行。
- **边界验收**：取消、异常、已运行loop、子命令、ctx资源清理、async生成器支持范围和退出码回归。
- **原生回归**：tests/test_core.py、tests/test_exit_errors.py。
- **实际依赖**：无；标准库asyncio/inspect；不引入网络客户端。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/testing.py)。

## 02．日期时间与时长的注解类型族

- **类型与业务场景**：增强提案；商品交付日期、营业时间和本地任务时长以明确类型输入。
- **原版观察**：date注解RuntimeError；datetime及formats选项已存在。
- **交付目标**：新增date/time/timedelta的原生类型适配，定义ISO日期、时区时间和明确单位duration语法，贯穿帮助、错误和补全提示。
- **真实模块**：typer/main.py、typer/models.py、typer/params.py。
- **兼容边界**：已有datetime不改；自定义parser可用但不是完整内建语义，禁止猜10表示天还是秒。
- **正常验收**：日期只得到date，时间只得到time，2h30m时长得到150分钟，帮助显示支持语法。
- **边界验收**：无效日期、闰日、负时长、offset、空值、Optional、重复列表和formats适用边界回归。
- **原生回归**：tests/test_types.py、tests/test_type_conversion.py。
- **实际依赖**：无；标准库datetime，格式规则须本地固定。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/params.py)。

## 03．明确优先级的多类型Union参数

- **类型与业务场景**：增强提案；商品标识可以是数字ID或文本名称，并需说明实际选择的类型。
- **原版观察**：int|str构建触发Currently does not support Union断言；Optional[T]已有。
- **交付目标**：新增受限定Union解析策略，声明first-match或discriminator，失败聚合各分支原因，成功保留所选类型。
- **真实模块**：typer/main.py、typer/models.py、typer/utils.py。
- **兼容边界**：Optional默认保持；不能让str分支静默吞所有错误；模糊值优先级必须用户可见。
- **正常验收**：42按选定优先级成int，coffee成str，二者回调收到真实类型。
- **边界验收**：bool/int、Path/str歧义、多个失败、Annotated约束、None、列表Union和自定义parser回归。
- **原生回归**：tests/test_types.py、tests/test_annotated.py。
- **实际依赖**：无；现类型适配及标准库typing；不依赖Pydantic。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/utils.py)。

## 04．精确金额参数与Decimal约束

- **类型与业务场景**：增强提案；本地价格工具需要精确到分且支持金额上下限。
- **原版观察**：Decimal注解RuntimeError；每个参数可手工parser=Decimal，现min/max主要按int/float映射。
- **交付目标**：增加原生Decimal类型，精确min/max、scale/舍入策略和错误文案，不经过float比较，默认值/补全元数据一致。
- **真实模块**：typer/main.py、typer/models.py、typer/core.py。
- **兼容边界**：已有float/int及自定义parser保持；小数点/精度策略显式，不默认改成本地区域解析。
- **正常验收**：0.10与0.20输入精确相加为0.30，边界金额逐十进制比较正确，help不出现浮点噪声。
- **边界验收**：NaN/Inf、科学计数、负零、超scale、quantize舍入、Optional/列表及非法金额回归。
- **原生回归**：tests/test_types.py、tests/test_type_conversion.py。
- **实际依赖**：无；标准库decimal；无需财务服务或数据库。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)。

## 05．dataclass记录展开成参数组

- **类型与业务场景**：增强提案；同一商品记录复用于导入和导出命令，希望统一字段约束及默认。
- **原版观察**：dataclass Product注解RuntimeError；普通函数参数和Typer子组已有。
- **交付目标**：新增显式dataclass参数组适配，按字段前缀展开，验证后构造记录，支持嵌套组和组级帮助。
- **真实模块**：typer/main.py、typer/models.py、typer/utils.py。
- **兼容边界**：不把所有未知类自动当记录，不执行任意构造器猜字段；基础阶段限定标准dataclass，Pydantic可作为后续适配。
- **正常验收**：--product.name coffee/--product.quantity 2构造Product，两个命令共享定义但默认对象独立。
- **边界验收**：default_factory、kw-only、frozen、嵌套/递归类型、重名flag、字段别名和partial group回归。
- **原生回归**：tests/test_annotated.py、tests/test_types.py。
- **实际依赖**：无；标准库dataclasses；单步包含解析、构造、help和错误，不拆小步。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/utils.py)。

## 06．有类型的重复键值映射

- **类型与业务场景**：增强提案；商品标签数量通过重复--label color=1等输入。
- **原版观察**：dict[str,int]注解RuntimeError；列表及固定tuple已有。
- **交付目标**：新增映射参数语法，按key/value注解转换，声明重复键覆盖/拒绝和split/转义规则，回调接收dict。
- **真实模块**：typer/main.py、typer/models.py、typer/core.py。
- **兼容边界**：不将任意含等号字符串自动当映射；普通str/list原样，完整JSON输入可作为显式替代模式。
- **正常验收**：两次--label得到两个正确int值，重复键按策略处理并保留确定顺序。
- **边界验收**：键含等号、空key/value、Unicode、非法value、Enum键、Optional、envvar拆分和shell补全回归。
- **原生回归**：tests/test_types.py、tests/test_type_conversion.py。
- **实际依赖**：无；标准库映射与已有类型转换。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)。

## 07．重复的成组参数记录

- **类型与业务场景**：增强提案；本地采购命令重复指定--item coffee 2和--item tea 5。
- **原版观察**：list[tuple[str,int]]被List types with complex sub-types断言拒绝；单层list和固定异构tuple已支持。
- **交付目标**：新增重复复合记录参数，按固定组宽消费并逐元素转换，保持各次组边界和顺序。
- **真实模块**：typer/main.py、typer/core.py、typer/models.py。
- **兼容边界**：不改变已有list单值或tuple固定一次语义；不把任意深嵌套容器全部纳入第一版。
- **正常验收**：两次--item得到[(coffee,2),(tea,5)]，help标明每组两个值，错误定位第几组第几项。
- **边界验收**：缺组项、多余项、可选空列表、负数被误当flag、envvar编码、tuple内Enum/Path和默认组回归。
- **原生回归**：tests/test_types.py、tests/test_type_conversion.py。
- **实际依赖**：无；现multiple/nargs与转换器扩展。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)。

## 08．声明式参数之间的业务约束

- **类型与业务场景**：增强提案；本地导出只能选CSV或JSON之一，指定range时必须同时有start/end。
- **原版观察**：有参数callback但无relations/required_if声明；应用需手工检查多个ctx.params。
- **交付目标**：新增命令级关系规则互斥/至少一项/依赖/成对出现，按最终解析值评估并产生统一参数定位。
- **真实模块**：typer/main.py、typer/models.py、typer/core.py。
- **兼容边界**：单字段callback和required保持；关系检查时机与prompt/env/default值来源明确，不把False/0当缺失。
- **正常验收**：互斥两格式同时输入被拒绝，start无end指出依赖，合法组合只调用业务一次。
- **边界验收**：默认/显式同值、嵌套组、envvar、未知字段、多个失败、prompt取消和eager --help不触发业务回归。
- **原生回归**：tests/test_core.py、tests/test_ambiguous_params.py。
- **实际依赖**：无；命令metadata和现解析结果；可独立于记录参数组。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)。

## 09．本地配置文件与参数来源组合

- **类型与业务场景**：增强提案；商品工具把常用quantity等默认放本地TOML，再用env/CLI覆盖。
- **原版观察**：default_map和envvar已有，但Typer无config_files集成声明。
- **交付目标**：新增可选本地文件源适配，受限格式先转default_map，声明config/env/CLI/default优先级与未知键处理，重用参数类型校验。
- **真实模块**：typer/main.py、typer/core.py、typer/models.py。
- **兼容边界**：不是新增default_map或envvar；默认不读隐式文件，不访问URL或远程配置；路径及编码显式。
- **正常验收**：TOML quantity=2、env=3、CLI=5按规则得5，错误定位来源键，原文件不改。
- **边界验收**：缺文件、坏格式、子命令段、unknown keys、None/空值、多个文件顺序和默认工厂回归。
- **原生回归**：tests/test_core.py、tests/test_others.py。
- **实际依赖**：JSON/TOML标准库；YAML若纳入需明确可选依赖，不先引入。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)。

## 10．版本化命令元数据清单

- **类型与业务场景**：增强提案；本地GUI和文档生成器需要读取命令、字段、约束与默认来源。
- **原版观察**：可读get_command(app).params，当前app无to_schema，底层命令也无to_info_dict。
- **交付目标**：新增版本化manifest，表达命令树、参数名/类型/choices/range/env/default及未知动态项；输出纯数据而非扫描Rich文本。
- **真实模块**：typer/main.py、typer/models.py、typer/core.py。
- **兼容边界**：现元数据仍可内省，不声称help是唯一信息源；不执行default_factory/回调填假默认值。
- **正常验收**：商品命令manifest可JSON序列化，quantity范围与真实parser一致，Literal choices原样。
- **边界验收**：自定义parser/类型、不可序列化default、lazy命令占位、别名、子组、回调动态约束与版本兼容回归。
- **原生回归**：tests/test_core.py、tests/test_types.py、tests/test_rich_utils.py。
- **实际依赖**：无；标准库JSON数据；不依赖前面新增类型。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)。

## 11．按需加载的本地子命令

- **类型与业务场景**：增强提案；大型本地工具启动help时不导入所有重型业务模块。
- **原版观察**：registered_commands保存已有function引用，无add_lazy_command；add_typer需已构造实例。
- **交付目标**：新增明确的本地module/factory lazy注册，保留轻量name/help描述，仅选中命令或需深度内省时加载并缓存。
- **真实模块**：typer/main.py、typer/models.py、typer/core.py。
- **兼容边界**：现eager注册保持；不从远程拉插件，不隐式扫描执行任意包；错误按选中模块定位。
- **正常验收**：根help不触发重型模块计数，选中一次加载并可运行，同一应用重复调用按规则缓存。
- **边界验收**：循环加载、导入失败、命名碰撞、completion深度、并发首次加载、子组与factory返回非法值回归。
- **原生回归**：tests/test_core.py、tests/test_others.py。
- **实际依赖**：标准库importlib；不引入插件下载机制。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)。

## 12．应用级类型适配注册

- **类型与业务场景**：增强提案；多个商品命令共用自定义SKU类型，希望一次声明解析/帮助/补全和反向表示。
- **原版观察**：每个Option可指定parser或click_type，但无app.register_type_adapter。
- **交付目标**：新增显式按annotation注册的适配协议，统一parse/metavar/constraints/complete/serialize，定义应用/子应用继承与优先级。
- **真实模块**：typer/main.py、typer/models.py、typer/utils.py。
- **兼容边界**：每参数parser/click_type优先规则保留并明确；不能全局猴补或因注册一个app影响另一个。
- **正常验收**：两个命令同SKU注解自动用同适配，单参数override可用，另一个未注册app不受影响。
- **边界验收**：Annotated/NewType/泛型、重复注册、子app覆盖、递归适配、解析异常与缺serialize能力回归。
- **原生回归**：tests/test_types.py、tests/test_type_conversion.py、tests/test_annotated.py。
- **实际依赖**：无；现类型/回调协议；前面类型族可独立内建实现，不强制依赖该registry。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/utils.py)。

## 13．带调用作用域的本地依赖提供

- **类型与业务场景**：增强提案；商品命令注入同一次调用共用的本地仓储对象，并在结束时关闭。
- **原版观察**：Context和with_resource已有，Depends入口不存在；需根callback设置ctx.obj再各处手工取。
- **交付目标**：新增显式Depends提供者图，按调用作用域缓存，支持局部覆盖和生成器资源清理，先完成参数校验再创建依赖。
- **真实模块**：typer/main.py、typer/models.py、typer/utils.py。
- **兼容边界**：不替换既有Context/with_resource，清理可复用其机制；不注入任意未声明参数或启动外部服务。
- **正常验收**：一个命令两个消费者共享本地对象，正常/异常均清理一次，CliRunner可覆盖provider。
- **边界验收**：依赖环、factory错误、嵌套作用域、命令取消、help不创建资源、线程隔离和异步组合回归。
- **原生回归**：tests/test_core.py、tests/test_type_conversion.py。
- **实际依赖**：标准库上下文管理；同步能力可独立交付，async组合依步骤01另验。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/utils.py)。

## 14．可机器读取的CLI错误结构

- **类型与业务场景**：增强提案；本地任务调度器需要稳定的错误类别和参数路径。
- **原版观察**：非法quantity退出2且Rich stderr是英文文本，CliRunner异常是SystemExit，无error_info。
- **交付目标**：新增opt-in结构化错误记录及JSON渲染，含code/command/parameter/message/exit_code；保留普通文本默认。
- **真实模块**：typer/core.py、typer/rich_utils.py、typer/testing.py、typer/_click/exceptions.py。
- **兼容边界**：不把SystemExit改成业务成功，不默认输出参数原值；旧stdout/stderr与退出码保持。
- **正常验收**：bad quantity产生稳定invalid_parameter及--quantity路径，JSON可解析，默认Rich文本未改。
- **边界验收**：unknown command/option、缺参、关系错误、用户BadParameter、Unicode、宽终端和异常tracebacks回归。
- **原生回归**：tests/test_exit_errors.py、tests/test_rich_utils.py、tests/test_tracebacks.py。
- **实际依赖**：无；标准库JSON与已有异常对象。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/rich_utils.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/testing.py)；[源码4](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/_click/exceptions.py)。

## 15．按调用作用域选择界面语言

- **类型与业务场景**：增强提案；本地中文商品工具需要help分组和常见错误也按中文显示。
- **原版观察**：中文业务输出正常，但原Invalid value英文；Typer无locale构造参数。
- **交付目标**：增加显式translation/catalog上下文，覆盖框架help/错误固定文案，支持默认与回退；命令和flag标识保持稳定。
- **真实模块**：typer/main.py、typer/core.py、typer/rich_utils.py。
- **兼容边界**：不翻译用户实际参数值，不全局切locale影响其他app；默认英文输出兼容，外部help可由应用自行翻译。
- **正常验收**：同命令两个独立调用分别显示中文/英文固定提示，解析得到同值和同退出码。
- **边界验收**：缺catalog、复数/格式占位、Rich/plain、嵌套app、并发CliRunner、Unicode宽度和自定义错误回归。
- **原生回归**：tests/test_rich_utils.py、tests/test_core.py、tests/test_exit_errors.py。
- **实际依赖**：标准库gettext或轻量catalog；不需要远程翻译。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/rich_utils.py)。

## 16．全局选项可选择的跨命令位置

- **类型与业务场景**：增强提案；本地用户希望tool --verbose export与tool export --verbose语义一致。
- **原版观察**：根verbose放export前成功，放后No such option退出2；这是当前命令分层解析。
- **交付目标**：新增opt-in inherited/global option声明，在匹配子命令范围内解析共享选项并记录其拥有者。
- **真实模块**：typer/core.py、typer/main.py、typer/models.py。
- **兼容边界**：默认位置规则保持；同名局部选项优先/冲突需显式，不从任意字符串中偷取父参数。
- **正常验收**：两种位置都使父verbose=True，子参数仍按自己的类型处理，业务只执行一次。
- **边界验收**：多级子命令、--终止、位置值恰似flag、重复全局项、短flag组合、envvar和help所属回归。
- **原生回归**：tests/test_core.py、tests/test_tutorial/test_commands/test_context/test_tutorial003.py。
- **实际依赖**：无；现token解析及参数所有权。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)。

## 17．显式默认子命令分派

- **类型与业务场景**：增强提案；本地商品工具不写show时仍能按show的参数规则查询。
- **原版观察**：无default_command选项；invoke_without_command与no_args_is_help已有，当前根空调用报Missing command。
- **交付目标**：新增显式default_command配置，未匹配具名命令时按声明目标分派并使用其参数/help，定义默认参数前置位置。
- **真实模块**：typer/main.py、typer/models.py、typer/core.py。
- **兼容边界**：不重复已有空callback执行；现无默认命令应用保持，真正unknown子命令不应随意当默认位置参数。
- **正常验收**：tool coffee与tool show coffee按声明等价，tool export仍走具名export，root --help不执行默认业务。
- **边界验收**：默认命令不存在/循环、子app、未知token歧义、required参数、completion、callback顺序和退出码回归。
- **原生回归**：tests/test_core.py、tests/test_suggest_commands.py。
- **实际依赖**：无；本地命令路由；不依赖lazy加载。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)。

## 18．具有规范名称的命令别名

- **类型与业务场景**：增强提案；本地工具保留旧list-products简称ls，但help只突出一个规范命令。
- **原版观察**：command无aliases参数，同函数可多次用不同name注册；只是重复独立命令信息。
- **交付目标**：新增first-class alias metadata，别名路由到同一规范命令，help/completion去重，可为旧alias单独标弃用提示。
- **真实模块**：typer/main.py、typer/models.py、typer/core.py。
- **兼容边界**：多次装饰现有行为保持；不是声称没有任何命令别名替代；命令flag/环境名规范身份明确。
- **正常验收**：show/ls调用同一逻辑与参数，help显示规范show并注明别名，弃用提示只对旧名出现。
- **边界验收**：alias碰撞、链/循环、多级子组、hidden命令、suggestions、completion和错误usage名回归。
- **原生回归**：tests/test_core.py、tests/test_hidden.py、tests/test_suggest_commands.py。
- **实际依赖**：无；命令metadata；可独立检查碰撞，不依赖步骤19。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)。

## 19．命令注册碰撞的显式策略

- **类型与业务场景**：增强提案；本地多个模块合并命令时需要发现两个show互相覆盖。
- **原版观察**：两次注册show不报错，实际执行second；get_group_from_info用同名dict项覆盖。
- **交付目标**：新增opt-in error/warn/replace注册策略，记录两个声明来源，覆盖命令/组/无名合并组之间的碰撞。
- **真实模块**：typer/main.py、typer/core.py、typer/models.py。
- **兼容边界**：现replace默认可保持；不把既有最后注册获胜直接叫BUG，显式严格模式才拒绝。
- **正常验收**：error模式在构建阶段指出两个show的函数/模块，replace模式仍执行second。
- **边界验收**：同函数重复、alias/组碰撞、无名add_typer、lazy加载后冲突、父子同名合法范围和稳定顺序回归。
- **原生回归**：tests/test_core.py、tests/test_others.py。
- **实际依赖**：无；字典注册与轻量来源记录。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)。

## 20．类型值到可逆argv的构造

- **类型与业务场景**：增强提案；本地GUI用已验证的商品字段生成可复制的命令参数列表。
- **原版观察**：CliRunner接受argv，但Typer无build_argv；调用方需手工拼bool/list/tuple/子命令。
- **交付目标**：新增独立argv builder，按现command metadata编码typed values，生成token列表并支持重解析对照，不默认拼shell字符串。
- **真实模块**：typer/main.py、typer/core.py、typer/models.py。
- **兼容边界**：默认调用与CliRunner不变；shell quoting由另一个显式展示步骤处理，不把shell字符串当token列表。
- **正常验收**：商品name=咖啡/quantity=3生成可直接invoke的argv并得到同结果，bool双flag与重复列表正确。
- **边界验收**：默认值省略策略、None/空集合、Path含空格、Enum/Literal、位置参数、子命令、未知字段和不可逆自定义parser回归。
- **原生回归**：tests/test_types.py、tests/test_core.py、tests/test_type_conversion.py。
- **实际依赖**：无；现metadata和类型；自定义类型可明确提供codec，不依赖步骤12registry。 功能步骤依赖：无，组合场景另行累计回归。
- **依据**：[源码1](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)；[源码2](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)；[源码3](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)。

## 控制端冻结及累计回归

未来以纯本地合成商品命令调用真实Typer/CliRunner，验证exit_code、stdout/stderr、callback调用次数、真实类型、解析往返、资源关闭及应用之间状态隔离。所有文件/环境使用临时目录，async用本地受控协程；不需要远程服务或账户。每项包括代码/测试/文档的完整交付，未拆小修凑步。每步累计关联原生测试；原版通过不等于20步新增契约已通过，冻结验收和正式接入尚未开始。
