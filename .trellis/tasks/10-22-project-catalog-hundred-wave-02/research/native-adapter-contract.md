# 第二阶段可信原生入口合同

本阶段固定三十仓逐项复核来源和完整适用入口，复用已完成第一阶段的可信回归、候选隔离、冻结合同与实际交付，不改变此前四十仓私有副本。新增能力先测试再校准；当前仍在实施，不能据设计计为通过。

## 起始四仓

- alive-progress：实际tests完整pytest，about_time与graphemeu按setup.py精确冻结。
- JMESPath：完整tests及compliance／legacy，不设置JMESPATH_TEST裁剪。
- Confuse：完整test集合，原生Sphinx可选发行模块的收集跳过单独保留，不与主项重复计数。
- Simplejson：沿官方simplejson.tests._cibw_runner，保留all_tests_suite的C与NoExtensionTestSuite纯Python两轮及index.rst示例。实际候选C源码在现有/work可执行临时树构建，REQUIRE_SPEEDUPS仅约束构建；测试前额外核make_encoder／make_scanner接线，逐轮保留原始ID与上下文，拒绝重复ID折叠或缺失C轮。当前目标为Linux／CPython3.12，不冒称其他平台／调试或无GIL矩阵已通过。

## 证据边界

固定研究报告是历史线索。逐仓当前原生、业务、错误候选、产品链、页面／API／数据库及Git／Docker收据完成后，才能将本阶段项目计为本地正式准入；全部三十仓通过后才提交本阶段。

## 结构校验修正

起始两仓业务实际通过后，内容校验拦住了披露目录误放；已按既有disclosure前缀修正，并将真实内容／环境校验提前到草稿序列化入口。业务原件的程序、验收规格及授权未变。Simplejson前两次原生562项通过，但节点携带额外mode／raw_id不符合平台既有三字段合同；改为节点仍只有id／kind／outcome，原始ID和两轮上下文另存合同顶层unittest_contexts并精确比对。旧合同与原件保留，不作为正式内容通过，当前副本重新校准。

## 官方工厂顺序校准

Simplejson参考第一次完整回归实际562项为486通过／76跳过、逐节点和双轮上下文均匹配，但官方工厂按os.listdir顺序加载，原生skip表按回调顺序写入使相同身份／理由仅因顺序而拒绝。仅该官方入口的skip表改为按完整身份排序，保留每个条目与原因，不改变发现、执行、主项、上下文或既有套件。旧回归失败原件保留；重新校准后只重跑受影响的完整回归，其他真实业务程序和期望未变。

## 收集摘要与公开校验一致

Simplejson参考回归第二次实际562项全部符合冻结结果，但ProjectVerifier按既有id／kind摘要检查，runner此前把额外模式字段带入摘要而被拒绝。现明确按原两字段计算摘要；模式／原始ID仍保存在独立unittest_contexts并严格核对。旧套件collection本就只有两字段，其摘要保持不变。保留失败原件，仅重跑受影响的参考完整回归。

## Marshmallow当前时间参数身份

完整1192项原版通过，但参考回归只有1190项被选中，真实missing_frozen_nodes为2。已读test_deserialization.py的完整参数表：索引9／10在收集时用datetime.now生成字符串，原ID含秒数，每轮自然不同。只对该固定测试的in_value索引9／10按参数位置规范命名，保留所有11项及原始运行参数；真实旧ID／值进入parameter_identities证据，不改测试输入、断言、测试时钟或候选。旧套件没有此配置，保持原路径。重新冻结完整集合后再跑受影响回归，失败原件保留。

## tqdm同镜像离线Tk依赖

