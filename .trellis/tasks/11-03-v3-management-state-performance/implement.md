# 实施与验证

- [x] 固化根因及受影响调用链，收敛PRD并展示Brief后启动。
- [x] 完成只读快照准入、重复状态工作削减及相关接口边界测试。
- [x] 完成管理HTTP连接池与有限JSON读取超时，覆盖SSE/长操作不变。
- [x] Python定向业务回归及必要完整集合；Rust涉及src时完整cargo test（4线程）和fmt；前端如改动则实际build，diff检查。
- [x] Check-All、最小Spec、精确Git提交推送及进行中任务记录。
- [ ] 核验最终CI镜像并按US流程部署，保留活动任务及数据身份；只读验收与采样。
- [ ] 磁盘处理后置：用户已要求“等会再做”，当前不继续盘点或清理；待其恢复后执行既有定向回收。
- [ ] 两个任务按真实验收分别写progress完成态与Close，推送精确记录。

## 当前运行证据

只读盘点与采样保存在gitignored `.deploy/v3-latency-hot-41563822763/`，不提交任何生产响应正文或凭据。原批次切换因CLI执行证明在assert_idle阶段拒绝，未执行停止服务操作；当前生产版本保持原样。

Python扩大回归497项中496通过；唯一失败为原有test_proof_revoked_during_terminal_setup_closes_the_new_terminal仍期望公开原始异常文案，当前既有启动错误脱敏已改为结构化startup_unknown。在HEAD版projects.py的独立临时导入上复现同一失败；保留拒绝、baseline未发布和新终端收口的断言，并改核现有结构化错误，不修改执行路径。

## 最终本地验证

- `.venv/bin/python` 执行 test_projects*、test_quota*、test_warmup*、test_account*、test_pi_owners.py：最终497通过（102.700s），无跳过。
- cc2api `cargo test --locked -- --test-threads=4`：825通过，4个既有外部条件用例忽略；最后补读成功认证小响应以归还连接后，`cargo test --locked --lib management_ -- --test-threads=4` 4通过，覆盖最终模块。
- Python语法编译、`cargo fmt --package claude-code-gateway -- --check`、父/子仓`git diff --check`均通过；本轮无前端代码改动。
- 并发用例证明页面不等额度消费锁，执行锁忙时返回不可放行的未知状态；严格执行仍等待锁并消费新事实。真实SQLite夹具验证卡片字段一致、目录仅在请求内复用、下一请求重新读取。
- 真实本地TCP夹具证明管理客户端两次复用同一连接、无默认凭据；有限状态GET才使用10秒期限，会话验证/连接5秒，SSE、WS、长写操作不加状态期限。

## 提交阶段

Check-All full三维通过，无CHK/FBK/DOC；只读准入、请求内复用及管理桥期限合同已写入project-iterations规范。网关与父仓业务代码均已精确提交推送，待最终CI和生产验收后完成两个任务。磁盘处理继续后置。
