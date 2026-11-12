# 真实 GitHub 项目审查：alive-progress

研究日期：2026-10-21。适合真实终端进度工具的累计工程，保留动画编译器、单元格布局、工作线程及全局打印/日志适配等原生结构。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./alive-progress-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[rsalmei/alive-progress](https://github.com/rsalmei/alive-progress)，元数据归档状态为 false。
- 完整固定提交：[69d9bf0aba6276e2434a3a595cceca55040d64d7](https://github.com/rsalmei/alive-progress/tree/69d9bf0aba6276e2434a3a595cceca55040d64d7)，包版本 3.3.0。
- 许可证：MIT。保留LICENSE和源文件版权；许可证与setup.py、官方仓库元数据一致。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

alive_bar返回上下文管理器，内部闭包管理count/processed/percent、指数平滑速率与ETA、动画线程和最终收据。alive_it包装同步迭代器并自动递增；__AliveBarHandle通过描述符暴露text/title/current/rate/eta/elapsed/receipt。configuration创建不可变Config；hook_manager包装stdout/stderr与已有StreamHandler；terminal分TTY/非TTY/Jupyter；cells使用graphemeu提供宽字/簇单元格。已读这些定义与原生配置/进度/打印测试；不改造成统一app.py。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 79／56459125 |
| 产品源码 | 3359 行 Python，29 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | 产品精确要求about_time==4.2.1和graphemeu==0.7.2；按requirements/test.txt安装pytest、pytest-cov、pytest-sugar、click，实际所有传递版本已冻结。本地setup.py安装，没有另外假定统一lock |
| 外部系统 | 无数据库/云API/外部服务；动画为本机线程。本轮不安装MPI/Celery/Jupyter，未做实机终端视觉或Windows验证 |
| 安装耗时 | 17.51 秒；受缓存与网络影响 |
| 独立 venv 大小 | 29,407,841 字节，含 pip 和本轮测试工具 |
| 原生基线 | 563 通过、0 失败、0 错误、0 跳过 |
| 测试进程墙钟／峰值 RSS | 1.39 秒／44,348 KiB |

执行完整tests目录pytest，与上游CI/nox原生pytest入口一致：563通过、0失败/错误/跳过。未跑nox外包装、多Python矩阵或真实TTY/Jupyter/Celery/MPI。原生测试的内部_testing受控时钟保持原样；观察另用真实上下文和合成流。

## 隔离验证与真实使用

原生基线与观察均使用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；本仓各次临时容器均已删除并核对不存在，无 OOM。

alive_it真实消费[1,2,3]，处理成[2,4,6]，写临时JSON文本并读回，同时真实生成含3/3的最终收据；确认导入模块位于/tmp/source/alive_progress。20项独立观察均在无网容器保存JSON，时间序列使用受控位置/秒数，不等待数小时。

复现3项问题：假值callable finalize被布尔判断跳过，格式校验接受未知嵌套字段/非法转换，未启动适配器的hasattr/inspect.unwrap抛UserWarning。其余17项明确作为增强，包括分段字节兼容、近期吞吐、动态总量、多进度、响应布局、多行/颜色、命名计数器、运行时收据、每项耗时、终端窗口协议、结构化快照、异步/加权迭代、退出原因回调、挂钩策略及作用域配置。字节分段原版虽报UnicodeDecodeError，但没有把未承诺的分段字节接口称为既有BUG。

已经有自动/未知/手动模式、零和负增量、skipped=True续跑、bar.pause、最终收据与结束后改title/text、单位缩放、rate/eta文本查询、自动禁用非TTY动画、dual_line两行、打印/日志多线程同步及文件输出。它们不重复计步；命名计数器不同于一个总count，近期速率不同于现有累计速度的指数平滑，多行状态不同于固定双行。contrib分发、增加动画皮肤、测试覆盖率或新参数排列不单独计步。

## 二十步路线与接入边界

20步为3项复现修复与17项增强，来源为固定源码、原生场景和上游#331/#328/#327/#247/#20/#188/#49/#71/#297/#184/#314及README To do。动态总量与未知转已知合为一项；收据三个开关合一项；颜色的多种SGR不拆步。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。后续须运行真实alive_progress导入、有限生命周期的线程与真实临时流，分别检查计数、异常、收据与流恢复；控制端保留独立验收，不能用候选自报通过。屏幕布局需确定性终端模拟，实机视觉证据另记。512MiB/PID128基线不代表默认256MiB、多进度扩展成本或正式verifier已兼容。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/alive-progress/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/rsalmei/alive-progress.git <checkout>
git -C <checkout> checkout --detach 69d9bf0aba6276e2434a3a595cceca55040d64d7
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> pytest pytest-cov pytest-sugar click
```

本轮实际隔离执行命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run alive-progress baseline -- \
  -m pytest tests -q -ra -p no:cacheprovider --junitxml=/results/tests.xml
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run alive-progress observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
