# Research: 三仓统一原生回归 wrapper 校准

- Query: 统一 wrapper 能否在原版测试与配置不可被候选删改的条件下，保持三仓完整集合、严格 doctest、真实源码绑定与正确失败判定？
- Scope: internal；指定镜像、已有离线制品、仅新 wrapper 的原版／候选／参考修复及覆盖保护对照。
- Date: 2026-10-21

## Findings

### 当前证据状态

最终草案为 `research/content-drafts/shared/native_regression.py`，SHA-256 `3bbf34e44c67ae040ade28f601634f7ef61af9c8f38da6fad1cb4e6cf8cd6ec0`。实际源码差异在 `wrapper-calibration.patch`，摘要在 `wrapper-changes.json`。所有结果是新 wrapper 的真实执行，不是借用此前普通原生测试日志。

| 项目 | 最终版本校准 | 完整节点与结果 |
| --- | --- | --- |
| python-frontmatter | 原版冻结、原版候选、参考修复、删除测试／替换 conftest、删 doctest、源码行为错误共六项均符合各自预期 | 正例均 67 通过，严格 DoctestItem 11；源码错误仍收集 67，28 失败／39 通过，正确拒绝 |
| pydantic-settings | 原版冻结、原版候选、参考修复三项均通过 | 每次 1,261 节点，1,256 通过／5 普通跳过，逐节点结果与 contract 相等 |
| Typer | 最终版本原版冻结、原版候选对照两项均通过 | 每次 1,505 节点，1,481 通过／22 平台跳过／2 XFAIL，真实 Bash 父进程 |

`latest.json` 定位每仓本轮目录；三仓均已生成独立 `completion-audit.json`，总审查位于本目录同名文件。最终源码哈希、节点、原始 XML／报告、临时源码路径零残留与精确清理全部对账通过；不是仅凭冻结轮或退出码推断完成。

### 可信测试与覆盖对照

- 只读原版 `seed/library` 复制成临时测试树；FM／PS 只叠加允许的实现，原版 tests、conftest、pyproject 和配置保留或恢复。Typer 用户应用任务保持整份库固定。
- 插件自动发现关闭，仅加载已读实际 dist-info 入口的固定插件白名单。候选 conftest 不参与；真实删除原 tests 并把根／包 conftest 改成抛异常后，仍恢复原 67 项并全部通过，未执行这些候选 hook。
- FM 两个实现文件中八处含 doctest 的文档字符串被真实删除；独立重建后的候选实现摘要与 wrapper 记录相同。wrapper 从只读原文 AST 恢复示例文本到候选对象，实际执行完整 11 个 DoctestItem，普通 56 项也保留。
- 将原版 `metadata.update(fm_data)` 改成 `metadata.clear()` 后，完整 67 项仍收集，但原始 XML／逐节点报告均出现 28 项失败，不能以 wrapper 退出码 0 冒充通过；控制端必须读取它的 JSON status。
- contract 固定原版摘要、Python／pytest／插件版本、完整节点及逐节点 passed／skip／xfail。不是只比较总数；新增候选测试不能补足丢失的原生能力。

### 实际修正与失败留证

1. Typer 使用固定数组 `bash -c '"$@"; result=$?; exit "$result"' bench-native <pytest argv>`，后续命令防止 Bash 优化为 exec。原始进程记录证实 master 的真实父进程为 `/usr/bin/bash`，worker 的父进程为 Python。
2. 首轮 Typer 保留全部 1,505 节点，但两个上游 test_scripts 在覆盖 PYTHONPATH 的子 coverage 进程中找不到 typer，结果为 1,479 通过／2 失败／22 skip／2 XFAIL，未冻结 contract。完整失败证据留在 `typer/run-e544516532/`，容器已精确清理。
3. 修正在 `/work` 独占验证 venv 暂存一个只含本次测试树路径的 `.pth`，不安装外部 Typer、不执行候选 build、不改原版配置；ExitStack 在返回前删除，每个校准阶段独立确认残留为 0。该机制只用于 Typer 的既有子进程测试，拒绝修改共享／宿主解释器。
4. 该修正加入共用退出清理上下文后，FM／PS 已重新在最终源码哈希上校准；早期成功和失败目录均保留，不覆盖原始当轮。

### 环境、资源与清理

镜像固定 `sha256:d055c5f0035c8fb3f204ed97d6f774a38afdb3515f5503f7fa028adb6a5e908d`，实际 Python 3.12.15。每个容器无网络、UID1000、只读根、cap_drop ALL／no-new-privileges，`/work` 显式 exec，原版／候选／控制脚本及 offline 制品只读挂载。

资源来自各环境 `profile.regression`：FM 180 秒／512 MiB／64 PID，PS 300 秒／1,024 MiB／128 PID，Typer 600 秒／1,024 MiB／128 PID。cgroup 与真实配置分别存各 run 的 `evidence/cgroup.json` 和 `container.json`，不把单进程 RSS 和含 tmpfs 的容器峰值混用。

最终轮的容器总内存峰值（含 tmpfs）分别为 FM 100,786,176 字节、PS 688,324,608 字节、Typer 350,236,672 字节。Typer 两次 wrapper 回归阶段为 196.172 秒／198.917 秒；这不是最佳预算或并发容量承诺。

只创建 `bench-scenario-research-reg-*` 前缀下本脚本登记的精确容器，查询与移除均核对 ID／唯一标签；不查询或停止其他账号环境。Docker wait 每次为 1 秒，长测通过分次状态查询返回。本轮全部六个容器（含首次成功和首次失败证据轮）均已保存 removed 证明，没有遗留执行。

### 文件与复核入口

- `calibration_runner.py`：容器内固定安装与 wrapper 校准场景，所有命令／stdout／stderr／步骤实际落盘。
- `calibrate.py`：创建、返回状态及精确清理；`latest.json` 保存实际 run 归属。
- `<project>/<run>/evidence/contract.json`：同一目标镜像原版执行后冻结的节点和插件 contract。
- `<project>/<run>/evidence/*-wrapper.json`、对应子目录的 `junit.xml`／`pytest-*.json`：单一 wrapper JSON、原始 XML、worker 收集及阶段结果、实际导入路径与进程父子关系。
- `audit.py`、已完成仓的 `completion-audit.json` 与 `evidence-sha256.json`：独立核对上述原始证据、反例变更重建、最终源码哈希和清理。

## Caveats / Not Found

- 本校准不验证模型评分质量，不构成模型任务完成或生产发布；未调用模型、未修改产品或规范、未执行 Git。
- 暂未运行 wrapper 超时、额外平台或其他资源档位反例；不能借本轮结果宣称这些已通过。原版失败不会生成候选可用 contract。
- 三仓校准完成只证明此统一回归支架及已列对照可用；主会话仍须审阅后集成到正式 verifier，不把研究脚本通过称为产品入口已经接通。
