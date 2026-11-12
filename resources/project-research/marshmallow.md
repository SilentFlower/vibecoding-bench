# 真实 GitHub 项目审查：Marshmallow

研究日期：2026-10-21。来源、固定源码、原生基线、真实JSON交换与 [二十步路线](./marshmallow-roadmap-20.md)研究完成；尚未实施路线、冻结新增验收或接入正式库。

## 来源与成本

官方 [marshmallow-code/marshmallow](https://github.com/marshmallow-code/marshmallow)，完整提交 [b762ea2d59ca52fe5df76b90de14bed7e5ec5607](https://github.com/marshmallow-code/marshmallow/tree/b762ea2d59ca52fe5df76b90de14bed7e5ec5607)，实际4.3.1。MIT，保留Steven Loria及contributors的LICENSE；Python≥3.10，3.11以下有两个backport依赖，本轮3.12核心零外部运行依赖，无服务。

103个跟踪文件、1,150,227字节，产品Python5,051行。按上游tests组另装pytest/simplejson，精确版本冻结；安装10.681秒，独立venv51,127,719字节，含测试工具，耗时受网络缓存影响。

## 原生结构与基线

SchemaMeta收集字段与钩子，SchemaOpts管理Meta配置；Schema做输入映射、字段处理、schema校验与聚合；Field支持pre_load→类型转换→validate→post_load；Nested/List/Tuple组合字段，ErrorStore与ValidationError保存错误，experimental.Context提供当前单通道上下文。已读取相关真实定义、类型字段、时间工具和验证器，保留原工程。

完整 `pytest tests` **1,192通过、0失败／错误／跳过**；沿用pyproject对mypy静态样例的norecursedirs，不把其当运行测试。测试2.806秒、容器全程4.429秒、峰值RSS59,348KiB，256MiB未OOM。未跑mypy/pre-commit、Sphinx、performance/benchmark或跨Python/平台矩阵。

基线与观察均用V3镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，UID/GID1000、无网络、只读根／源码／依赖、移除capabilities、禁止提权、256MiB无额外swap、PID128。HOME为临时空目录，无账号或真实配置挂载，容器已删除核对。

## 真实使用与路线证据

真实临时JSON订单qty='3'通过OrderSchema.load变整数并补中文地区，schema.dumps写文件、标准库JSON独立读回；qty=0反例含正确字段错误。导入确认是固定`/source/src/marshmallow`。

四项原版问题已复现：Email接受末标签首尾连字符；Date返回带时间的datetime；timestamp把纪元前日期写为负数后自己拒绝读取；unknown=INCLUDE覆盖已转换的data_key内部目标。第四项必须明确名称冲突的新失败政策和迁移影响，不能宣称无兼容变化。

另16项增强依据实际字段／Schema／钩子／上下文签名与使用场景。现有Field pre_load/post_load、Context、from_dict、only/exclude、partial、unknown、定制Field和错误kwargs均未重新计数。dump不验证、单通道Context与required/default当前限制按增强处理；新接口不是已实现能力或维护者承诺。

## 证据与重跑

本地忽略证据根 `.deploy/github-100-research/core-utils/marshmallow/`；源码、依赖和日志不进入正式内容快照，跨机器重新准备。

```bash
git clone https://github.com/marshmallow-code/marshmallow.git <checkout>
git -C <checkout> checkout --detach b762ea2d59ca52fe5df76b90de14bed7e5ec5607
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_baseline.py baseline .deploy/github-100-research/core-utils/marshmallow --tests tests
.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/core-utils/marshmallow
```

`repository.json`／`revision.txt`／`issues.json`／`source/LICENSE`保存来源；`installation*.json`／`install.log`／`size.json`／`requirements-frozen.txt`保存成本；`baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`保存原生计数；`observe.py`／`observations*.log`／`observations-result.json`保存20项观察和文件场景；`roadmap-20.json`／`review-result.json`／`evidence-sha256.json`保存路线与摘要，实际执行脚本副本已保存。

当前verifier只支持旧app.py行协议，原生适配、候选加载的冻结验收和每步预算仍待后续。本轮未修改上游源码、产品、正式库或账号数据，未提交、推送、部署或向上游发消息，未执行真实模型评测。
