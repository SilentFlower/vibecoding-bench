# 第一阶段可信原生回归和交付合同

## 已记录决定

auto-loop决定 `DEC-0001` 复用既有 `implementation_dir`，明确允许其为导入模块对应的 `.py` 文件；不复制新的验证框架，不改变旧套件默认路径、私有runner或冻结合同。

## 实际接口及约束

- `_suite_paths(suite)` 仍返回实现与导入根两个相对Path；只接受 `import_root / package模块路径` 或对应 `.py` 文件，拒绝绝对路径、`..`、模块名／实现不匹配。
- `_overlay` 对文件类型核真实文件及父目录无链接、在候选内，解析并比较原版pytest控制声明，仅覆盖该模块文件；原版测试／配置与其他文件保持。
- 校准、实际导入、冻结主／子节点与错误安装库拒绝仍由现有产品链验证；这次路径扩展本身不代表xmltodict或decouple已经完成原生准入。

## 验证范围

定向验证单文件覆盖保留原版测试和配置、新测试不进入冻结树、收集钩子／插件声明／链接拒绝、精确文件路径与旧默认保持。后续分别在当前目标镜像真实注册、校准并验证各仓候选绑定；结果另附，不提前声明通过。

首轮单文件定向回归14项通过。按已确定的起始四仓准入计划，可信SUITES增加cachetools的src布局与子测试、xmltodict／decouple单文件和tabulate原生默认集合；tabulate的16个模块doctest从固定源码提取并恢复，README仍来自原版测试树，不能允许候选改文档后保留相同节点名蒙混通过。四仓没有把历史主项总数写成通用硬编码，当前镜像校准与候选合同另行实际执行。

## 后续四仓的实际原生差异

- Click使用固定src实现及真实pyproject版本元数据。原生测试会调用importlib.metadata，因此只在/work独占venv补固定分发元数据和受控源码路径，不安装另一份Click实现；退出后全部删除。
- Click分页原生测试真实依赖less，目标Bookworm镜像未内置。冻结官方less 590-2.1~deb12u2的deb、匹配源文件、完整许可和提取二进制，逐项SHA见 `click-pager-provenance.json`。制品保持普通数据权限，仅在验证器已有可执行/work内校验并复制为本次venv/bin/less，不改系统或挂载安全选项。
- 原生Click测试会生成并执行pager脚本，因此pytest的basetemp指定到既有/work。原/tmp继续保留原安全选项；没有跳过缺工具或执行位失败的测试。
- Boltons需要全部153个doctest和12个子测试。Stats模块会删除类内_calc方法并导出新函数，不能只按静态AST名称恢复示例。受控子进程只导入冻结原版，以实际doctest导出名提取原文；候选的类方法绑定对象在真实__func__上恢复，不使用候选自改示例。
- Mistune按真实src路径保留1324主项和158子项；CLI Helpers保留96项（92通过、4跳过），不把跳过说成通过。

最新共享适配定向回归20项通过，覆盖多模块／动态导出示例、类方法、私有分发元数据和真实离线工具的摘要／越界／已存在入口拒绝及清理。逐仓成功校准编号和摘要见 `next-native-baselines.json`；此前失败日志完整保留。原有十项目和已冻结起始草稿／模拟快照的私有runner字节保持，正式业务和整链准入另验。

## 第三内部小批的真实入口

共享可信适配继续复用同一受控复制、实现覆盖、源码绑定、进程组时限和schema1合同，没有另建平台验证器。Python-Markdown沿上游unittest discover tests运行，真实TestCase.id、结果、跳过理由及候选导入逐项冻结；当前1129项为1019通过／110原生跳过。分发入口仅从固定pyproject写入/work独占venv元数据，不安装另一份Markdown。

ConfigObj保留79项pytest，并逐个执行上游src/tests/configobj_doctests.py和configobj.validate原入口的初始化、globs与异常匹配标志。两入口分别326／198个实际doctest示例，合计524；冻结name／ordinal／source及want摘要／flags／结果，候选相同名称改预期也会恢复原文并拒绝。主项与补充示例分别计数。

More-itertools实际765主项／21194子项。上游并发测试创建100线程，回归PID从临时默认64校准为128，处于既有16..256合同，业务仍64；校准工具已改为读取并校验真实profile.regression，时限及内存不再硬编码。Dataset在当前SQLite环境61项通过；不能称PostgreSQL／MySQL分支已执行。最新四仓完整共享runner字节与校准／合同摘要见third-native-baselines.json，原失败现场保留。