实际当前目标镜像导入_tkinter缺libtk8.6.so／libtcl8.6.so。按既有固定Debian研究依赖镜像原件导出18个共享库、17个包的版权，来源镜像、dpkg版本和逐文件SHA保留；不拷贝libc／动态加载器。系统库清单SHA在私有runner冻结，逐文件再核SHA和普通路径，无安装或系统改写；只给原生子进程设置只读制品LD_LIBRARY_PATH。仍用当前原账号镜像和完整Python原生入口，保留Tk导入测试；性能项按上游tox原-k not perf。当前回归预算512MB／64pids先实际测量，未预先增加。

## tqdm业务准备内存

按真实ProjectVerifier准备入口实测256MB OOM且未出现ready标记；512MB正常准备并完成实际原版任务。只将本仓业务内存设为512MB，PID64／业务时限30秒／无网／UID1000／只读和回归档案保持；旧项目不变。失败准备不算业务失败。

## Pluggy原生分发链接元数据

本仓自身是pytest依赖，环境不安装另份Pluggy，私有venv用固定候选路径及已核SCM元数据。首次225项中224通过，唯一失败为原生test_package_metadata_links_to_repository要求Repository元数据。已核完整pyproject，按其实际project.urls写Project-URL到私有dist-info，不改源码、测试或真实安装，不发请求。原有套件未启用project_urls，原行为保持；重新校准全部225项。

## Dynaconf原生命令与元数据

首次完整567主项中564通过、2失败、1原生xfail；失败明确来自找不到dynaconf命令和importlib.metadata分发。固定pyproject.scripts声明dynaconf.cli:main，VERSION为3.3.0-dev0；沿已有私有分发绑定补规范化3.3.0.dev0元数据，并只在本次独占venv生成该命令入口。私有.pth指向实际候选源码，不安装另一份Dynaconf，也不改原测试或95%覆盖率门槛。入口名称／模块／函数严格核格式，拒绝覆盖现存文件；真实子进程测试证明候选变化会改变命令结果，并核注入拒绝及退出清理。第二次原集合566通过、1xfail，17个integration沿上游本地入口不选中；失败原件保留。旧套件未启用console_scripts，入口和行为保持。

## 独立模拟审计中的收集跳过

Confuse真实299主项通过，Sphinx可选发行模块另有1个原生收集跳过，所以JUnit为300条。第二小批产品链本身通过，旧审计按主项299核XML导致拒绝；现独立核冻结collection_skips完整身份／行／理由／状态、计数及匹配标志，再分别核主项、XML跳过与无错误。不删除跳过、不冒充第300个主测试；保留旧审计失败，重新审计同一已封存产品证据通过。

## 分发描述与声明顺序

Structlog原生兼容接口读取Summary／Author-email和首个Project-URL。按冻结pyproject提供严格白名单单行描述字段，并保留其链接声明顺序；不按字母排序而改变__uri__。其实际原生构建版本0.1.dev1的已有元数据可追溯，源码实现仍只来自候选。标准PathDistribution读取器、头注入及清理检查通过；原生949项928通过／21skip。Flask沿原声明绑定私有命令与3.2.0.dev0元数据，494项通过。cattrs完整集合297.67秒，以600秒回归、512MB／64PID运行，不缩减Hypothesis或节点。

## 模拟控制容器的验证器版本一致性

第八小批首次Dynaconf业务受阻为离线准备异常。已只读提取实际控制镜像project_verifier.py，其_NATIVE_EXECUTE缺少第一阶段ada3ff90已提交的--no-compile；当前独立业务六条均在256MB通过，因此不能为旧准备代码的差异增加本仓资源。模拟入口增加显式可选的已提交验证器覆盖：必须逐字节等于当前HEAD原件，记录commit／模块SHA／准备程序SHA，并在控制容器实际导入后再核三者；只读挂载，不构建发布或部署。独立审计核运行前后的精确身份。保留failed-run-001和清理证明，同一内容／业务期望不改后重跑；先前已通过集合和冻结内容不改写。


## 完整源码的既有交付列表同步

