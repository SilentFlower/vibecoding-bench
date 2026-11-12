# 真实 GitHub 项目审查：Backoff

研究日期：2026-10-21。已完成固定源码、适用原生基线、真实文件读取和 [二十步路线](./backoff-roadmap-20.md)研究；未实施、冻结新增验收或接入正式库。

## 来源与原生结构

官方 [litl/backoff](https://github.com/litl/backoff)，固定完整提交 [d82b23c42d7a7e2402903e71e7a7f03014a00076](https://github.com/litl/backoff/tree/d82b23c42d7a7e2402903e71e7a7f03014a00076)，2.2.1，MIT，保留litl, LLC.版权与LICENSE。GitHub元数据明确已归档；可以做本地维护研究，不暗称上游仍活跃或愿意接受路线。

_decorator配置on_predicate/on_exception与handler；_sync/_async执行真实调用、等待和放弃；_common处理动态配置、等待和日志，_wait_gen实现expo/fibo/constant/runtime/decay。已读这些相关实现与原生测试，保持原始工程；28跟踪文件、108,094字节，产品Python890行。无必须第三方运行依赖或服务；pyproject声明Python ^3.7，本轮实际Python3.12。

## 成本与基线

本轮按上游开发依赖范围准备pytest7.4.x、pytest-asyncio0.18.x、pytest-cov3.x、requests2.x、responses0.20.x，实际版本冻结。安装19.612秒，专用venv46,138,657字节；网络／缓存影响耗时。

完整原生tests **123通过、0失败／错误／跳过**，测试0.493秒、容器全程1.490秒、峰值RSS47,092KiB，无OOM。保留2个pytest-asyncio弃用告警：未来asyncio_mode默认值变化、初始无current event loop；不把全绿说成无告警。未跑mypy/flake8、文档、全覆盖率验证或跨版本／平台矩阵，安装pytest-cov不等于证明其覆盖率门槛。

基线与观察分别在V3账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1` 中执行，UID/GID1000、无网络、只读根和源码／依赖、移除capabilities、禁止提权、256MiB无额外swap、PID128。HOME为空临时目录，未挂账号或真实配置，各次研究容器均已删除核对。

## 原版使用与改进依据

临时JSON文件第一次不存在，第二次发布后真实读回中文配置；on_exception正确重试一次，值和调用数均断言，实际加载固定`/source/backoff`。只有零秒等待，无外部服务请求。

七项复现：总预算漏算当前调用耗时（受控时钟模拟，不是真睡60秒）；有限等待源耗尽时忽略raise_on_giveup=False；装饰器复用累计日志；partial日志二次异常；异步giveup callable误判并漏await；动态配置TypeError被吞；有cap指数生成器在中间幂溢出。predicate耗尽返回0是通过对照，没有称其崩溃。导入覆盖应用日志级别按增强政策处理。

其余13项是已核对公开参数和原生结构的增强。已有runtime可用于同步／异步结果提取，动态max参数、异步handlers、raise_on_giveup、log_level等没有重计。等待、事件、配置、循环等新接口为本地提案，非维护者承诺。每步含真实场景、模块、兼容边界和正反验收；未套用统一app.py。

观察过程中为捕获预期异常和分离stdout/stderr调整过取证脚本；早期probe-preparation-attempt.log／probe-json-attempt.log保留，均不是原生基线失败。最终观察exit0，stdout为完整20项JSON，stderr保留原版未await协程RuntimeWarning，未把告警藏掉。

## 证据与重跑

本地忽略证据根 `.deploy/github-100-research/core-utils/backoff/`，源码与独立venv不混入正式项目快照；跨机器重新准备。

```bash
git clone https://github.com/litl/backoff.git <checkout>
git -C <checkout> checkout --detach d82b23c42d7a7e2402903e71e7a7f03014a00076
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_baseline.py baseline .deploy/github-100-research/core-utils/backoff --tests tests
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/core-utils/backoff
```

`repository.json`／`revision.txt`／`issues.json`／`source/LICENSE`保存来源；`installation*.json`／`install.log`／`size.json`／`requirements-frozen.txt`保存成本与依赖；`baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`保存原生结果；`observe.py`／`observations*.log`／`observations-result.json`保存原版业务与缺口。路线、复核和摘要在`roadmap-20.json`／`review-result.json`／`evidence-sha256.json`，执行脚本副本随证据保留。

目前verifier只支持旧app.py行协议，本轮不代表平台原生接入就绪。未修改上游源码、产品、正式库或账号数据，未提交、推送、部署或向上游发消息，未执行真实模型评测。
