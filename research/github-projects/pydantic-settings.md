# Pydantic Settings：真实 GitHub 项目研究

官方来源、许可、恢复的固定源码、已通过原生基线及全新的本地业务观察已核对，形成[20步路线](./pydantic-settings-roadmap-20.md)。**仅研究，未实施路线，未冻结新增验收，未接入正式库。**

## 来源、许可与恢复

官方 [pydantic/pydantic-settings](https://github.com/pydantic/pydantic-settings)，完整commit `8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930`，包版本2.16.1。主[LICENSE](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/LICENSE)为MIT，保留Samuel Colvin及贡献者版权。旧cli-config证据的临时检出已不存在，本轮重新clone官方仓库并detached checkout同commit；原revision、原editable安装URL、原测试cwd和全部log/JUnit仍保留。恢复关系及原文件SHA见baseline-reuse.json。

本轮真实读取SettingsConfigDict/BaseSettings的来源创建、合并、字段名还原、缓存、debug及CliApp序列化入口；核对env复杂值/字典分段、CLI serializer/unknown层级及pyproject路径、JSON/YAML/TOML构造器和真实tests。源码58跟踪文件、1361728字节，37个Python文件/23488行；复用独立venv实际225871030字节。未改旧venv，观察通过sys.path先导入恢复源码，结果记录真实module路径。

## 实际原生基线与本地业务

复用原固定commit的上游默认tests完整集合：**1256主项通过、5普通skip、0xfail、0xpass，退出0**；14.338秒，最大RSS348636KiB，宿主Python3.12.3独立venv。原当轮JUnit/log未改，不重复已成功的集合。5项skip逐例核对：1项Windows环境大小写平台条件、3项CLI metavar原生Skipped参数、1项PyYAML已装时跳过not-installed用例；不是失败或xfail。原命令、环境及冻结依赖在cli-config/pydantic-settings，全部SHA被本轮引用。

原安装记录及制品保留，复用成本见installation-result.json；观察仅使用Pydantic、dotenv、CLI和本地YAML/TOML，无外部服务。新的requirements-recovered.txt只将旧editable路径替换成恢复源码，作为异机重建说明，未冒称执行过第二次安装或原生基线。未来若要求容器测试，需另做对应环境证据，不能把本次宿主测试说成镜像结果。

临时.env中title=商品工具/quantity=2，环境quantity=5实际覆盖成功并转int；20项观察全部重新运行并封存observations-result.json。原环境通过patch还原、文件自动清理，cache结尾清理，async负例协程显式关闭。未接入真实账号、远程配置或业务数据。

## 路线真实性

7修复均在恢复源码实际复现：dict Union解码、CLI prefix+alias、frozenset/deque往返、~显式路径、UnknownArgs层级、TypeAliasType子字段、nested fields_set。其余13为增强。旧issue923的跨来源别名合并样例本次已正确得到env-a/file-b，明确排除修复；该步改提可选的来源列表合并，默认replace不叫BUG。

已排除cache/clear_cache、source debug日志、文件源构造路径覆盖、strict转换、CLI help/serializer/自定义parser和JSON Schema等既有能力。PlainSerializer与CLI业务值表示不同不直接叫BUG，提成对CLI codec；缓存刷新不承诺改变旧引用。每条含正常/边界验收、真实模块、原生回归与实际依赖；20条均未实施，控制端冻结尚未开始。

## 证据与重跑

本轮证据根.deploy/github-100-research/resume-app/pydantic-settings含恢复检出、revision/clone、基线复用SHA、官方元数据和issue、20观察/20步JSON、review及摘要；原生原文件保留在cli-config根。项目根可重跑本地业务：

```bash
PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/cli-config/pydantic-settings/venv/bin/python .deploy/github-100-research/resume-app/pydantic-settings/observe.py
```

异机从官方URL检出同commit，按requirements-recovered.txt重建venv（调整editable路径）并核对真实导入；原基线的/tmp路径不再可用，不能原样照搬。若未来重新跑原生，先归档旧日志/XML/result并生成全新JUnit，失败不误读旧证据。未来冻结还需离线制品准备。tracked源码干净，未改正式库、实施路线、提交推送部署或向上游发消息。
