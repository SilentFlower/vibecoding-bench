# 真实项目审查：simplejson

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[simplejson/simplejson](https://github.com/simplejson/simplejson)。独立维护的JSON编解码器，具备可选C加速、Decimal精度、自定义对象/数组hook与文件格式化CLI。
- 固定提交：[9950b7e5f4443fff8defb51e80e41ab40d0a36b9](https://github.com/simplejson/simplejson/tree/9950b7e5f4443fff8defb51e80e41ab40d0a36b9)；版本与运行要求：4.2.0；Python2.7或>=3.9（本轮Python3.12）。
- 许可证：MIT OR AFL-2.1（实际LICENSE.txt明确双许可，可选择MIT）。保留Bob Ippolito版权与完整许可文件；不要误把双许可写成必须同时履行两份。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 63 个，575,722 字节 |
| Python 产品源码 | 9 个文件、2,193 行 |
| Python 测试文件 | 36 个、4,485 行 |
| 隔离依赖安装 | 7.155 秒，venv 62,338,899 字节 |
| 适用原生基线 | 486 通过、0 失败、0 错误、76 跳过 |
| 基线进程 | 1.709 秒，峰值子进程 RSS 41128 KiB |
| 容器运行 | 整体 2.039 秒，内存 256 MiB、PID 64，无 OOM |

运行核心无第三方依赖；可选_speedups由本机隔离venv构建并只读挂载。测试额外准备unittest-xml-reporting输出XML（其依赖lxml）及通用pytest；未把XML报告工具当运行依赖。产品还包含实际C源码_speedups.c与_speedups_scan.h，Python行数表不能代表全部实现成本；文件规模详见size.json。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

dump/dumps封装JSONEncoder，load/loads封装JSONDecoder；encoder支持Decimal、namedtuple、default/for_json、iterable_as_array，Python与C两套实现可切换；scanner将数字/容器/字符串交给decoder，新增array_hook已存在。原生all_tests_suite会先跑C可用集合，再NoExtensionTestSuite切纯Python，包含模块与index.rst doctest；本轮直接调用该上游套件，没有替换测试发现逻辑。已读相关入口、encoder/decoder/scanner、RawJSON/tool及C扩展构建/测试契约。

发票含9007199254740993整数与123.4500 Decimal，写JSON并精确读回；真实simplejson.tool格式化后数值保持，生成器数组与HTML安全编码作为已支持对照。合成文件复现tool坏输入清空既有输出和同路径截断，统一为一个根因问题；重复输入键、编码键碰撞、未验证RawJSON、UTF16默认解码作为增强观察。

## 基线范围与限制

原生all_tests_suite(project_dir=/tmp/source)共562个报告项，486通过、76跳过、0失败/错误，包含C与纯Python两轮及index.rst doctest；C扩展存在由前置断言验证。76跳过为30 debug引用计数、18纯Python轮C专属、13需Python3.13+ heap类型、6需Python3.15内建frozendict、5需_interpreters、4 Python2 long子类用例；均为上游条件跳过。

初跑从/tmp/source导入时容器tmpfs不允许动态库执行映射，误判扩展缺失；保存tmpfs-noexec与extension-probe证据，最终仅把sys.path优先设为同固定提交的/source只读挂载，不改变容器执行权限/账号隔离。由此同时覆盖C与纯Python。未验证debug、Python2/3.13+、free-threaded多解释器构建或所有平台；未跑打包矩阵和性能基准。许可证/当前工具问题已经实测，其余为增强不是20个BUG。

## 迭代路线

[20 步路线](./simplejson-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

1项当前文件破坏问题修复+19增强，涉及JSON语义政策、受预算约束的流读写、显式扩展与CLI。已有JSONL手工示例、array_hook、Decimal、iterable_as_array、RawJSON、HTML encoder和错误注释不重复计为新能力。JCS为可选严格模式，来源RFC8785，不将sort_keys直接称规范化；每步C/纯Python一致性是验收维度，不能再各算一步。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/simplejson/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/simplejson/simplejson.git <checkout>
git -C <checkout> checkout --detach 9950b7e5f4443fff8defb51e80e41ab40d0a36b9
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 /smoke.py --baseline
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run simplejson -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/simplejson/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。simplejson/smoke.py在导入前优先sys.path=/source，确保同提交C扩展从只读绑定路径加载；普通动态库不能从/tmp noexec映射。安装依赖准备要能编译该扩展。baseline命令调用原生套件并由xmlrunner记录XML；smoke脚本须一起复制。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
