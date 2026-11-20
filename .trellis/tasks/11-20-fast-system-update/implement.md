# 实施顺序与验证

1. 在本地复现悬挂推理、工具等待和慢节点。记录从发布维护门禁到首个可用请求的基线。核对现有节点准入入口、网关活动与发送器的取消和终止证明。
2. 增加操作绑定的推理取消与回执，接入 CC 流、AGY 流和待回填工具轮。使用假上游与真实本地发送器验证关断、许可归还、同一操作重复请求及正常 EOF 竞态。凭据操作保持原事务收尾。
3. 将升级执行器切换为预检后触发取消、校验实际终止并进入中央短切换。兼容版本复用原账号容器，真实迁移沿同一快照及恢复链。校验首次接入和固定源码包在仓库外的导入与恢复。
4. 切开节点独立换版与中央验收。复用持久同步作业。核对兼容、慢速、失联、失败、回滚和跨重启续接。确认其他节点和本机可持续处理请求。更新页显示中央已恢复接单，节点页显示单独进度和恢复动作。
5. 运行 Rust 网关与发送器定向测试、编排和宿主更新测试、系统更新浏览器验收。用隔离 Docker 加两库迁移历史和一个慢节点运行完整升级，再执行一次中断恢复和回退。提交前用对照表记录各阶段耗时、控制端状态、资源归还、请求结果和节点归属。

## 验证入口

- `cargo test --manifest-path services/gateway/Cargo.toml system_update`
- `cargo test --manifest-path services/gateway/Cargo.toml agy`
- `python3 -m unittest discover -s deploy/flower2api -p 'test_system_*.py'`
- `PYTHONPATH=services/orchestrator python3 -m unittest discover -s services/orchestrator -p 'test_system_update*.py'`
- `python3 deploy/flower2api/verify_system_update_browser.py --output .deploy/fast-system-update/browser`
- 真实数据库、节点和故障恢复沿系统更新验证入口和仓库已有集群集成测试扩展已确认场景。
