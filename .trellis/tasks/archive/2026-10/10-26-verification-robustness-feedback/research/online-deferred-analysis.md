# 线上待复验证据与现有机制

## 来源和范围

- 用户先要求统计、分类，再要求提高鲁棒性和真实通过率；本次修复建立在本会话已完成的只读调查上。
- 2026-10-26 21:05:31（北京时间）线上 us 环境：项目空间 3 项，工程养号空间 0 项，均属账号 10-23（account_id=8）、当前 cycle=1。
- 详情本地副本：`/tmp/vibebench-deferred-audit-vgew_i65/classification.md`、`reproduction.json`；原始线上快照为 `/tmp/vibebench-deferred-current-20261026.json`、`/tmp/vibebench-deferred-evidence-20261026.json`、`/tmp/vibebench-deferred-final-state-20261026.json`。
- 数据通过现有 `.deploy/pi-efficiency-rollout-20261026/remote.py` 连接入口读取，凭据仅由私有连接配置在进程内使用。数据库使用 `mode=ro` 和 `PRAGMA query_only=ON`，未启动模型、重新提交或改写线上状态。

## 三个目标

| 项目 | work_id | 最近不可变 submission_id | 原始观察器 SHA256 |
| --- | --- | --- | --- |
| attrs | 88e9bf9aa2ee4d9e8a2a076e823aa665 | c1c39e7a459542998c5b1e7eabeaa885 | 304a4403f8a037da3e6a5c4eb0d125678fb725fe69580c6ce479a878d5304461 |
| babel | 8f4ae955816a4fc5b80c8bb9f82091a3 | ad18d50a175d448e947e9a5ad583cecd | c9470d69d118400e7042fe6f7ccb702d9d6a0107f656d5b7d2de72e2bf8bfe99 |
| bibtexparser | cc768b6f845f4bfcb3df0592e6b6b63f | e8497c38c0ad4ac2ae363b9fe861f573 | 8d95cce3afe191108213fe59aadef3449522f4a75c2039448d78623e509881e2 |

- 候选路径：`/srv/vibebench-v3-us/bench/projects/submissions/<submission_id>/candidate`。attrs 冻结内容版本为 `89a8d8e0be4e901f2b9c7771c356dc0ade51cb9f45fd549284f842c25e7c6882`，另两项为 `beaa4b4d11d44a444f7a973c250de131f7ed2a9b5879e359d89f8420444fbb02`。
- 三个原业务观察器均已在取回副本中复现 `candidate_import=true,business=false`；冻结公开测试分别为 6、4、3 项，全部通过。
- attrs 原脚本在 `raise_errors=1` 上强制未公布的 TypeError，并复用实例重复调用后检查一次计数；已知修正版同份候选通过，`feedback_codes=[]`。线上受信观察器摘要与仓库 `project_attrs_observer.py` 一致，本任务不再重做该纠错。
- babel：`en;q=0, en-US;q=1, fr;q=0.1` 对 `['en_US','fr']` 返回 `en_US`，原脚本要求 `fr`。公开合同只明确通配符选择前的排除，未明确冲突时排除是否压过更具体偏好。质量、同权、通配符和空头部等其它诊断通过。
- bibtexparser：`' 001 - 009 '` 返回 `' 001--009 '`，原脚本要求 `'001--009'`。公开合同未明确首尾空白；原对象、数字文本、其它字段、元数据、幂等性和混合未知格式诊断均符合对应公开示例。
- 历史 9 次提交中，7 次业务观察器失败，2 次范围拒绝：attrs 改了未授权 `attr/__init__.py`，babel 混入 6 个原测试输出文件；最后候选已清理越界内容。冷却、范围豁免不属于本轮修复点。

## 已核对的运行条件

- 离线复现容器 Python 3.12.15，与线上冻结环境一致；所用本地 profile 的规范 JSON 摘要与线上冻结 profile 相同，文件原始 SHA 差异来自 JSON 序列化格式，不是内容差异。
- attrs profile 摘要：`8d290363b2a9e567b2b7cb06365a5b40f243f326dee706358a709658c7f898d0`。
- babel profile 摘要：`8c9d0409b9a353ab1920545afd9f883ab910395cde8c709d974a144deb6e69b6`。
- bibtexparser profile 摘要：`5f2e9aa237794e1b8fdf9f7abcd4241df3041e0c4b12012429ec9470499b0c61`。
- 每个离线轮子的 SHA256 均按 profile 校验；Docker 禁网，候选只读挂载。尚未在此调查中运行完整原生历史回归及语义验收。

## 代码与规范锚点

- `orchestrator/project_verifier.py:145`：现有 `_native_attrs_adapter`，精确来源、受信字节与临时入口复用点。
- `orchestrator/project_verifier.py:590`：现有受信 `feedback_codes` 的严格协议校验与 expected 比较。
- `orchestrator/projects_verification.py:201`：固定业务类别到中文公开事实的映射、八项限制与历史报告递归。
- `orchestrator/projects.py:860`：持久冷却与原会话保留；本次不改。
- `.trellis/spec/vibecoding-bench/backend/project-iterations.md:650`：验收反馈、来源保护、待复验与私有事实边界。
- `.trellis/tasks/10-26-attrs-verification-contract-feedback/brief.md`：已有 attrs 修正的范围、反例和验证约束。
