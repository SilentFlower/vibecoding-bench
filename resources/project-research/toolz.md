# 真实 GitHub 项目审查：Toolz

研究日期：2026-10-21。已完成来源、固定源码、适用原生基线、实际数据管道与 [20 步研究路线](./toolz-roadmap-20.md)；路线尚未实现，独立冻结验收和正式库接入尚未开始。

## 来源与固定版本

- 官方：[pytoolz/toolz](https://github.com/pytoolz/toolz)，完整提交 [451af60dec590a6010e2babdbf391ea8f815122f](https://github.com/pytoolz/toolz/tree/451af60dec590a6010e2babdbf391ea8f815122f)，本轮实际安装元数据版本 1.2.0，最低 Python 3.9。
- 许可证：实际 `LICENSE.txt` 和 pyproject 均为 BSD-3-Clause；GitHub 元数据的 NOASSERTION 不替代许可证原文。
- 无必须的第三方运行依赖；真实工程由 itertoolz／dicttoolz／functoolz、curried、recipes、sandbox 及 tlz 兼容入口组成。

## 原生工程与实测成本

已读 tail／partition_all／isdistinct、映射复制与嵌套更新、join、merge_sorted、reduceby、memoize、pipe、recipes 和 sandbox 中的实际定义；同时核对原生测试和公开导出。curry 管理部分参数和签名，memoize 已支持外部映射，merge_with／join／partitionby 均有可用组合能力；路线没有把这些已有能力重新计数。

| 项目 | 实测结果 |
| --- | --- |
| 跟踪文件／字节 | 81／290,337 |
| 独立 venv | 50,142,422 字节，包含 pip 和 pytest 等测试工具 |
| 安装 | 15.563 秒；网络与缓存影响耗时 |
| 原生 pytest | 192 通过、1 跳过、0 失败／错误 |
| 测试耗时／容器全程 | 2.109 秒／3.371 秒 |
| 测试峰值 RSS | 45,528 KiB；256 MiB 容器内未 OOM |

命令沿用 pyproject 的完整 `toolz` testpaths，包括 sandbox 原生测试；唯一跳过为 Python 3.14 才提供的 annotationlib，本轮 Python 3.12 不适用。未执行跨版本矩阵、bench、文档构建、覆盖率或全模块额外 doctest；原生集合自身收集的 doctest 不重复计数。未修改测试或排除失败项。

## 离线隔离与原版观察

基线与观察分别使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，UID/GID 1000、无网络、只读根、源码与专属依赖只读挂载、cap_drop=ALL、no-new-privileges、256 MiB／无额外 swap、PID 128。HOME 指向空临时目录，未挂账号目录或凭据；两容器已删除并确认不存在。

原生 pipe→reduceby 实际聚合中文地区订单，得到华东 7／华南 4，原记录不变；实际导入来自固定 `/source/toolz`。复现零项 tail 返回整个列表、partition_all 丢弃与内部占位字符串同对象的数据、isdistinct 拒绝没有长度但可重复遍历的 Iterable。其余 17 项为已核对当前能力和签名的增强；具体对照与业务场景见逐项路线，未把所有增强说成 bug。

官方 issue #626／#579／#515／#580／#567／#392／#400／#510 提供部分需求线索，原文已保存并与固定源码对照。增强是本次试点提案，不代表维护者承诺。已有 apply、excepts、countby、partitionby、外部缓存与高阶组合均保留，不把简单别名拆为额外步骤。

## 重跑与证据

证据根：`.deploy/github-100-research/core-utils/toolz/`，本地忽略，不进入产品源码快照；跨机器需重新准备。

```bash
git clone https://github.com/pytoolz/toolz.git <checkout>
git -C <checkout> checkout --detach 451af60dec590a6010e2babdbf391ea8f815122f
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

本轮实际入口：

```bash
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_baseline.py baseline .deploy/github-100-research/core-utils/toolz --tests toolz
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/core-utils/toolz
```

`repository.json`／`revision.txt`／`source/`／`issues.json` 保存来源；`installation*.json`／`install.log`／`requirements-frozen.txt`／`size.json` 保存成本和依赖；`baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json` 保存原生计数；`observe.py`／`observations.log`／`observations-result.json` 保存实际场景与差异；`roadmap-20.json`／`review-result.json`／`evidence-sha256.json` 保存逐项路线和校验摘要。执行脚本副本也保存在证据根。

研究完成不代表平台 verifier 已适配原生库。现有 app.py JSON 行协议不能直接证明上述迭代完成；后续需保持 Toolz 原工程并建立加载候选源码的独立验收和累计回归。本轮没有修改业务、上游源码或正式库，未提交、推送、部署或向上游发消息，未进行真实模型执行。
