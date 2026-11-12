# 真实 GitHub 项目审查：tqdm

研究日期：2026-10-21。适合真实进度库的累计工程；基础CLI轻量，可选数据分析/Notebook测试环境的较高成本单独记录。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./tqdm-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[tqdm/tqdm](https://github.com/tqdm/tqdm)，元数据归档状态为 false。
- 完整固定提交：[9cf5a12b1f955468a17f0ba3c59092b23e4258ac](https://github.com/tqdm/tqdm/tree/9cf5a12b1f955468a17f0ba3c59092b23e4258ac)，包版本 4.70.1。
- 许可证：MPL-2.0 AND MIT，遵循原LICENCE按贡献/文件列出的声明，不能当作MIT任选或全仓MIT。保留LICENCE、作者声明及固定源码；已核对Mozilla官方MPL-2.0全文并保存MPL-2.0.txt与来源。后续分发包含改动的受MPL覆盖源码须保留对应许可和源码提供方式，不移除原声明。本轮仅本地研究，未分发改动。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

std.tqdm持有n/total、时间平滑、实例WeakSet、全局写锁和显示生命周期，format_meter生成终端字符串；utils处理显示宽度、环境覆盖及IO包装。cli解析参数并转发二进制stdin到stdout。asyncio继承原类；contrib.concurrent包装真实线程/进程/解释器池；itertools推断组合总数；pandas通过闭包注册progress_*；Discord/Telegram为可选消息输出适配。已读上述类/方法及对应测试，保留真实多模块结构。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 109／1149967 |
| 产品源码 | 4663 行 Python，31 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | Linux基础运行无必需第三方依赖，Windows条件依赖colorama；本轮按tox Python套件选择pytest/cov/timeout/asyncio、NumPy、Pandas、Rich、Dask、ipywidgets、Matplotlib、Cython，并额外安装requests用于完全模拟的可选组件观察。NumPy2.5.4、Pandas3.0.6等实际版本见freeze；上游无统一锁。本仓venv包含全部这些可选工具，因此不能把测试环境大小当成CLI必需成本；安装分两阶段，耗时合计 |
| 外部系统 | 基础CLI/进度无服务；本轮所有容器无网络。requests组件仅使用假Session/假submit，未访问Discord/Telegram、未提供真实token，也未发消息。TensorFlow/Keras和浏览器Notebook前端未装；原生Tk导入测试所需libtk8.6=8.6.13-2、libtcl8.6=8.6.13+dfsg-2仅装进临时研究派生镜像，不改账号原镜像/生产。系统依赖准备55.07秒，派生镜像完整大小301,264,419字节（包括原镜像）；Tk可导入不等于已做GUI视觉验证 |
| 安装耗时 | 88.72 秒；受缓存与网络影响 |
| 独立 venv 大小 | 346,130,988 字节，含 pip 和本轮测试工具 |
| 原生基线 | 175 通过、0 失败、0 错误、4 跳过 |
| 测试进程墙钟／峰值 RSS | 4.51 秒／109,660 KiB |

完整Python原生pytest按tox的-k not perf原样执行，最终175通过、0失败/错误、4跳过、7性能项未选中。4跳过为3项需Python3.14解释器池与1项无Keras。首次原账号镜像缺libtk8.6.so导致174通过/1失败/4跳过，日志/XML保留pytest-tk-attempt。手工Tk skip和包装脚本缺main保护导致spawn重入均只作辅助失败记录（manual-tk-skip-observation、wrapper-spawn-attempt），不作为准入基线。已从固定账号镜像派生本地临时研究镜像，仅用Debian源安装Tk/Tcl及其动态库，随后无网/只读运行完全不带插件的原命令；Tk原生导入测试现已通过。包含Pandas/Dask/Matplotlib模块/ipywidgets模块/线程进程/异步的全部Python测试；未跑性能基准、nbval执行.ipynb、tox覆盖上传、多Python/真实GUI。上游Pandas测试仍断言错误的DataFrame.map列数进度；路线11须修正对应预期。

## 隔离验证与真实使用

原生基线与观察均使用 `vibebench-local-research-tqdm-tk:9cf5a12`，镜像 ID `sha256:7c48875a811ddc23a58b615f72f4772b54333c497cf28ab31df8b8729d93aa58`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；本仓各次临时容器均已删除并核对不存在，无 OOM。

真实python -m tqdm CLI透传19字节的三行输入，最终stderr含3/3；stdout写临时二进制文件后逐字节读回相同。确认模块来自/tmp/source/tqdm。20项原版观察包括真实小型ProcessPoolExecutor（2工作进程、11项chunksize=4得到计数3）、异步生成器与真实Pandas；网络行为仅本进程模拟。

16项修复均实际复现：组合repeat整数索引/溢出、OSC8切断、跨缓冲分隔符、实写字节回调、CLI日志参数、HEX色、网络异常掩盖、异步生成器、空DataFrame、共享total被pop、元素map总数、GroupBy虚假map、进程分块计数、异常锁恢复、Telegram删除URL未格式化和布尔环境转换。4项增强是簇宽/裁剪、可选用户文本转义、计时源、类级临时状态。Unicode只与已安装wcwidth参考结果对照，不声称所有实际终端字体相同。

已有异步迭代/gather(return_exceptions)、多条position进度、process/thread/interpreter_map、动态宽度、reset(total)/initial续跑、单位/逆速率、format_dict、时间完成点{eta}、日志重定向和callback IO。上游#1801的无长度输入min空序列已在该commit修复，不计BUG；#1745请求的完成时钟已可用bar_format显示，不重复增强。外部envwrap可作为布尔解析的替代，但本次实际未安装，复现的是utils内置回退。测试/格式化迁移、CI发布设置和新动画不计步。

## 二十步路线与接入边界

20项为16项复现修复与4项增强。每个修复均有原生入口或隔离模拟结果；同类情况合并，如Discord/Telegram响应前异常合一项、product repeat的索引/负值/零次/溢出合一项。Pandas空形状、重复注册配置、元素调用计数与错误API注册是不同触发/收益，未按DataFrame行列矩阵拆步。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。须用真实候选tqdm导入、CLI字节转发、Pandas返回结果与显示计数及真实有界进程池执行验收；网络适配保持离线假Session，实服务需另有明确授权。MPL声明及源码分发安排保留到后续快照。基础CLI无服务但本轮可选测试venv较大；512MiB/PID128未验证默认256MiB或生产verifier，20步未实施。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/tqdm/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/tqdm/tqdm.git <checkout>
git -C <checkout> checkout --detach 9cf5a12b1f955468a17f0ba3c59092b23e4258ac
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> pytest pytest-cov pytest-timeout pytest-asyncio numpy pandas rich dask ipywidgets matplotlib cython requests
```

本仓先用 `prepare_tk_image.py` 在临时容器安装Tk库，派生 `vibebench-local-research-tqdm-tk:9cf5a12`，原账号镜像保持不变。`tk-system-install.log`、`tk-system-image.json`保存包版本、耗时、镜像ID和清理记录；准备阶段仅下载系统依赖可联网，下面的所有基线/观察仍无网。跨机器先运行 `.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/text-formats/tqdm/prepare_tk_image.py` 准备对应派生镜像，再执行：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/tqdm/native_tk_run.py run tqdm baseline -- \
  -m pytest -k not perf -p no:cacheprovider --junitxml=/results/tests.xml
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/tqdm/native_tk_run.py run tqdm observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
