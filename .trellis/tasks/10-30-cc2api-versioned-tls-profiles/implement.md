# TLS 版本绑定实施计划

1. [x] 核对既有TLS、HTTP选择、内部传输和用户默认兜底决定。
2. [x] 收敛PRD/design，展示完整Brief并进入任务实施路由。
3. [x] 增加TLS ID注册/版本绑定/默认解析，改造按代理和画像隔离的工厂及测试。
4. [x] 冻结网关请求选择并贯通直连、sender、count_tokens及重试；补兼容/拒绝/实际传输测试。
5. [x] 同步账号或版本相关辅助调用，完整cargo test与格式、diff、敏感内容检查。
6. [x] Check-All、协议Spec、精确子仓/父仓推送。
7. [x] 匹配Actions和实际镜像握手验证、us空闲部署、健康/身份/计划保持及镜像收尾。
8. [x] 记录结果、独立任务记录推送并完成Close。

## 范围与检查

- 子仓tlsfp、version_profile、gateway、runtime_transport及相关OAuth/Hello/telemetry调用和现有tests；必要的现有内部传输测试/夹具。
- 主仓当前任务、权威协议Spec和gitlink；部署程序保存在忽略目录。保留初始334项无关dirty，不修改其他任务。
- 定向cargo test tlsfp、version_profile、runtime_transport及网关相关回归；cargo fmt --check和完整cargo test -- --test-threads=4。Python/前端无代码变化时复用同批源码摘要验收。
- 代码与SHA未变化的通过证据直接复用；新画像必须实际采集，本轮仅有测试专用第二画像，不添加虚假生产选项。
- 回退使用前一已验收联合清单和两镜像，不重放未知输入、不覆盖凭据或资源参数；部署不自动操作独立cc2api旧服务。
