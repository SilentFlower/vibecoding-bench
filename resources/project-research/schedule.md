# 真实项目审查 02：schedule

研究日期：2026-10-21。结论：适合轻量 Python 工程迭代研究；已完成来源核对、原生基线、实际使用场景和 [20 步改进路线](./schedule-roadmap-20.md)。尚未实现路线、制作冻结验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[dbader/schedule](https://github.com/dbader/schedule)，用途为在 Python 进程内周期执行可调用对象，无独立调度服务。
- 固定提交：[82a43db1b938d8fdf60103bd41f329e06c8d3651](https://github.com/dbader/schedule/tree/82a43db1b938d8fdf60103bd41f329e06c8d3651)，对应包版本 1.2.2、Python ≥ 3.7。研究时检出的 master 位于该提交，已切换 detached HEAD。
- MIT 许可证；复制源码须保留 LICENSE.txt 及版权／许可声明。
- 官方仓库未归档，但本轮元数据的 pushed_at 为 2024-05-25，维护活跃度有限。开放 issue 是需求线索，不代表维护者已同意本路线或会接受相关修改。

## 工程规模与依赖成本

以下来自固定工作树和实际运行，不采用 README 的概括或 GitHub size 代替测量。

| 项目 | 实测结果 |
| --- | --- |
| 跟踪文件 | 32 个，共 166,428 字节，约 163 KiB |
| Python 产品源码 | schedule/__init__.py 一个模块，945 行，主要为 Scheduler／Job 和便捷函数 |
| 原生测试 | test_schedule.py，1,599 行、81 个实际测试 |
| 必需运行依赖 | 无；核心使用 Python 标准库 |
| 时区功能 | 上游可选 extra timezone 使用 pytz；本次安装以覆盖时区测试 |
| 外部服务／凭据 | 本次基线和使用场景均不需要 |
| 本机环境 | Python 3.12.3、Linux；测试依赖 POSIX TZ 与 time.tzset |
| 安装 | 独立虚拟环境安装本地源码、pytest、pytz，约 7.90 秒；受网络与缓存影响 |
| 虚拟环境磁盘 | 51,225,933 字节，约 51.2 MB，包括 pip、测试工具和时区库，不是运行包本身大小 |
| 完整基线 | 81 通过、0 失败、0 错误、0 跳过；pytest 0.374 秒、进程墙钟 0.618 秒 |
| 基线子进程峰值 RSS | 50,076 KiB，约 48.9 MiB |

测试依赖实际冻结为 pytest 9.1.1、pytz 2026.5，以及 iniconfig 2.3.1、packaging 26.3、pluggy 1.7.0、Pygments 2.21.0。产品 pyproject.toml 没有核心运行依赖；没有为本轮研究安装完整 requirements-dev.txt、Sphinx、格式和类型检查工具，也未执行多 Python 版本矩阵。

## 原生数据路径

`Scheduler.every()` 创建 Job → 单位／at／to／until 等构建配置 → `Job.do()` 绑定回调、计算 next_run 并加入 jobs → `Scheduler.run_pending()` 挑选到期任务 → `Job.run()` 调用实际回调、更新 last_run 和下次时间 → 返回 CancelJob 时由调度器移除。

Job 的 interval、unit、at_time、at_time_zone、start_day、last_run、next_run、cancel_after 和 tags 均为真实源码字段。默认同步串行执行；run_pending 不补跑错过的全部周期，普通周期包含回调执行耗时，异常默认向调用者传播。带时区的 at 用 pytz 计算，公开 last_run／next_run 保持本机朴素时间。这些既有规则不能直接标成缺陷。

项目没有独立命令行程序、数据库服务器或网页入口。后续验收应直接导入候选 schedule 包，控制时间并观察真实回调和文件副作用，保留原生工程结构。

## 已运行的验证

1. 原生完整测试：执行 `python -m pytest -q -ra test_schedule.py schedule --junitxml=...`，81 项全部通过。原始日志没有警告汇总；未声称格式／类型／文档检查通过。
2. 正式账号镜像：`ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，UID/GID 1000、无网络、只读根、删除 capabilities、禁止提权、256 MiB 内存／无额外 swap、PID 64；源码与预备依赖只读挂载，未挂账号 HOME 或凭据。完整 81 项通过，pytest 约 0.62 秒，容器整体约 1.54 秒，无 OOM；删除临时容器后再次检查不存在。
3. 原生使用场景：创建独立 Scheduler，注册带参数且带 tag 的任务；将可读的 next_run 置为已到期，运行 run_pending，实际写入临时 JSON 文件得到 `{"value": 7}`；回调返回 CancelJob 后标签查询为空。临时文件随上下文删除。
4. 原版路线观察：25 条观察覆盖 20 个步骤，22 条显示目标差异、3 条对照匹配。包含两次有界子进程超时用于复现非法间隔；超时进程已杀死并回收。目标差异包含增强接口缺失，不能统称为 22 个 BUG。

上述容器测试仅证明预备依赖后可隔离运行原生测试。现有产品 ProjectVerifier 仍使用 app.py／JSON 行协议，不能据此宣称已完成平台原生接入。

## 已确认问题和增强边界

- [#670](https://github.com/dbader/schedule/issues/670)：run_all 文档承诺任务之间延迟，实际 1／3 个任务都会在最后一次后额外 sleep。零任务为通过对照。
- [#646](https://github.com/dbader/schedule/issues/646)：尚未选择单位的 Job 调用 repr 抛出 TypeError，已配置单位的对照正常。
- 源码实际复现：零／负 interval 的注册进入 `_schedule_next_run` 无法正常结束；两种输入均在 0.5 秒研究上限被回收。正数 0.5 秒间隔可正常注册，不能误报所有小数间隔不支持。
- 其余为 17 项增强：小数随机范围、毫秒单位、多星期／多时间点、隔周星期、时钟对齐、固定节奏、单次任务、时间窗口、日期排除、跳过／重置／立即首跑、任务元数据、优先级、最近结果和失败次数策略。逐项来源、范围和验收见路线文档。

上游文档主动提醒：不保证亚秒精确执行，不原生提供持久化、并发执行或节假日引擎。本路线的毫秒仅表示配置单位；日期排除只接收显式日期；时间控制用于确定逻辑正确性，不宣称实时保证。所有增强为试点维护路线提案，默认行为需要兼容，不能把研究提案描述为上游既有承诺。

## 重跑与证据

证据根：`.deploy/real-project-review-20261021/schedule-review/`。其中 source 为完整冻结检出，venv 为独立环境；本地目录未纳入 Git，跨机器重跑需重新检出和安装。

```bash
git clone https://github.com/dbader/schedule.git <checkout>
git -C <checkout> checkout --detach 82a43db1b938d8fdf60103bd41f329e06c8d3651
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在 checkout 中执行 `<venv>/bin/python -m pytest -q -ra test_schedule.py schedule`。原版复现脚本的当前位置约定见 reproduce.py；本轮实际执行命令为：

```bash
PYTHONPATH=.deploy/real-project-review-20261021/schedule-review/source \
PYTHONDONTWRITEBYTECODE=1 \
  .deploy/real-project-review-20261021/schedule-review/venv/bin/python \
  .deploy/real-project-review-20261021/schedule-review/reproduce.py
```

- repository.json、revision.txt、issues-page1.json、issues-page2.json：官方来源和需求正文，共保留 147 个开放 issue。
- installation.json、installation-result.json、install.log、requirements-frozen.txt、test-requirements.txt、size.json：安装及运行成本。
- baseline-result.json、baseline-tests.xml、baseline-tests.log：宿主原生基线。
- container-baseline.py、account-runtime-result.json、account-runtime-tests.log：实际隔离容器与清理结果。
- reproduce.py、reproductions-result.json：原版问题、增强缺口、通过对照和真实文件副作用。
- roadmap-20.json：结构化研究路线，明确 research_only=true、production_integration_ready=false。
- evidence-sha256.json、review-result.json：证据摘要和研究完整性检查。

本轮未修改上游源码、正式库、产品实现、线上数据或先前未提交改动。未创建 task、提交、推送、部署，也未向上游发送 issue／PR。模型测试和生产请求均为 0。
