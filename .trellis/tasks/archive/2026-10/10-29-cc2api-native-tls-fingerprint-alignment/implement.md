# TLS画像实施计划

## 步骤

1. [x] 读取现有模板、craftls、客户端工厂和规范；盘点58条HTTP关联握手并完成原版293直接本地无MITM对照。
2. [x] 完成三件套、上下文与完整Brief，沿本会话无需重复确认的连续交付授权启动；通过trellis-route选择实施位置。
3. [x] 更新统一293主请求cipher／有序扩展／算法／组／key_share，保留真实恢复与Cookie，去掉fake组并补必要peer校验。
4. [x] 修正显式key_share模板受缓存hint改变的问题，保留无覆盖及HRR机制。
5. [x] 增加脱敏固定基线、独立wire解析、真实TLS1.2／1.3／恢复／HRR与混合交换测试；跑现有代理／取消／证书回归及完整cargo test、cargo fmt --check。
6. [x] Check-All、权威Spec更新，展示精确多仓Push计划后按既有授权执行。
7. [x] 匹配Actions、同批镜像源码和实握手验收，按us SOP排空切换、健康与持久身份／计划保留，完成旧镜像清单收尾。
8. [x] 记录实际交付与未覆盖条件，独立提交任务记录并完成Close。

## 文件范围

- `cc2api/src/tlsfp/tlsfp.rs`：统一模板、Provider、真实混合组与测试。
- `cc2api/craftls/rustls/src/craft/mod.rs`、`client/tls13.rs`：显式模板的初始组选择，内部窄改。
- `cc2api/tests/fixtures/`：独立解析与本地TLS夹具／脱敏293目标。
- 必要的现有TLS测试集成；主仓任务记录、协议spec、gitlink与私有部署操作。无UI或数据库改动。

## 验证与回退

- 定向：`cargo test --lib tlsfp`、`cargo test --lib local_https`；独立Python解析固定fixture与实际Rust序列化，验证全部字段而非只JA3。
- 最终：`cargo fmt --check`、`cargo test`、`git diff --check` 与秘密排除。仅复用源hash未变且实际已通过的结果。
- 线上：真实batch／parent／child／镜像hash、临时本地TLS服务器（无正式模型探针）、鉴权与双空间API、数据库只读完整性、身份／会话／计划与其它服务保持；新TLS采样不取代无MITM对照。
- 操作前确认没有未知输入、API／CLI占用或控制器工作；等待健康工作自然收口。失败保留原批次／证据，不盲重放输入、不清理其它任务、不覆盖凭据。
