# 真实 GitHub 项目审查：Tenacity

研究日期：2026-10-21。已完成固定源码、原生基线、实际文件重试场景和 [二十步路线](./tenacity-roadmap-20.md)；未实施路线、冻结新增验收或接入正式项目库。

## 来源与成本

官方 [jd/tenacity](https://github.com/jd/tenacity)，完整提交 [32ac68f0941319c0d2f4fb927f96e4ee29bb46c6](https://github.com/jd/tenacity/tree/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6)。Apache-2.0，保留 LICENSE、版权头与适用归属。源码动态 VCS 版本，本轮浅检出的实际安装元数据为 `0.1.dev1+g32ac68f09`，不能当正式发行版；Python≥3.10。

无必须第三方运行依赖或服务。本轮按 test extra 准备 pytest/tornado，另补 dev 中的 trio 以覆盖对应异步路径；实际版本冻结。97 个跟踪文件、280,215 字节，产品 Python 2,442 行。安装 22.160 秒，专用 venv 59,641,215 字节，含测试工具；耗时受网络／缓存影响。逐文件规模见 `size.json`，源码构建生成的 _version.py 不作为手改产品。

## 原生结构与基线

BaseRetrying 按 action 流处理 retry/wait/stop 与前后钩子；RetryCallState 保存 attempt/outcome/sleep 等状态。Retrying、AsyncRetrying、TornadoRetrying 提供同步与异步入口；wait/retry/stop 可用内置策略与自定义 callable 组合。已读控制器、RetryCallState、wait/stop/retry、nap、日志和 asyncio 的相关定义与测试，保留原工程。

完整 `pytest tests` **185 主项通过、15 子测试通过，0失败／错误／跳过**；JUnit 200 项包含二者，不重复混加。测试进程 2.996 秒、容器全程3.863秒，峰值 RSS49,148KiB，无 OOM。未跑独立 Sphinx doctest/HTML、ruff、mypy、多Python／平台矩阵；安装测试依赖不等于运行这些工具。

基线与观察使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，1000:1000、无网络、只读根／源码／依赖、移除 capabilities、禁止提权、256MiB无额外swap、PID128，HOME为临时空目录。未挂任何账号或真实配置；两个容器均已删除核对。

## 实际场景与路线依据

临时 JSON 配置最初不存在，原生 before 钩子在第3次尝试前发布文件；重试捕获前两次 FileNotFoundError，第三次实际读回中文配置，次数与值均断言。全程使用 wait_none，没有真实长休眠，实际导入来自 `/source/tenacity`。

三项原版复现：零指数倍率在1025次编号时返回最大等待；sum组合1000个等待策略抛RecursionError而flat对照成功；同一装饰器重入导致外层第2次尝试统计为4。对应上游 #710/#748/#701 线索均经过本地复现，未把原issue中的静态判断直接当证据。

另外17项是基于实际控制器签名与场景的增强提案。现有 enabled、name、retry_with、wait_exception、stop_before_delay、异步回调、原因链环检测和pickle支持均未重新计数。手写自定义策略／sleep／回调的替代方式明确保留；提案不是维护者承诺。同步强制超时、任意generator自动恢复、隐式业务事务等没有被虚构成可实现保证。

## 证据与重跑

本地忽略证据根 `.deploy/github-100-research/core-utils/tenacity/`；跨机器重新准备，不把依赖和日志混入正式源码快照。

```bash
git clone https://github.com/jd/tenacity.git <checkout>
git -C <checkout> checkout --detach 32ac68f0941319c0d2f4fb927f96e4ee29bb46c6
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_baseline.py baseline .deploy/github-100-research/core-utils/tenacity --tests tests
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/core-utils/tenacity
```

`repository.json`／`revision.txt`／`issues.json`／`source/LICENSE` 保存来源与许可；`installation*.json`／`install.log`／`requirements-frozen.txt`／`size.json` 保存依赖与成本；`baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json` 保存实际计数和隔离；`observe.py`／`observations.log`／`observations-result.json` 保存原版差异。路线、复核状态、摘要在 `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`，执行工具副本随证据保留。

目前 verifier 只支持既有 app.py 行协议，不能把本轮原生测试说成已经接入。候选加载、冻结验收、累计改进回归和资源预算适配均待后续。未修改上游源码、正式库、业务或账号数据，未提交、推送、部署或向上游发送消息，未执行真实模型评测。
