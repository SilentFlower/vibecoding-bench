# attrs 验收合同与反馈设计

## 已确认合同与误判

冻结目标只承诺 `validate_all(instance, *, raise_errors=False)` 的聚合功能，没有规定非 bool 参数必须在调用验证器前拒绝。旧观察器用 raise_errors=1 同时检查异常类型和第二次调用后的 seen，导致符合公开功能的候选落入外层通用 business=false。

## 未来内容与已有冻结目标

先封存精确旧字节及 SHA256；未来业务观察器使用修正版。ProjectVerifier 在现有 schema/weighted 链后增加 attrs 专属适配，只有 script、args、python_paths、严格 expected 和已确认原始 SHA256 一致时创建临时可信执行副本。修正版 SHA256 同样白名单化，以支持安全诊断协议。原项目 verification 挂载只读，旧冻结合同与源码不改写。

未知来源不猜测替换；继续按严格协议报告失败或原有环境错误，不能把任意同名脚本当作可信修正版。审计中记录适配名称、范围、原始及实际来源摘要。

## 独立业务矩阵

按公开合同将检查组织为独立事实：声明顺序/真实字段名和 Attribute、保留原始异常对象、每字段调用一次及 and_/or_/optional/deep 既有语义、禁用开关、raise_errors=True 的 issues tuple、Exception 与 BaseException 边界、字段不改变。检查器为不同调用独立准备输入和计数，避免自己的测试动作污染一次验证判断。移除严格 bool 边界，不要求候选新增接口或修改公开需求。

## 结果与安全反馈

原 expected 仍是严格的 candidate_import/business 两个布尔字段。可信 attrs 观察器额外输出反馈枚举，ProjectVerifier 在精确来源核对后检查：对象形状、字段个数、布尔类型、枚举白名单及重复/数量限制；拆出 codes 后按既有 expected 比较。错误源码归属、未知枚举和额外任意字段不能通过。

ProjectsVerification 将枚举映射为公开合同对应的行为说明，继续复用 _public_facts 的八项和 12 KiB 边界；检查/结果状态分开，私有异常正文和断言源码不进入 Pi。原生/历史回归失败仍保留其已核实阶段事实，不用当前业务反馈覆盖历史错误。

## 验证边界

把线上精确候选复制到本地隔离位置复现，通过修正版业务观察器和原六条公开回归；构造故意破坏顺序、身份、组合语义、禁用、聚合和异常边界的反例。验证业务矩阵通过不代表完整项目通过，原生回归、已通过能力和必要语义审查照常执行。deferred、冷却和旧报告无需迁移或重写。

## 受信程序分发

`orchestrator/project_attrs_observer.py` 是控制端受信业务矩阵，未来内容中的同名目标观察器保存相同字节。适配器只从自身同目录读取受信程序并核对固定摘要，不从候选或旧内容取修正版；测试要求两份分发字节一致。控制镜像现有 orchestrator/*.py 与内容 COPY 均覆盖它们。未知 attrs 来源返回环境错误；结果类型、键集合及反馈类别与 business 布尔的一致性在公开投影前校验。
