# Cachetools真实场景任务设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](cachetools-admission.json)为准。

## 固定来源与已读实现

上游 `tkem/cachetools@6f23e2a7b75a42d30cb9d890ab3ca4059ee01bfd`，MIT许可，完整44个Git文件已按blob核对并准备在隔离草稿。实际读取Cache大小账本、TTLCache及计时器、cached／cachedmethod、keys与descriptor相关定义；不把自定义key、TTL、info和条件锁等既有能力当新功能。

当前目标镜像Python3.12.15的原版校准为366主项与8子测试通过，完整节点合同位于 `.deploy/project-catalog-hundred/stage-01/calibration/attempt-002/cachetools/evidence/native-contract.json`。该结果只证明原版基线，不代表下述新任务已完成。

## 场景与九项独立任务

| 场景 | 任务 | 类型 | 真实用户问题与合法结果 | 公开材料／独立事实 |
| --- | --- | --- | --- | --- |
| CT-S01 配置文件缓存 | CT-U01 | 理解 | 为什么第二次读取不访问文件，TTL边界何时重新读取 | 给定真实JSON文件读取器与受控时钟；实际读取次数和边界前后数据 |
| CT-S01 | CT-C01 | 咨询 | 文件改了但缓存没过期，是否是库缺陷、是否必须改库 | 给定更新日志；解释TTL缓存不监听文件、已有清除或key版本方案 |
| CT-S01 | CT-P01 | 方案 | 规划原子发布、验证、缓存失效与读取错误处理 | 业务发布要求；真实坏JSON不被缓存、既有失效机制可用 |
| CT-S02 缓存键与商品价格 | CT-D01 | 诊断 | 价格偶尔串值，但当前材料不足以归因 | 初始只有症状；请求实际两个函数、cache/key配置及调用序列后才披露；无材料入口可正常insufficient_information |
| CT-S02 | CT-C02 | 咨询 | 两个业务方法共享缓存时怎样隔离键而不改库 | 完整方法及既有keys公开；实际重现共用默认键与显式命名空间后的差异 |
| CT-S02 | CT-U02 | 理解 | 语义等价调用为什么有三次miss，typedkey解决什么 | 公开调用脚本；默认位置／关键字／默认值键不同，typed与归一化是不同问题 |
| CT-S03 类入口绑定 | CT-D02 | 诊断 | 同一cachedmethod经实例或位置参数可用，关键字receiver失败 | 完整最小复现及实际报错；从_Unbound调用与原函数receiver分析 |
| CT-S03 | CT-M01 | 修改 | 修复类访问的合法关键字receiver，保留全部原有效调用及拒绝边界 | 明确完整合同和复现；原版失败，参考与错误候选分别验证；真实上游完整回归 |
| CT-S04 可变值容量账本 | CT-C03 | 咨询 | list长大后currsize未变化，如何守住缓存预算 | 公开getsizeof=len样例；插入时计量、重新赋值重计和超限拒绝，不能声称自动追踪 |

共四场景／九任务，八项非修改、一项修改；数量来源于不同独立问题，不按二十步路线拆配额。每场景独立原版，requires均为空：默认顺序只是阅读／业务顺序，不宣称消费前置回答或代码。

## 材料与入口

CT-S01／S04只有normal入口。CT-S02提供normal、diagnose_only和unavailable；后两者只选D01，unavailable明确说明无法提供实际证据。D01的rubric在实际披露前不能出现隐藏价格、函数名或根因，不能以一般症状直接断言缓存键冲突。请求证据的正常澄清不增加业务尝试，分支不增加任务数。

CT-S03提供normal（D02、M01）、diagnose_only及modify_direct。修改首问和公开合同自足，不用先前诊断答案解锁；只授权 `library/src/cachetools/_descriptor.py` 与 `library/tests/test_cachedmethod.py`。公开复现和合同给出目标，候选看不到参考与私有测试。

## CT-M01边界与独立验收

- 对原函数允许位置或关键字传入的receiver，类访问以其真实参数名传入receiver时与原位置／实例调用等价；不能只硬编码self，亦不能将任意业务关键字当receiver。
- 原receiver为positional-only时仍拒绝其关键字形式；缺失receiver、重复位置／关键字receiver仍TypeError。保留多实例缓存隔离、info行为、原业务参数、既有descriptor／slots／super／classmethod兼容，不更改公开签名或全局设置。
- 参考必须交付有意义的公开回归，证明同一测试原版失败／参考通过；完整上游366主项／8子项回归独立冻结，候选新增测试不替代原集合。
- 私有业务直接调用真实装饰器的标准receiver、自定义receiver名、位置控制、缺失／重复和positional-only反例，不依赖修复算法或词法匹配。错误的硬编码receiver候选须被拒绝。

## 运行与语言

模型首问、材料说明及rubric英文，中文标题／目标；原始代码及中文商品值不翻译。非修改任务allowed_paths为空且不产生接受代码；D01仅语义评审，其余任务用实际程序事实加独立语义评审。精确离线依赖为pytest9.1.1及其四个固定依赖，业务256MiB／30秒、回归512MiB／180秒分别实测后才记准入。
