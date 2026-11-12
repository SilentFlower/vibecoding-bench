# 真实 GitHub 项目审查：Cerberus

研究日期：2026-10-21。来源、固定源码、原生基线、真实配置文件校验和 [二十步路线](./cerberus-roadmap-20.md)研究完成；未实施路线、冻结新增验收或接入正式库。

## 来源与原生结构

官方 [pyeve/cerberus](https://github.com/pyeve/cerberus)，固定完整提交 [83f5dada76aa3179ef21b677a7f4235bf20c1566](https://github.com/pyeve/cerberus/tree/83f5dada76aa3179ef21b677a7f4235bf20c1566)，实际1.3.8。ISC许可，保留Nicola Iarocci归属和LICENSE原文；Python≥3.7，3.8以下依赖importlib-metadata，本轮3.12核心无外部运行依赖或服务。

BareValidator/动态Validator保存schema与本次document，按normalization和validation规则处理；DefinitionSchema校验、展开和缓存规则，注册表共享具名schema/rules；errors模块提供ErrorList、树和handler，utils提供TypeDefinition等扩展。已读相关类、真实规则与测试，保留公开和自定义扩展入口。65个跟踪文件、7,458,476字节，产品Python3,536行，仓库大小包含文档资源。

## 实测成本与基线

仅另装pytest，专用venv50,146,051字节；安装12.039秒，网络与缓存影响耗时。按上游tox命令运行完整 `pytest cerberus/tests`，**246通过、1跳过、0失败／错误**；唯一skip需Python2，本轮不适用。测试0.904秒、容器全程1.748秒、峰值RSS36,552KiB，无OOM。

基线和观察使用V3镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，UID/GID1000、无网络、只读根／源码／依赖、移除capabilities、禁止提权、256MiB无额外swap、PID128，HOME是空临时目录；未挂账号或真实配置，容器均已删除确认。未跑Sphinx doctest/linkcheck、pre-commit、其他Python/PyPy或平台矩阵。

## 实际场景与改进依据

真实临时JSON订单qty='3'，经validated得到整数3并补region='华东'，写出JSON再独立读回；qty=0反例明确失败并含qty错误。确认加载`/source/cerberus`，没有用其他安装副本冒充。

两项原版修复依据：逻辑oneof_schema绕过readonly而直接schema对照拒绝；重命名成自身删除字段，rename和rename_handler同时配置抛KeyError，两种中间状态症状合为一个改名交付。其余18项增强逐一核对现有规则和使用场景。rename→coerce顺序、nullable转换、dependencies不代表缺失字段必填、NaN类型语义、用户coercer修改输入均按现有约定或增强处理，不都称为bug。

现有自定义check_with、子类规则、coercers/default_setters、注册表、错误树和handler均可作为替代，未计成缺失功能。新提案明确范围，包括条件／比较、有限数、可移植schema、预算、批处理、解释与CLI；互操作导出尚未编写，未声称已通过另一个validator验收。上游issue只提供线索，不代表维护者承诺。

## 证据与重跑

本地忽略证据根 `.deploy/github-100-research/core-utils/cerberus/`；源码、venv和日志不进入正式项目快照，跨机器需重建。

```bash
git clone https://github.com/pyeve/cerberus.git <checkout>
git -C <checkout> checkout --detach 83f5dada76aa3179ef21b677a7f4235bf20c1566
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_baseline.py baseline .deploy/github-100-research/core-utils/cerberus --tests cerberus/tests
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/core-utils/cerberus
```

`repository.json`／`revision.txt`／`issues.json`／`source/LICENSE`保存来源和许可；`installation*.json`／`install.log`／`requirements-frozen.txt`／`size.json`保存依赖与成本；`baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`保存原生结果；`observe.py`／`observations*.log`／`observations-result.json`保存20项对照、实际业务与清理。路线和复核在`roadmap-20.json`／`review-result.json`／`evidence-sha256.json`，执行脚本副本已保存。

当前verifier仍只支持旧app.py行协议，研究完成不能称平台原生适配、模型完成或生产上线。未修改上游源码、产品、正式库或账号数据，未提交、推送、部署或向上游发消息，未执行真实模型评测。
