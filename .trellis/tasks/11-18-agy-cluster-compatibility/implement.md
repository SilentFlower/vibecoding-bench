# 兼容集成执行计划

## 1. 开工与证据

- [x] 完成 Brief 评审，激活本任务并进入 implement 路由。
- [x] 按 trellis-before-dev 加载相关规范与类型定义，读取两侧涉及的结构、方法和测试。
- [x] 核对来源 HEAD、目标 SHA、当前工作区状态及已有集成状态；当前仅有本任务规划文件。
- [x] 创建 `merge/agy-into-flower2api`，以冻结集群目标为基线合并AGY来源，完整保存 conflict stages 和路径清单。

## 2. 冲突与语义集成

- [x] 解决 20 个冲突文件；按三方差异保留两侧功能。
- [x] bench 沿目标 1—4 追加 AGY 5，检查并更新所有步骤 ID、前驱、断言、夹具和证据工具引用。
- [x] 合并唯一迁移来源表及升级器源码清单；保留摘要、来源和符号链接保护。
- [x] 保留运行时平台版本读取与构建缓存，接入 AGY 认证制品输入。
- [x] 合并维护代次与远程节点路由，补齐资源收口。
- [x] 合并 Rust/TypeScript 诊断字段和所有构造点，核对 Vue 两套环境和详情交互。
- [x] 对 37 个共同变更路径逐项复核自动合并结果，关注 shadow assignment、路由顺序、凭据门禁及启动生命周期。

## 3. 验证

- [x] Git：检查未合并索引项、冲突标记、diff 空白错误及冻结祖先关系；产品树内容与集群基线比较。
- [x] Python：数据库迁移、定义扫描、source_layout、manage/system_release、升级器相关测试；AGY 环境/凭据/采集/维护与集群 Node/transport/owner/管理入口相关测试。
- [x] 数据库：空库、冻结集群 bench4/gateway4 源升级、原记录保持、幂等、失败回滚、旧集群程序读写；分叉 AGY 2 和坏台账受控拒绝且数据库保持。
- [x] Rust：`cargo fmt --check --manifest-path services/gateway/Cargo.toml` 与 `cargo test --locked --manifest-path services/gateway/Cargo.toml`；按实际测试入口核对环境所需依赖。
- [x] Web：读取 package.json，运行项目规定的类型检查和生产构建；用既有合成验证工具覆盖本地管理 API、SQLite 及页面中的组合字段，必要时扩展已有探针。
- [x] 沿既有验证程序复用精确源码一致的证据；对本轮变更及原有证据失效部分重新执行，记录实际通过/失败/阻断。

## 4. 检查和交付

- [x] 记录 `research/validation.md`，逐条映射 AC、实际命令、源码身份、结果及限制。
- [x] 通过 trellis-route(check) 执行 Check-All，并按当前报告处理问题和复检。
- [x] 进入 Spec 评估，更新 bench5 与集群/AGY 共存合同及必要防回归约定。
- [x] 准备含双父合并要求、精确文件范围、提交信息、目标分支与远端的 Git 计划；沿 confirmation 协议评审。
- [x] 提交/推送后记录确定性任务进度和 Close。Flower2API 目标分支的实际推进按其精确授权范围执行。

## 风险与范围恢复

- bench 历史步骤逐项与冻结目标核对；出现语义漂移先恢复该步骤定义，再通过新增步骤完成需要的变化。
- 原 AGY 开发版本 2 台账保持受控拒绝。发现需要迁移的真实此类库时，单独展示兼容范围变化并取得该部分决定。
- 真实生产变更、真实凭据或模型调用需求沿独立授权边界处理。
- 本任务是一个共同验收的集成结果，采用单任务。执行默认为 inline；按 route 的实际结果继续。