第二阶段Dynaconf固定提交的76个公开Git测试夹具被通用.env规则过滤；最初82个路径中另6个是本就忽略的Python缓存。沿现有project-iterations集成交付合同同步manage.py的精确路径/SHA列表和Dockerfile.dockerignore的逐文件例外，不增加通配放行。逐文件SHA与原始Git blob核对见dynaconf-public-fixture-delivery.json。修改字节、符号链接和相邻未知.env继续拒绝；实际Git与Docker完整交付须重跑通过后才更新正式准入收据。首轮delivery-attempt-008失败保留。

完整三十仓来源扫描另识别Flask的一个公开.env测试原件，精确Git/SHA见remaining-public-fixture-delivery.json，同步既有双列表。snapshot忽略函数对空排除集直接返回，并在有排除时只解析一次当前目录，保持同路径/字节/链接校验语义，避免每个普通目录重复解析所有白名单路径。delivery-attempt-010原始失败保留，全部二十仓交付将重跑。


## 最后三十仓的完整原生对账补充

- sqlparse原生非strict XPASS按唯一原始ID `tests/test_regressions.py::test_issue484_comments_and_newlines` 保留，主合同仍逐节点固定结果。未列明、新增、丢失或换身份均拒绝；实际错误候选覆盖同数量但不同XPASS身份，适配器共39项测试通过。
- Dateutil的pytest-cov插件只登记上游已有no_cover标记，保留warnings-as-errors与完整tests/docs集合；PYTHONTZPATH及libc TZDIR读取同一离线tzdata2026.5，TZ为America/New_York。当前4861通过、264普通skip和17xfail逐项冻结。
- Packaging完整默认63338项在逐阶段报告下，需要1024MiB／600秒回归预算；150秒超时和768MiB收尾OOM原件保留，最终81.483289秒完整通过。业务仍256MiB／30秒，不动上游434项opt-in排除或跳过标记。
- ftfy增加一项完整配置转交修复，原版失败／参考通过／单开关错误候选拒绝及公开5测试、完整368主项22doctest均实跑。库原版seed字节不变，参考只改变授权两文件。

当前三十仓共134场景／192独立任务：68理解、59咨询、29方案、28诊断、8修改。每仓准入记录已完成原生部分，产品链及最终完整交付另记。任务稳定ID按项目/场景合同作用域核对，不将跨项目同名task_key误当冲突；数据库任务ID与task_key分离。


## Git原生属性的行尾兼容

Werkzeug根.gitattributes声明`* text=auto`，覆盖外层-text，core.autocrlf=true导出发生LF转CRLF，delivery-attempt-012原始失败保留。仓库内容范围增加`eol=lf`，使被上游重新标记为文本的LF源码仍按LF导出；-text文件继续原字节保留。当前Werkzeug含CRLF的文件均含NUL；上游还为tests/res/test.txt、HTTP与PNG显式标记binary，原件继续按字节保留。上游.gitattributes与所有seed文件不改，完整目录Git／Docker将重跑；不是归一化旧源码字节或更换固定提交。

Dateutil上游另外显式声明NEWS和*.bat为CRLF，外层属性无法覆盖。delivery-attempt-014准确捕获NEWS与docs/make.bat两份文件的导出差异，原始失败保留。实际官方CI调用manage.py build，因此在该入口的临时源码副本内增加精确恢复：只接受这两份固定原件的SHA或整份Git CRLF转换后SHA，全部预检成功后恢复原始Git blob的LF字节；未知修改、文件／父目录链接拒绝，执行位不变，不改工作区或上游属性。Git验证沿真实checkout-index后调用同一生产恢复函数，并分别披露raw_checkout_bytes_equal与production_source_restoration，不能声称未经恢复的检出字节相同。随后实际Docker COPY验证恢复后的完整交付树。30项部署测试覆盖合法恢复、重复调用、执行位、未知修改拒绝、预检不部分写入和父链接拒绝；普通直接Git检出可能呈上游CRLF，正式构建快照使用恢复后的固定blob字节。
