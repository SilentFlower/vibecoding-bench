# PyPika：真实 GitHub 项目研究

研究完成：已核对官方来源许可、固定真实源码、完整原生基线和实际普通业务场景，形成[20项独立交付及验收边界](./pypika-roadmap-20.md)。**仅研究，未实施路线、未冻结独立验收、未接入正式库。**

## 来源、许可、真实工程

官方仓库[kayak/pypika](https://github.com/kayak/pypika)，固定完整提交[`465fb9ae12f7727d28785d087b64e6226da5714e`](https://github.com/kayak/pypika/tree/465fb9ae12f7727d28785d087b64e6226da5714e)，版本0.51.1。repository.json、commit.json、revision.txt与实际检出对应；完整读取LICENSE.txt为Apache-2.0，保留许可文本和源码归属通知，未来修改文件须明确标识；若分发包含NOTICE也需一并保留，不以项目商标作额外背书。

跟踪**97文件、658,552字节**，62个Python文件共**16,323行**，含测试工具。主要读取Query/QueryBuilder/CreateQueryBuilder、方言专用builder、Term/ValueWrapper/JSON/各criterion/Function/Interval、当前日期时间函数、builder复制装饰器及相关原生测试。查询对象动态__getattr__会构造Field，故所有拟议方法缺口都从类上查定义，未误用hasattr(query,name)作不存在证明。

## 原生基线与运行成本

证据根`.deploy/github-100-research/resume-app/pypika/`，独立source、venv与isolated-home。宿主Python**3.12.3**、Linux x86_64，本轮未在正式账号镜像运行。安装本地editable工程、pytest**9.1.1**及parameterized**0.9.0**耗时**17.797秒**；venv **50,342,137字节**。Python3.12下无第三方运行依赖，旧Python的typing_extensions条件依赖按上游声明保留。

完整原生`pypika/tests`：**1099主测试通过、90子测试通过、0失败、0错误、0跳过**，耗时**2.902秒**，测试进程峰值RSS**46,224KiB**。冻结依赖、安装日志与JUnit原始结果齐全。未运行其他Python/OS矩阵、文档、lint/类型检查；本次目录此前无基线，不存在旧JUnit复用。上游适用测试主要验证SQL生成，不要求真实数据库服务。

业务场景在标准库SQLite **3.45.1**的`:memory:`创建合成商品表、插入茶/咖啡，原生SQLLiteQuery构造数量筛选和排序，实际执行返回咖啡/4。另用SQLite真值对照证明组合条件判空缺括号会把结果1变0。连接仅在进程内临时内存中存在，无真实数据库、账号、凭据、监听服务或外部写入。

## 原版发现与二十项边界

observations-result.json.module指向本轮固定resume-app/pypika/source/pypika/__init__.py。9项原版修复反例为负微秒符号、EXISTS别名、跨方言索引提示、空PG语句残留后缀、外层join影响CTE内部冲突目标命名空间、DELETE遗漏WITH、函数丢参数收集上下文、组合判空优先级和当前日期/时间括号。CTE命名空间问题只在外层join触发，报告同时保留单独upsert正常结果，未把无法复现的简单样本当复现。

11项增强为JSON值连续组合、明确Python切片分页、NULL排序、共享锁子句、UNPIVOT、通配列排除、ClickHouse建表、条件链、只读metadata、别名去重映射和IS/IS NOT。已存在的datetime.time正确引用、派生表as_、pipe、fields_对子查询的故意隔离、is_joined、isnull和for_update均明确排除新增；不照抄旧issue宣称仍缺失。别名去重、分页新模式等可能改变用户预期，均设计opt-in与明确迁移边界。

其他数据库方言仅对照原版输出、源码和官方语法：PostgreSQL[SELECT](https://www.postgresql.org/docs/18/sql-select.html)、[INSERT](https://www.postgresql.org/docs/18/sql-insert.html)、[日期时间](https://www.postgresql.org/docs/18/functions-datetime.html)；Snowflake的SELECT/UNPIVOT与ClickHouse建表官方页见逐步来源；最初ClickHouse直接下载403已保留，随后通过官方现行页面核对ENGINE、ORDER BY与存储子句顺序，抓取方式及原始快照可用性记录在dialect-primary-sources.json。**未连接这些数据库，不声称服务器已接受/拒绝样本，也不声称实际锁效果已验证。**后续验收按每步真实依赖单独准备引擎，不影响本轮原生轻量基线。

## 证据与重跑

证据根包含官方repository/commit/issue元数据、完整revision、安装记录、requirements-frozen.txt、size.json、baseline-result.json与log/xml/time；observe.py、observations-result.json/log保存20个原版观察和SQLite效果；roadmap-20.json封存唯一步骤ID、来源、模块、回归、验收与依赖；dialect-primary-sources.json记录官方方言页面抓取结果；review-result.json/evidence-sha256.json为复核入口。

项目根重跑普通业务证据：

```bash
HOME="$PWD/.deploy/github-100-research/resume-app/pypika/isolated-home" PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-app/pypika/venv/bin/python .deploy/github-100-research/resume-app/pypika/observe.py
```

完整基线在source目录设置相同隔离HOME，运行独立venv的`python -m pytest -q -ra -p no:cacheprovider --junitxml=<证据目录>/baseline-tests.xml pypika/tests`。异机clone官方URL，detached checkout完整commit，依冻结依赖创建venv并把editable项替换为本地固定源码；先核对导入路径再运行。首次安装需依赖源，未来冻结验收前需准备离线wheelhouse。本机原始证据位置不是跨机器可用性保证。

上游git工作树干净。未改正式库或产品代码，未实施路线、提交、推送、部署或向上游发消息。
