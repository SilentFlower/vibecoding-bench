# sqlparse：真实 GitHub 项目研究

研究完成：已核对官方来源/许可、固定源码、实际完整原生测试与业务场景，形成[20项独立工程交付和验收边界](./sqlparse-roadmap-20.md)。**完整基线506通过、1 XPASS、2个上游预期失败；不声称509全通过。仅研究，未实施路线或接入正式库。**

## 来源、许可、源码

官方仓库[andialbrecht/sqlparse](https://github.com/andialbrecht/sqlparse)，固定完整提交[`60cdc649726bf1bc4f1b336050560b336da715ec`](https://github.com/andialbrecht/sqlparse/tree/60cdc649726bf1bc4f1b336050560b336da715ec)，版本0.6.1.dev0。repository.json、commit.json、revision.txt与实际detached checkout一致。已读取LICENSE：BSD-3-Clause，保留Andi Albrecht/贡献者版权、再分发条件与免责声明，不以作者姓名背书。

真实工程跟踪**93文件、629,688字节**，41个Python文件共**8,798行**，包括测试和工具。已读顶层parse/format/split/parsestream、Lexer词法链与单例、FilterStack、StatementSplitter状态机、Token/TokenList/Identifier/Statement定义、各相关分组与缩进/输出/空白过滤器、CLI文件处理与相关原生测试。未改写真实工程，所有路线模块与回归测试路径均在固定提交实际存在。

## 安装和适用原生基线

证据和环境根`.deploy/github-100-research/resume-app/sqlparse/`，独立source/venv/isolated-home。Python**3.12.3**、Linux x86_64，运行库本身无第三方运行依赖；本轮安装本地editable源码与pytest**9.1.1**，冻结记录包含其iniconfig/pluggy/packaging/Pygments依赖。安装**9.615秒**，环境**50,141,769字节**。

完整上游`tests`目录：**506通过、1 XPASS、0普通失败、0错误、2个pytest.xfail、0普通跳过**；耗时**3.886秒**，峰值RSS**50,228KiB**。另有1个上游非严格xfail标记实际XPASS：`tests/test_regressions.py::test_issue484_comments_and_newlines`，覆盖普通CREATE TABLE的行尾注释移除及换行保留。该能力当前已通过，不列入20步修复；本轮DDL新排版与查询指纹分别有独立目标，并不重复认领该既有能力。JUnit把XPASS归普通通过，共507个JUnit通过；报告按pytest摘要单列506普通通过和1 XPASS。两个xfail均上游`Needs fixing`：`test_python_multiple_statements_with_formatting`和`test_format_right_margin`。本轮未改测试标记或过滤失败；原版反例分别收入步骤04/03，未来应真实修复，不能靠保留xfail声称增强已验收。未跑其他Python/OS、文档、lint/静态类型检查。

无需数据库、服务、账号或云凭据；所有SQL只作为本地文本，不执行SQL。业务脚本通过原生parse识别两个商品报表SELECT，原生format与CLI完成关键字大写和重排；本地文件效果只在脚本自己的TemporaryDirectory中验证。

## 实际发现和路线边界

`observations-result.json.module`指向本轮固定`resume-app/sqlparse/source/sqlparse/__init__.py`，20项原版观察一一保存。原生CLI非法indent_width会在报错前把in-place目标清空；布尔文字False被argparse的bool解释成True；right_margin直接NotImplementedError；两语句Python输出无法通过ast.parse；READ WRITE事务被合成一条；OFFSET/FETCH的ONLY落单；函数隐式别名导致缩进累加；成对反斜线字符串边界产生错误token；未完成括号格式化泄漏IndexError。以上9项均有原版运行记录，不根据issue文字直接下结论。

DDL专用排版、REFRESH识别、独立Lexer、源位置、显式匹配大小写、查询指纹、CLI检查/diff、文件换行保留、多段标识符与增量输入、严格选项共11项标成增强。已有get_token_at_offset、quoted Identifier、关键字大小写不敏感匹配、parsestream输出生成器、BOM保留和自定义Lexer本身均保留为已有能力。特别是官方#795的关键字大小写描述与实测不符，路线只提议对Name等类型开放明确策略；#798已在当前grouping有处理，不拿它当未修复缺陷。指纹只用于本地统计分组，不宣称能替代数据库参数化或语义等价证明。

二十项都定义了交付、影响模块、兼容、正常/边界验收、原生回归与真实依赖，不拆测试/文档/重试凑数，不强造步骤依赖。尚未实施、未跑提案冻结验收或平台原生适配。

## 原始证据与重跑

证据根`.deploy/github-100-research/resume-app/sqlparse/`：官方元数据与issues.json/ordinary-open-issues.json、固定revision、安装日志和冻结依赖、baseline-result.json/log/xml/time、observe.py、observations-result.json/log、roadmap-20.json、review-result.json及evidence-sha256.json。原始issue仅作为线索，实际报告选择普通业务方向并逐条核实；未向上游发消息。

项目根可重跑普通业务证据：

```bash
HOME="$PWD/.deploy/github-100-research/resume-app/sqlparse/isolated-home" PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-app/sqlparse/venv/bin/python .deploy/github-100-research/resume-app/sqlparse/observe.py
```

完整基线在source目录设置相同隔离HOME，运行独立venv的`python -m pytest -q -ra -p no:cacheprovider --junitxml=<证据目录>/baseline-tests.xml tests`。异机clone官方URL并detached checkout上述commit，按requirements-frozen.txt重建依赖，把editable项替换为本地固定检出，确认导入路径后执行。首次安装需要依赖源，未来冻结验收需准备离线依赖；本机venv和日志位置不是跨机器可用性保证。

上游工作树干净，未改正式库、产品代码、真实数据库或生产数据；未提交、推送、部署或实施路线。