共享适配24项定向回归通过，覆盖实际unittest发现／错误实现／候选删改测试／空集合／skip漂移／子项失败以及原始doctest初始化与同名预期篡改。正式旧十仓及前面已冻结的小批runner保持其实际校准字节。

## 内容交付过滤的实际差异

首轮Git导出发现Tabulate自身.gitignore会忽略四个上游原件，以及Decouple两个公开测试.env。前者不修改上游ignore文件，Git导出与后续精确暂存只强制加入冻结的四条文件路径；后者仅对固定两个正式路径保留原SHA，源码快照过滤、Gitignore和Dockerignore同步；未知.env仍忽略，改字节或链接被拒绝，见public-env-proof.json。

前四仓正式v5-en全部3362文件通过Git临时索引导出和真实Docker COPY的全集／SHA／执行位对账，旧3069个非catalog文件未变，模拟子集与正式目录逐项目／环境字节一致而非假称目录摘要相同；失败attempt-001和成功attempt-002分别保留，汇总见delivery-first-four.json。

## 第四内部小批：真实打包产物和包内原生测试

Markdown-it-py完整181跟踪文件、原生1032项在当前镜像全过，pytest-regressions／datadir／timeout按实际wheel entry_points显式加载，保留CommonMark语料和flit sdist断言。Path完整32个跟踪文件及构建生成MIT原文独立保留，生成物不伪称Git原件；143主项含27模块doctest，142通过／1上游Windows跳过。Path按原AGENTS要求完整获取并阅读上游skeleton文档，具体证据和许可来源见path-generated-artifact.json。

PETL从固定提交既有构建产物保留实际petl/version.py，开发版本和gcd5ed9dd3提交前缀及SHA单独证明，不用安装库替代候选；上游明确pytest<9，环境固定8.4.2。其923个已收集用例为912通过／11跳过，另有12个可选依赖模块在收集阶段跳过；XML总935、skip23分别对账。新可选collection_skips合同冻结实际nodeid／行／理由，不将模块跳过冒充运行过的用例；旧套件保持原合同。

PETL与Toolz的测试位于实现包内，显式冻结test_roots，恢复完整原测试及其夹具、排除候选新测试，不能让候选改断言后保持同一nodeid蒙混通过。Path与Toolz原生doctest原文从受控子进程的固定原版模块提取，排除包内tests目录。

Toolz提供固定1.2.0分发元数据，仅在/work独占venv生成metadata，不装另一份实现。首次原生失败来自本轮文档恢复适配覆盖InstanceProperty动态描述符；错误类名的第二次失败也原样保留。修正为只更新实际InstanceProperty.classval，实例仍动态组合其函数／处理器文档；第三次完整193项为192通过／1上游Python版本跳过。共享适配27项定向回归通过，包含动态实例文档、真实收集阶段skip／XML／合同漂移拒绝，以及包内原测试与夹具冻结。逐仓校准、私有runner及合同摘要见fourth-native-baselines.json。

Path取消恢复工程目标仅覆盖yield用户块异常，最小参考与两项公开测试已在当前镜像完成原版失败／参考通过／常见内置异常特判反例拒绝，完整143原生集合通过。新业务及整链准入另验，不把单一工程结果当全阶段完成。

## 第五小批：局部版本元数据、嵌套unittest与固定夹具别名

JSON Schema在独占验证venv补该固定检出的真实开发版本0.1.dev1+gc497561ea及原pyproject中MIT License-Expression，不安装另一份实现。首轮元数据缺字段导致原test_license失败，修复控制支架后完整8529项为8297通过／232上游skip；失败原件保留。

Docutils按原生工作目录docutils/test执行标准unittest discover，实际459主项457通过／2skip，另1776子项。子项重复上下文和出现序号不折叠，临时项目根只替成$PROJECT稳定身份；子项skip单列，不能把父项误计skip，子失败仍令父失败。仅私有测试树将六个已核Git CSS别名blob按受控目标复制成普通文件；原源码和其他sandbox别名blob保持原字节。不是沙箱全量运行或多Python矩阵。

