# 实施与验证

## 实施顺序

1. 开工后加载网关、编排和部署规范。核对 `gemini.rs`、`gemini_contract.py` 的现有调用和在研变更，保留之前已受理续轮重读与请求诊断。
2. Rust 网关在原工具轮匹配中统一两步配对。初步验证先构造 `A、B、B、B` 和无 ID `B、B、B、A`，再检查混合 ID、完整性、身份及兼容旧输入。
3. Python 原生续轮和历史导入共用整轮配对。多段历史结果收齐后生成现有 Cortex 步骤，按原调用编号校验合成结果。
4. 更新现有 `verify_agy_native_loopback.py --parallel-tools` 的合成验证。用一个包含多个工具名及同名调用的工具轮复现重排，核对四个结果实际出站、各一次续轮和后续接续。运行已有重读和权限验证。
5. 按 Check-All 范围核对实际 diff、涉及源码映像和版本部署路线，随后更新权威配对合同。

## 验证入口

- `cd services/gateway && cargo test --locked --lib service::gemini`。沿上次的并发 4 全量重跑，逐项核对网关会话、权限和重读。
- `PYTHONPATH=services/orchestrator:deploy/flower2api python3 -m unittest discover -s services/orchestrator -p test_agy_runtime.py`，覆盖原生历史和待回填调用。依赖隔离按编排器规范。
- `python3 deploy/flower2api/verify_agy_gemini.py --image <当前隔离测试镜像>` 和 `python3 deploy/flower2api/verify_agy_native_loopback.py --image <当前隔离测试镜像> --parallel-tools`。本地使用合成凭据、模型回环和测试数据库。

## 交付衔接

- 按任务精确范围提交。核对远端候选，按项目 SOP 预览具体发行，用手动签名发布构建同批两种镜像并查验旧库演练。
- 对 US 执行既有系统更新检查、准备和安装，使用当前 revision 与目标签名摘要。等待操作收口及实际目标账号的后台发送器更新完成，再提供目标发行身份和新轮次复测入口。读取新请求证据确认表现。
- 现网维护、安装和回退使用同一受信状态机。失败恢复遵循实际操作阶段及原回执。
