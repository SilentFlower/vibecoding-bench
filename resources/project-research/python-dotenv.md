# 真实项目审查 03：python-dotenv

研究日期：2026-10-21。结论：适合轻量配置工具的工程迭代研究；来源、原生基线和 [20 步路线](./python-dotenv-roadmap-20.md) 已核对。尚未实现路线、制作冻结验收或接入正式项目库。

## 来源与工程规模

- 官方仓库：[theskumar/python-dotenv](https://github.com/theskumar/python-dotenv)。读取、插值和编辑 .env，提供 Python API、可选 CLI 和 IPython 扩展。
- 固定提交：[0b2880591780a426b0551436f47a17e7a76d954f](https://github.com/theskumar/python-dotenv/tree/0b2880591780a426b0551436f47a17e7a76d954f)，版本 1.2.4，Python ≥ 3.10。研究时 main 位于该提交，已 detached 检出。
- BSD-3-Clause；保留 LICENSE、版权和归属声明。官方仓库未归档，本轮元数据 pushed_at 为 2026-10-01。
- 固定工作树 47 个受跟踪文件、191,350 字节；8 个 Python 产品模块合计 1,173 行，tests 中 Python 文件合计 2,656 行。不是重建的玩具 app.py。

| 模块 | 职责 | 行数 |
| --- | --- | --- |
| src/dotenv/main.py | DotEnv、查找、加载、变量解析和文件原子替换 | 532 |
| src/dotenv/cli.py | list/get/set/unset/run 等 CLI 行为 | 256 |
| src/dotenv/parser.py | 引号、转义、多行、注释和带位置的 Binding | 191 |
| src/dotenv/variables.py | 插值 Atom／Literal／Variable | 86 |
| src/dotenv/__init__.py | 公开 API、get_cli_string | 51 |
| src/dotenv/ipython.py | IPython 魔法命令 | 50 |
| __main__.py、version.py | CLI 入口及包版本 | 7 |

## 运行成本与原生基线

核心无外部运行依赖，CLI extra 需要 click。没有外部服务、云密钥或前端构建。本轮 Python 3.12.3，独立 venv 安装本地源码的 cli extra、pytest 和用于覆盖原生测试的 IPython；安装 28.324 秒，包含网络下载，不能当作纯执行时间。

环境占用 83,548,425 字节，约 83.5 MB，包括 pip、pytest、IPython 和依赖；IPython 是本轮测试依赖，不是核心解析／CLI 的必需依赖。实际固定依赖见 test-requirements.txt 和 installation.json；没有安装完整构建、发布、ruff、mypy 和文档工具链，也未运行多 Python 版本矩阵。

第一次在宿主检出目录执行完整测试得到 **280 通过、4 失败、4 跳过、31 警告**。4 个失败的断言均受到上层工作区存在 .env 的影响，`find_dotenv()` 查找到祖先文件；4 个权限测试因为宿主 root 身份按上游规则跳过。这个结果保留于 baseline-tests.log／xml 和 baseline-result.json，不计作未解决的源码缺陷。

随后用正式账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1` 完整重跑：**288 通过、0 失败、0 错误、0 跳过，35 警告**。pytest 2.973 秒，容器整体 3.906 秒。UID/GID 1000、无网络、只读根、capabilities 全删除、禁止提权、256 MiB RAM／无额外 swap、PID 64；源码和预备依赖只读挂载，未挂载宿主父目录的 .env、账号 HOME 或凭据，无 OOM。

原生测试会直接调用 `dotenv` 可执行名；本轮在证据目录 cli-bin 中预备只读入口，指向镜像 Python 和实际候选包的 cli，验证期间通过 PATH 使用。第一次入口准备在不可执行 tmpfs 导致 CLI 测试失败，修正只读入口挂载后全套通过；准备失败日志另存，没有把它算作产品 BUG。临时容器均已删除，成功轮额外核对不存在。

35 条警告来自 Click isolated_filesystem 弃用及 IPython 在只读 HOME 下选择临时目录，保留原文日志。没有通过修改上游测试、忽略失败用例或更改父工作区 .env 来取得基线通过。

## 实际使用与改进证据

真实 CLI 场景在临时文件上执行 set/get/unset：写入 `GREETING=你好 synthetic`，CLI 读回与 Python API 一致；删除后文件解析为空，三个命令退出码均为 0，临时目录清理。所有配置均为合成数据，没有读取业务凭据作为测试输入。

本轮 reproduce.py 保存 22 条观察，覆盖 20 项路线：4 个原版问题、16 个增强方向，其中 2 条是通过对照。

1. [#715](https://github.com/theskumar/python-dotenv/issues/715)：`${B:-default}` 在 B 为空字符串时返回空值；缺失 B 与非空 B 的对照正常。改动需要明确旧空值行为的兼容影响。
2. get_cli_string：带空格的路径被拆成多个参数，带引号的值失真。只以 shlex.split 核对参数往返，没有交给 shell 执行。
3. set_key 对非目标行的 CRLF 和多行内容全部转换为 LF；通过编辑前后的实际字节验证。
4. set_key 接受含换行的键，修改文件后原键无法读回；没有在写入前拒绝不可表示的键。

增强包括持久写入、严格解析、重复键策略、序列化、示例模板、临时环境上下文、多文件合并、有界查找、选择性字面量插值、自定义合并、来源诊断、初始配置、Windows 百分号变量、递归插值、字面文件引入和陈旧编辑冲突检测。上游 issue 与源码位置、目标及回归分别写入路线。

已排除的旧问题：源码已有 follow_symlinks，已有 Unix FIFO 支持，已有反斜杠和单引号的 dotenv 内部往返修复，已有 BOM 处理；这些不能再次算成新的迭代。Bash 相邻引号语法、默认查找的线程栈问题、加密／Web 管理界面等本轮不纳入，避免把定位扩展成 shell 或独立服务。

## 原生接入边界与重跑

产品没有 app.py JSON 行入口。现有 ProjectVerifier 不支持这个真实包／CLI 的原生验收；288 项通过只证明当前镜像在预备依赖后可隔离运行它。后续须由控制端持有冻结用例，核对导入路径、环境映射、CLI 参数、文件字节和失败边界，保留源码、CLI 和上游测试结构。

证据根：`.deploy/real-project-review-20261021/python-dotenv-review/`。重跑时 clone 官方仓库，checkout 上述完整 commit，建立独立 venv，再安装冻结 test-requirements.txt 和该检出源码的 cli extra。避免在含真实祖先 .env 的目录直接运行自动发现测试；本轮完整通过证据来自无这些父目录挂载的容器。

```bash
git clone https://github.com/theskumar/python-dotenv.git <checkout>
git -C <checkout> checkout --detach 0b2880591780a426b0551436f47a17e7a76d954f
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>[cli]'
```

在无祖先业务 .env 的隔离目录中运行 `python -m pytest -q -ra`。本轮容器脚本 container-baseline.py 保留只读依赖与 CLI 入口的挂载细节；其中使用当前账号镜像，但不包含账号数据或网络请求。

- repository.json、revision.txt、issues-page1.json、issues-page2.json：官方来源、提交与 issue 正文。
- size.json、installation.json、installation-result.json、requirements-frozen.txt、test-requirements.txt：运行和依赖成本。
- baseline-result.json、baseline-tests.log／xml：保留宿主环境造成的首轮失败和权限跳过。
- account-runtime-result.json、account-runtime-tests.log／xml、container-baseline.py：288 项全过的适用隔离基线。
- account-runtime-preparation-attempt-*：CLI 入口准备失败的单独证据，不冒充项目缺陷或最终通过。
- reproduce.py、reproductions-result.json：原版实际行为和 CLI 文件副作用；没有模拟断电。
- roadmap-20.json、evidence-sha256.json、review-result.json：结构化研究路线、摘要和完成检查。

本轮未修改上游源码、正式项目库、产品实现或生产数据。未创建 task、提交、推送、部署或给上游发消息，模型测试与生产请求均为 0。
