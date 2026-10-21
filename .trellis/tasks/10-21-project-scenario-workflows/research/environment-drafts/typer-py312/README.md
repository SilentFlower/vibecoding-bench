# Research: Typer 目标镜像离线环境取证

- Query: 在指定账号镜像、无网络／UID1000／只读根下，以固定依赖运行完整既有 Typer 测试及原版／参考应用业务校准。
- Scope: internal
- Date: 2026-10-21

## Findings

### 固定输入与范围

- 镜像：`vibebench-v3-account:v3-project-repairs-local-20261021-e`，实际 ID `sha256:d055c5f0035c8fb3f204ed97d6f774a38afdb3515f5503f7fa028adb6a5e908d`。
- 真实运行 Python 为 3.12.15，Linux amd64／glibc 2.36；不是先前宿主 3.12.3 的结果。实际导入位置为 `/work/project/library/typer/__init__.py`，版本 0.27.3。
- 候选源码来自同任务 `content-drafts/typer/seed/library/`，固定上游 `a5882dedf0bc7a46cd861fdfca020f88519e0f21`；没有安装外部 Typer／Click 发行包替代候选。
- `downloads.json` 固定 16 个 wheel、2,616,375 字节。下载只使用历史 `installation.json` 的精确 URL、版本和 SHA256，全部摘要一致，没有查询最新版本。
- `profile/profile.json` 使用实际 `validate_environment` 格式；候选源码、离线环境和原始证据分别存放，制品不混入源码 seed。

### 依赖与运行条件

运行依赖及其闭包为 annotated-doc 0.0.5、rich 15.0.0、shellingham 1.5.4、markdown-it-py 4.2.0、mdurl 0.1.2、Pygments 2.21.0。

完整已用测试依赖为 pytest 9.1.1、pytest-cov 7.1.0、pytest-sugar 1.1.1、pytest-xdist 3.8.0、coverage 7.16.2、execnet 2.1.2、iniconfig 2.3.1、packaging 26.3、pluggy 1.7.0、termcolor 3.3.0。每个制品的文件名、URL、字节数和摘要见 `downloads.json`，安装使用 `--no-index --no-deps --find-links /environment/artifacts`。

容器约束为 UID/GID 1000、network none、只读根、cap_drop ALL、no-new-privileges、内存／swap 各 1,024 MiB、PID 128。仅挂载本任务只读内容／制品与专属证据目录；不挂账号 HOME、凭据或 Docker socket。`/work` 为 1 GiB tmpfs，显式 `exec,nosuid,nodev`；`/tmp` 为 128 MiB tmpfs。

验证器创建独立 venv，并以 `.pth` 指向同一份候选 `library/`。这是为了上游子进程测试主动替换 PYTHONPATH 后仍加载候选；不复制源码到另一份安装、不改上游、不伪造 dist-info。完整 pytest 在保留的真实 Bash 父进程下运行，使 shell 条件用例真实执行。

### 已记录的环境修正

1. `attempts/01-noexec/`：默认 noexec tmpfs 使 coverage 的 C tracer 无法映射，strict warnings 在测试收集前退出；保留原始命令和 stderr。修正仅为验证目录显式 exec，未禁用 coverage 或吞掉警告。
2. `attempts/02-source-registration/`：完整 1,505 项真实运行，1,477 通过、24 普通 skip、2 XFAIL、2 失败，耗时 176.885150 秒。失败是覆盖 PYTHONPATH 的脚本子进程找不到未注册的 Typer；额外两项 skip 缺真实 Bash 祖先。
3. 修正源码 `.pth` 注册与真实 Bash 后，`evidence/environment-preflight.xml` 对应的 4 项均通过，耗时 13.041089 秒。未改测试集合或 skip 装饰器；随后完整重跑。

以上是环境问题与真实尝试记录，不是 Typer 产品缺陷或模型回答失败。每次只清理精确 ID／名称／自有 token 匹配的 `bench-scenario-research-ty-*` 容器，历史清理证据保留在对应 attempt。

### 最终运行入口与证据

`verify_target.py` 是本轮受控驱动；目标容器只执行 `python3 -B /environment/verify_target.py`。挂载、镜像、命令、源码及驱动摘要见 `target-runtime.json`。完整 pytest 保留 `--cov --cov-report=term-missing --showlocals --numprocesses=2 -ra` 及上游 strict 配置，输出独立 JUnit。

最终证据目录为 `evidence/`：

- `runtime.stdout.log`：实际 Python／平台／Typer 来源。
- `install-offline.command.json` 与日志：真实离线安装命令和结果。
- `native-tests.command.json`、stdout／stderr、JUnit、`native-regression-result.json`：完整测试的原始输出及分类计数。
- `business-calibration-result.json` 和逐模式输出：咨询、两种正常诊断、已有类型能力，以及 APP-R0 未满足／APP-R1 参考候选可达性。
- `container-resources.json`：实际 UID、cgroup 容器内存峰值及子进程 RSS 高水位，二者不混为一项。
- `verify_target.executed.py`、`profile-executed.json`：最后一次运行开始时封存的驱动与环境档案。

完整原生集合已通过：1,505 项中 1,481 通过、22 普通 skip、2 XFAIL，零失败／错误，耗时 187.781728 秒。22 普通 skip 为 20 项 Windows、2 项 macOS 条件；XFAIL 保留上游 Markdown 换行两项标记。

原生阶段容器峰值为 315,990,016 字节，子进程 RSS 高水位 102,224 KiB；两者定义不同，不相加或互相替代。

原生通过后的第一轮业务观察继承了测试的 `TERMINAL_WIDTH=3000`，参考应用的 Rich 帮助触及单用例输出上限；该组合运行的 `evidence/target-result.json` 如实保留 error，不覆盖为成功。随后只固定业务宽度 80、加强 help 退出码检查，单独运行 `verify_business_target.py`，没有重复完整原生集合。

最终业务证据位于 `business-evidence/`：6 次咨询／诊断／类型／原版导出／参考导出校准全部符合预期，3 种错误或歧义咨询答案均被拒绝，参考应用的 2 个用户业务测试通过。此容器峰值 110,215,168 字节。D02 隐藏 help 采用本轮目标镜像、同一注册代码生成的真实输出。

最终总对账为 `verification-summary.json`；`cleanup-audit.json` 已确认本轮 4 个精确归属的容器全部删除，未触碰其他容器。profile 在运行后仅补充实际验证状态／镜像／Python 元数据；运行开始时的原 profile 副本和摘要继续保留。

### 相关定义与外部引用

格式依据为实际 `orchestrator/project_scenario_content.py` 的 `validate_environment`；原生执行边界参照 `orchestrator/project_verifier.py` 的 `verify_native`。测试入口、条件与依赖读取了固定 Typer 的 pyproject、scripts/test.sh、tests/utils.py 和两项主动重设 PYTHONPATH 的原始测试定义。

外部制品仅来自历史记录中的固定 PyPI 文件 URL，精确列表留在 `downloads.json`，没有最新版本或模型价格假设。

## Caveats / Not Found

- 本轮取证是环境、完整原生测试和控制端参考业务候选；模型调用与模型完成数为 0。
- 不包括 upstream 的 mypy／ty／ruff、文档构建或全 Python／多平台 CI；Windows／macOS 条件跳过需按原始报告保留。
- 目标验证使用独立 venv、持久候选路径注册和真实 Bash 父进程。正式原生适配需复现这些条件；只设置一次 PYTHONPATH 或仅以 Python 为祖先的启动方式不能据此声称等价。
- 本轮不写产品或规范、不提交推送或部署；只操作本任务精确命名的专属验证容器和研究目录。
