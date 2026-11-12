# 真实项目审查：Babel

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[python-babel/babel](https://github.com/python-babel/babel)；官方网站／项目元数据与 GitHub commit API 已交叉核对，原始内容见 repository.json、commit.json。
- 完整提交：[e2a17919f0eb988bfea2883b00793ca4d5d37c4f](https://github.com/python-babel/babel/tree/e2a17919f0eb988bfea2883b00793ca4d5d37c4f)。
- 许可证：BSD-3-Clause；CLDR 数据 Unicode-3.0。读取了项目 LICENSE 与 babel/locale-data/LICENSE.unicode；代码再分发保留 BSD 三条条件与免责，CLDR 数据同时保留 Unicode 版权和许可。CLDR 48.2 的 ZIP SHA512 与固定源码下载器的校验值一致。
- 用途：区域化日期、数字、单位、列表格式化与 gettext 翻译目录抽取、读写和更新。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 204／1234639 |
| 产品 Python 文件／行数 | 27／13832（babel/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512MiB 上限运行 |
| 安装 | 16.161 秒，venv 62661532 字节（含本轮测试依赖） |
| 原生基线 | 7,989 通过、0 失败、8 跳过、2 预期失败（JUnit skipped 合计10）；墙钟 21.673 秒，exit 0 |
| 测试峰值 RSS | 316332 KiB（容器测试进程观测） |

无外部服务和凭据需求。代码跟踪体积不包含构建所得 CLDR 数据；额外离线数据为1,123个dat、32,142,939字节，下载ZIP35MiB（36,044,097字节），首次导入独立耗时未取得，不能只用代码体积描述成本。cldr-data-evidence.json 保存固定48.2数据源、ZIP校验及每个dat摘要；上游下载脚本/import_cldr 属依赖准备，不是路线实现。测试峰值约309MiB，512MiB预算内完成。

原生终端另有1条pytest参数生成器弃用警告，保留在baseline-tests.log。运行完整 tests 和 babel 模块 doctest；8 个普通跳过为可选性能基准插件未装、Windows专用、已弃用 lgettext 和两个显式 +SKIP doctest；2 个日期格式预期失败按上游标记保留。首次只读目录运行有20个CLI写入失败，日志保存在 readonly-first-*；修正取证夹具为将同一固定源码拷贝到 /tmp/working 后完整重跑，不删测试、不修改产品源码。原生 pytest 参数：tests babel --doctest-modules。未验证多Python版本、性能基准、覆盖率门槛或发行构建。

## 源码与真实场景

读取 dates 的 parse_date、parse_time 与 skeleton 匹配，numbers 的单值格式化和 parse_decimal，units 的单位解析与列表拼接，core 的 negotiate_locale，以及 gettext Catalog.update/check 和抽取的 tuple 合同。dates.py 中月份名和时区 TODO 是未提供能力；numbering_system 已文档说明是符号系统，因此数字字形只列显式增强。Catalog 已有冲突信息和校验，路线不重复创建这些已有能力，而聚焦预览、精确来源、稳定交换和语义比较。所有 20 项均为本地增强提案，未宣称上游承诺或已实现。

离线实跑德文 EUR 金额、中文日期、英文长度单位、中文列表，并创建真实 Catalog，经 write_po/read_po 和 write_mo/read_mo 保留 Hallo %(name)s 翻译，Catalog.check 无错误。observe.py 还记录文本月份、带小数/偏移时间、区域数字字形以及20项目标入口观察；部分接口已存在时明确说明要扩展哪个参数边界。加载路径确认为 /source/babel/__init__.py。

完整 [20 步路线](./babel-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/babel/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/babel/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/python-babel/babel.git <checkout>
git -C <checkout> checkout --detach e2a17919f0eb988bfea2883b00793ca4d5d37c4f
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

安装后先用固定 scripts/download_import_cldr.py 下载并核验 CLDR48.2 后生成数据；离线验收应预备并冻结 cldr-data-evidence.json 中的dat。重跑命令：`<含docker SDK的Python> <evidence>/run_babel_baseline.py`；其调用本目录 run_native.py 的 baseline 函数，参数 tests、babel、--doctest-modules，内存512m；该专用脚本在容器tmp复制源码，通用脚本直接只读挂载不适合原生CLI写入测试。run_python_probe.py 用于业务观察。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

本研究只处理普通文本／文档功能。未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
