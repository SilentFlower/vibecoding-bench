# 执行计划

1. 核对 `Accounts.vue`、`ProxyPicker.vue`、Rust 授权请求和 `AgyAuthManager` 的实体及请求类型。
2. 完成候选线路在私有授权请求、状态文件、结果及原成功事务的正向传递，核对已提交结果的幂等验证与代理目录引用。覆盖账号旧代理、所选目录修订、直连、取消和节点迁移占用。
3. 更新 Vue 入口并复用当前线路的脱敏投影，联动现有授权流程。
4. 执行 `npm --prefix apps/web run build`、Rust 管理授权和凭据聚焦测试、编排授权测试，以及 `verify_agy_accounts_ui.py` 和 `verify_agy_accounts_api.py` 所属场景。使用合成代理验证真实授权数据流与失败后原配置，核对 `git diff --check`。
