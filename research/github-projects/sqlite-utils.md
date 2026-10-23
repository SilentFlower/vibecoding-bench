# 真实项目审查 01：sqlite-utils

审查日期：2026-10-21。结论：适合作为首个真实工程试点，运行成本较低、功能与测试完整，存在可独立复现和验收的实际问题；当前尚未接入生产项目库。

## 来源与冻结版本

- 仓库：[simonw/sqlite-utils](https://github.com/simonw/sqlite-utils)。这是操作 SQLite 的 Python 库和命令行工具，包含数据导入、SQL 查询、全文搜索、表结构变换、迁移和插件能力。
- 固定提交：[9c66bafa52ae23d40499c74b0db3b635bcddb876](https://github.com/simonw/sqlite-utils/tree/9c66bafa52ae23d40499c74b0db3b635bcddb876)，包版本 4.2.1；本轮查询的上游 main 与此前研究的提交相同。
- 上游声明许可证为 Apache-2.0；后续内容快照应保留原 LICENSE、来源及提交记录。
- 旧研究位于 `/tmp`，本轮开始时已不存在。本次重新检出在 `.deploy/real-project-review-20261021/sqlite-utils/`，原始日志、复现和结果保存在其父目录。研究未修改上游源码、当前产品实现或线上数据，也未创建 Trellis task。

## 工程规模与运行成本

以下为实际检出和执行结果，不使用 GitHub 展示的仓库大小代替工作树测量。

| 项目 | 实测或源码事实 |
| --- | --- |
| 受版本控制的文件 | 107 个，合计 1,450,898 字节，约 1.38 MiB |
| Python 源码 | 11,252 行，10 个模块 |
| Python 测试 | 54 个文件，16,585 行 |
| 运行要求 | Python ≥ 3.10；本轮宿主 Python 3.12.3、SQLite 3.45.1 |
| 必需运行依赖 | click、click-default-group、pluggy、python-dateutil、sqlite-fts4、tabulate、pip，具体范围以冻结提交的 pyproject.toml 为准 |
| 服务依赖 | 本轮库与 CLI 场景只使用本地 SQLite，无独立数据库进程、云密钥或前端构建 |
| 安装 | 单独虚拟环境安装上游项目、pytest、hypothesis，用时 19.0 秒；网络和缓存会影响这一数值 |
| 环境磁盘 | 上述虚拟环境约 34.4 MB，不含项目源码；未安装上游完整 dev/docs 工具链 |
| CLI 行为验证 | 实际从 CSV 导入临时数据库，再以 SQL 查询，两次 CLI 调用合计约 0.313 秒 |

运行负担较轻，代码复杂度属于中等。它适合练习真实库和 CLI 的维护；如果后续要覆盖可视化网页应用，应另外逐仓选择对应项目，不能把这个项目包装成所有业务领域的替身。

## 原生结构与数据路径

| 模块 | 职责 | 行数 |
| --- | --- | --- |
| sqlite_utils/db.py | Database/Table、类型与结构变换、批量写入、全文索引、转换函数 | 5,547 |
| sqlite_utils/cli.py | Click 命令、导入导出、内存查询及用户错误反馈 | 3,813 |
| sqlite_utils/create_table_parser.py | SQLite 建表结构解析 | 897 |
| sqlite_utils/utils.py | 文件格式识别、行读取、类型推断等 | 666 |
| sqlite_utils/migrations.py | 迁移登记、应用状态与事务 | 184 |
| sqlite_utils/plugins.py、hookspecs.py | pluggy 插件装载与钩子 | 52 |

典型导入路径为 CLI → 文件读取与类型识别 → Database/Table → SQLite。Python 用户也可直接调用 Database/Table。验收必须保留这些入口和真实数据库副作用。

## 已执行的基线

原始结果：`.deploy/real-project-review-20261021/baseline-{result.json,tests.xml,tests.log}`。

执行上游整个 pytest 测试集合：**1,497 通过、16 跳过、0 失败、0 错误**，pytest 报告 24.36 秒，进程墙钟 25.01 秒。宿主测得子进程峰值 RSS 为 291,700 KiB，约 285 MiB。33 条警告均保留在日志中，本轮没有运行全套格式、类型和文档检查。

跳过项由上游原有条件决定：

- 3 项需要编译 tests/ext.c；本机缺 sqlite3ext.h，编译未成功，没有安装全局系统包。
- 1 项需要 pandas/numpy，本轮没有安装。
- 12 项需要 SpatiaLite 扩展，本机不可用。

另用当前正式 V3 account 镜像 `v3-ci-39482854683-1` 执行相关原生测试：

```text
python -m pytest -q -ra -p no:cacheprovider \
  tests/test_fts.py tests/test_convert.py tests/test_register_function.py
```

**75 项通过，pytest 用时 1.15 秒**。容器使用 UID/GID 1000、无网络、只读根、删除全部 capabilities、禁止提权、256 MiB RAM、PID 上限 64；源码和本轮已安装的 Python 依赖只读挂载，未挂载任何账号 HOME 或凭据。没有 OOM，临时容器已删除。

这一结果证明相关原生测试在准备好依赖后可于现有账号镜像隔离运行；不代表当前 ProjectVerifier 已支持它，也不代表整个上游测试集合已在 256 MiB 下通过。

## 可复现的真实改进

本轮在未改动的冻结提交上执行了 15 个复现／对照组合。以下错误属于预期观察到的原版缺陷；未把它们记成修复后通过。

### 候选迭代一：全文索引支持一次性迭代器

来源：[上游 issue #902](https://github.com/simonw/sqlite-utils/issues/902)。

`Table.enable_fts()` 的 columns 声明接受 Iterable。传列表时成功；把同样的列改成一次性迭代器，创建索引后填充索引时报 SQL 语法错误。源码在构造建表 SQL、populate_fts 和触发器时多次遍历同一个对象，第一次遍历后迭代器已经耗尽。

实际覆盖 FTS4/FTS5 × 创建／不创建触发器：4 个列表对照均成功，4 个迭代器场景均复现错误，且失败后仍存在 notes_fts 表。

该迭代的目标是让等价列表、元组和一次性迭代器产生一致的索引与查询行为。验收应检查初始命中、触发器下的新增／更新／删除，以及已有列表输入不回归。冻结验收从真实 SQLite 查询结果判断，不能只检查函数返回或模型声明。

### 候选迭代二：连续转换使用本次传入的函数

来源：[上游 issue #910](https://github.com/simonw/sqlite-utils/issues/910)。

先把州缩写转换成全称，再用另一映射把国家缩写转换成全称；当两个转换的注册名称相同，第二次调用会运行旧转换，country 被写成 NULL。

实际复现 4 种可调用形式：dict.get、functools.partial、可调用实例、同名普通函数。四者均产生错误结果；不同 lambda 的对照成功。源码中 convert 按函数名注册，而 register_function 对已有同名、同参数数量的函数保留旧注册，形成了可解释的因果链。

该迭代应隔离每次转换的回调。验收需要同时核对两列结果、跨表连续转换、同名和不同名函数、已有 lambda 行为，并保留 register_function 的公开 replace 语义；不能为修复 convert 而全局改变所有函数注册行为。

### 暂不纳入首批：批量推断类型导致前导零丢失

来源：[上游 issue #885](https://github.com/simonw/sqlite-utils/issues/885)。

前 200 行为整数、最后一行是字符串 `007` 时，实际读回整数 7；明确指定 TEXT 后读回 `007`。这个现象已复现，但涉及 SQLite 类型亲和性及上游按首批数据推断类型的既有规则。默认改成告警、严格拒绝还是要求显式列类型，需要先收敛行为，不能直接当作已经定好的修复规格。

首轮核实了上述两项有明确失败证据与验收方向的迭代。用户提出需要二十步后，进一步研究已形成 [二十步真实工程路线](./sqlite-utils-roadmap-20.md)：9 步问题修复、11 步功能增强，每步均有上游来源、边界和验收目标。两项初始修复仍是路线前两步；上面的前导零策略继续暂缓。

## 接入现有平台前的实际缺口

检查依据为当前父仓提交 b575871 的 `orchestrator/project_library.py` 和 `orchestrator/project_verifier.py`。

| 当前约束 | 对真实项目的影响 | 后续适配方向 |
| --- | --- | --- |
| ProjectLibrary 默认至少 100 项，每项至少 20 步 | 一个真实试点和两项有效改进无法按默认配置进入库 | 数量按实际内容定义，允许少量项目和不同路线长度 |
| entrypoint 必须等于 python3 app.py | 不能表达 sqlite-utils 的真实包与 CLI 入口 | 表达原生项目类型、启动及依赖元数据 |
| ProjectVerifier 固定运行 app.py、输入输出逐行 JSON | 原生 pytest、SQL 副作用和 CLI 断言无法直接执行 | 增加受控原生测试适配，保留无网络、隔离和冻结候选 |
| 当前内容只复制 seed，默认依赖镜像现有库 | 不能保证项目依赖已具备 | 按固定版本预备依赖，验收期间离线使用，不把虚拟环境装入源码快照 |
| 验收默认 30 秒、256 MiB | 本轮完整宿主测试约 25 秒、峰值约 285 MiB，余量不足 | 单步使用冻结的相关回归；完整基线另给明确预算，不能宣称原限制下已通过 |
| 当前目录记录题号而无上游仓库提交契约 | 无法完整核对真实来源 | 保存仓库 URL、完整 commit、许可证、源码摘要和测试基线 |

原生验收还需由控制端持有固定用例，并核对实际加载的是本次候选源码；候选内的 tests 被删改不能直接使验收放行。现有实例冻结、原目录接续、独立验收、检查点和账号门禁可以继续复用。

本轮只完成研究和验证，未改这些约束，未用一个伪 app.py 入口宣称完成真实仓库接入。后续应让这个固定仓库进入原生项目试点，可以先用前两步取得真实修改与独立验收闭环，再按已研究的二十步路线累计推进。

## 可复核证据

- 检出：`.deploy/real-project-review-20261021/sqlite-utils/`，Git 工作树未修改。
- 研究清单：`.deploy/real-project-review-20261021/candidate.json`，明确标记 research_only=true、production_integration_ready=false。
- 来源快照：repository.json、revision.txt、issue-902.json、issue-910.json、issue-885.json。
- 依赖：test-requirements.txt、installation.json、installation-result.json。
- 完整上游测试：baseline-result.json、baseline-tests.xml、baseline-tests.log。
- 正式账号镜像离线测试：account-runtime-result.json、account-runtime-tests.log。
- 独立复现：reproduce.py、reproductions-result.json。
- 文件核对：evidence-sha256.json。
- 二十步扩展研究：sqlite-utils-roadmap-20.md、roadmap-20.json、roadmap-baseline-result.json、roadmap-evidence-sha256.json。candidate.json 和原始摘要保留首轮两项候选的证据；扩展路线另存，不将研究清单当作生产内容。

复查时必须先检出同一 commit，再在独立虚拟环境中安装该源码及固定的测试依赖。复现脚本目前按本次证据目录组织运行；其断言用于确认原版错误仍能复现，不是修复验收器。

本轮模型调用和生产请求均为 0，没有提交、推送或部署。
