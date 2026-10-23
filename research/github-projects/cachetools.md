# 真实 GitHub 项目审查：Cachetools

研究日期：2026-10-21。来源、固定源码、适用原生基线、文件缓存场景和 [20 步路线](./cachetools-roadmap-20.md)研究完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与原生结构

官方 [tkem/cachetools](https://github.com/tkem/cachetools)，完整固定提交 [6f23e2a7b75a42d30cb9d890ab3ca4059ee01bfd](https://github.com/tkem/cachetools/tree/6f23e2a7b75a42d30cb9d890ab3ca4059ee01bfd)，实际源码与安装版本 7.2.4。MIT 许可原文和归属保留在 LICENSE；Python ≥3.10，无必需第三方运行依赖，无外部服务。

已读取 Cache 的大小账本、FIFO/LFU/LRU/RR、时间缓存的 timer/link/heap/expire、key 工厂、cached/cachedmethod 的锁与条件路径和 descriptor 定义。产品 6 个 Python 文件、1,712 行；44 个跟踪文件、260,285 字节。既有 condition 防击穿、方法统计、定制 key/getsizeof/timer/ttu、expire 返回值都列为已有能力，未重复计数。

## 实测成本与原生基线

| 项目 | 结果 |
| --- | --- |
| 安装 | 17.001 秒；独立 venv 50,138,533 字节，含 pip/pytest |
| 完整原生 tests | 366 主项通过、8 个子测试通过、0 失败／错误／跳过 |
| JUnit | 374 项，包含主项和上述 8 个子测试，不额外混加 |
| 测试耗时／容器全程 | 1.504 秒／2.829 秒 |
| 峰值 RSS | 41,788 KiB；256 MiB 配额未 OOM |

固定原版与原生测试均未修改。本轮 Python 3.12，只执行完整 tests 集合；未跑多版本／多平台矩阵、独立静态检查、文档构建或外部类型检查器。#394 的 pyright 兼容诉求没有被当作已复现运行时缺陷计入。

基线与原版观察分别使用 V3 镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，非 root 1000:1000、无网络、只读根与源码／依赖、移除 capabilities、禁止提权、256 MiB 无额外 swap、PID 128，HOME 指向空临时目录。没有账号或业务配置挂载，两容器已删除核对，无 OOM。

## 真实使用与二十步研究

实际写入中文 JSON 临时文件，cached(TTLCache) 第一次读取、第二次命中避免读取、受控时钟过期后重新读取；三次值一致、实际文件读取数为 2。导入路径确认是固定 `/source/src/cachetools`。

原版复现类访问 cachedmethod 的合法关键字 receiver 被拒绝，列为 1 项修复；实例 pickle 限制上游未承诺支持，按增强记。其余 19 项围绕键语义、定向失效、同步／异步请求协调、容量与寿命管理、策略和恢复。每项均有业务场景、已读源码或实际缺口对照、交付和正反验收，不为锁组合和缓存类型拆步骤。

实测还记录默认 key 对等价调用的三个 miss、多个方法共享缓存冲突、可变值成本不自动更新、LRU 扫描淘汰热点；均承认现有约定或自定义 key/cache 的替代方式，没有都称为 bug。同键条件重入观察在独立子进程中限时 0.5 秒，子进程已终止回收，不留后台死锁。增强为试点提案，不代表维护者同意。

## 证据与重跑

本地忽略证据根：`.deploy/github-100-research/core-utils/cachetools/`；源码、venv、日志不进入正式内容快照，跨机器需重新准备。

```bash
git clone https://github.com/tkem/cachetools.git <checkout>
git -C <checkout> checkout --detach 6f23e2a7b75a42d30cb9d890ab3ca4059ee01bfd
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_baseline.py baseline .deploy/github-100-research/core-utils/cachetools --tests tests
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/core-utils/cachetools
```

来源在 `repository.json`／`revision.txt`／`issues.json`／`source/LICENSE`；安装和大小在 `installation*.json`／`requirements-frozen.txt`／`size.json`；原生结果在 `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`；原版观察在 `observe.py`／`observations.log`／`observations-result.json`。`roadmap-20.json`／`review-result.json`／`evidence-sha256.json` 保存计数与摘要，实际执行脚本副本已保留。

研究未适配目前仅支持 app.py 行协议的 verifier。冻结验收、候选加载核对、原生入口接入和单步资源验证须另行完成，不能凭本轮通过称模型已经完成路线。未修改上游源码、产品、正式库或账号数据，未提交、推送、部署或向上游发消息，未执行真实模型评测。