Agate原生396全过；CSVkit355主项351通过／4Windows skip及31子项单列。CSVkit镜像en_US.UTF-8已实际确认可用。共享控制适配30项定向测试通过，包含真实嵌套unittest、重复子项／子skip／路径规范化／错误实现／skip理由漂移、夹具原件不变与越界拒绝、开发版本与许可注入拒绝。逐仓控制字节、合同和资源见fifth-native-baselines.json；已冻结前批私有runner不随共享版本自动改写。

## 第六小批：真实构建依赖与只读业务观察

Python-Box完整159项通过，TOON依赖按固定Git提交使用上游uv_build构建真实wheel，运行源码和许可证逐文件比对；不从已安装目录重打包冒充wheel，见toon-wheel-provenance.json。Box点号输入顺序的业务观察失败保留了五轮完整证据：前三轮是观察器遗漏构造阶段实际异常，第四轮是额外debug字段违反严格JSON对象键集合，第五轮按真实边界输出精确字段后通过。没有改变产品严格比较器或独立期望，复盘见box-observation-retrospective.md。

Rich实际981项为956通过／25跳过，保持其上游支持的pytest7／attrs21／Pygments2.19依赖组合。Pydash实际2880项全通过，含359个真实模块doctest；原src绑定及原生示例恢复保持。ConfigArgParse169主项为164通过／5xfail，225子项另计。各仓当前控制脚本、精确依赖和合同见sixth-native-baselines.json，业务回归和平台模拟分别对账。

## 最后六仓：真实nose2入口和离线内存开销

Backoff真实123项、Bottle含Jinja2／Mako依赖的382项通过；Cerberus ISC许可，嵌入cerberus/tests按固定test_roots恢复，247主项为246通过／1项Python2跳过。IceCream使用原生unittest入口65项通过；该包导出会覆盖包__file__，业务候选绑定用实际类定义文件，不能据此误判安装库替换。

Dpath保留原nose2.discover，显式关闭用户配置并加载官方nose2.plugins.junitxml，不改用pytest替代。通过原生startTestRun和testOutcome hook读取真实函数测试、TestCase完整集合及结果；记录stdlib、nose2主模块和官方XML插件的实际版本／文件SHA。成功、失败、错误、跳过、预期失败及意外成功分别归并，未知结果受阻；候选导入仍须落在受控源码树，不能替换测试。校准与参考完整79项通过，Hypothesis生成例不拆成独立主项。

新增定向用例实际在安装nose2的独立venv执行，全部31项通过、无skip，覆盖函数／TestCase发现、官方XML、预期失败／意外成功、skip理由变化、候选篡改和框架合同漂移拒绝。宿主缺可选nose2时的skip不能代替这条真实验证。

DeepDiff完整默认1308主项为1264通过／44项上游跳过，未开启额外慢测试或裁剪默认集合。前三轮512MB内存失败保留，定位到原30线程／30000个Future测试；限制glibc arena仍不足。原生离线准备改为pip显式--no-compile，保留全部精确wheel和源码，第四轮原资源内通过。此开销来自/work内存文件系统的依赖及额外字节码，不把历史只读宿主依赖挂载的256MB结果误作当前证明。业务档案显式512MB／30秒，回归512MB／180秒，不修改账号资源或并发；见deepdiff-resource-calibration.md和seventh-native-baselines.json。

Dpath另交付一个已复现的业务修复目标：原delete值过滤分支忽略glob，误删范围外同值字段。参考只修交集条件并新增四项公开unittest；原版业务与公开测试失败、参考通过、错误“或”候选被拒，完整79项nose2通过。不是为凑任务类型而制造缺陷，独立原件见business/dpath/attempt-001及dpath-admission.json。

## Docutils完整来源与构建过滤

正式Git导出已保留上游data／target等同名原件；源码快照首次仍丢失15个Git跟踪.log和两个target夹具目录的19文件，失败delivery/attempt-007原件保留。仅给这15条固定文件路径及两个完整目录清单增加SHA白名单，目录摘要含所有文件相对路径、SHA与执行位；额外文件、内容变化及链接被拒绝，未知.env／日志仍过滤。Dockerignore仅同步两个精确target路径，未广泛开放target或.env。

28项部署管理回归通过，含新增真实原件正例及额外文件／内容篡改／链接反例。随后delivery/attempt-008实际Git与scratch Docker COPY的9729文件全集、字节、执行位一致；旧3069个非catalog文件保持，临时资源已清理。该结果是本地交付证明，不是部署或镜像发布；逐项见delivery-first-twenty.json。
