# 调度与可视化验证记录

## 范围与基线

- 父仓：v3，基线 68950fd0b512ce6ca5f62e46420454e9fdfacd16。
- cc2api：基线 046c0a28a518337ed2c9745c4193fea47904cb1f；验证针对本任务工作区实现，尚未提交。
- 参考仓只读，未修改。未部署、未接触生产数据库或配置，未使用真实账号／模型压测。
- 所有调度和 UI 数据来自临时数据库、本地模拟 runtime／sender 或浏览器合成管理响应。

## 实际执行结果

| 命令／环境 | 结果 | 证据 |
| --- | --- | --- |
| cc2api：cargo fmt --check | 退出 0 | fmt-check.log（成功无输出） |
| cc2api：cargo test --locked | 811 通过、0 失败、4 ignored | backend-tests.log，含完整测试终态 |
| 新调度 SQLite／服务行为（全量包含） | 16 通过、PG 默认 ignored | tests/v3_scheduling_test.rs |
| 本机独立 PostgreSQL：postgres_check.py | 指定 ignored 合同 1 通过；容器已清理 | postgres-check.log、postgres-check-result.json |
| cc2api/web：npm run build | TypeScript／Vite 构建退出 0 | frontend-build.log；产物 web/dist |
| 本地 Vite + Playwright：ui_check.py | 9 组交互通过，页面异常 0，意外／模型请求 0 | ui-check-result.json、ui-account-scheduling.png |
| 离线方案图 HTML 截图 | 生成成功，与 HTML 同步 | doc/visualize/v3-scheduling-observability.html 及同名 PNG |

全量中的 4 个 ignored 场景为调度、诊断存储、额度迁移、版本设置的专用 PostgreSQL 验证。本轮只单独实际执行了调度 PG 合同；另外 3 个既有场景不报告为已执行。
依赖 vendor reqwest 等既有编译告警仍存在；本轮没有抑制这些告警。

## 关键行为证据

- 同会话并发 CAS 仅一个账号认领；失败事务回滚发送预算。不同 Token 隔离，无 SID 不造绑定；持续老会话保持原账号，新会话可选即时容量。
- SQLite／PG 同合同覆盖迁移、发送间隔、版本续租、分页、清理和账号原子删除；发送状态持久化可跨服务重建恢复。
- 发送测试覆盖跨分钟、RPM 改动、重启、不积攒许可；cold_environment_ready_cohort_still_submits_smoothly 通过内部 HTTP 记录，冷环境 4 请求同批就绪仍间隔提交，压缩 SSE 原始字节保持。
- v3_real_http_disconnect_releases_waiting_request 与 v3_real_http_stream_disconnect_releases_execution 验证真实 HTTP 断连回收；取消发送 FIFO 不生成提交事件。
- v3_pacing_timeout_preserves_binding_and_has_no_attempt 验证本地 429／Retry-After、保留绑定及诊断 attempt_count=0；存储关闭返回 503 且不产生发送。
- v3_sse_error_feedback_uses_existing_body_observation 验证 HTTP 200 内 SSE 错误不误算成功；真实失败降低健康，用户输入错误不虚奖延迟。
- 管理路由验证管理员鉴权、分页上限、参数校验和读取不续租／不扣许可；设置验证合并、非法值拒绝、热刷新与字符串值。
- 可视化验证总览／详情、单会话多请求、分页／摘要筛选、陈旧快照、隐藏／关闭暂停刷新、数字设置字符串保存。浏览器脚本阻断所有模型请求，页面为合成验收账号。
- 现有权限、额度、优先级、缓存、签名／认证重试、身份归属、原始传输字节等回归由全量测试覆盖；不把既有非 v3 测试等同于所有新 v3 组合已实际执行。

## 使用边界

- 节奏计时边界为 Gateway 向 sender 发起提交；不包含独立 CLI／项目／养号流量，不保证供应商最终接收间隔。
- 最近时间轴是有界进程内观测，重启有历史缺口；持久绑定与发送许可状态独立保存。
- 这里只验证本地软件行为，不推断账号停用根因，也不宣称某个 RPM 能保证官方账号安全或每次缓存命中。
- 本轮未做生产发布或线上验收；后续若部署，应单独按项目发布 SOP 执行。

## 授权修复后的定向证据

- CHK-001：sqlite_write_lock_and_held_permit_cannot_bank_send_time 验证写锁 350ms 后才认领；持有许可期间后续请求不能抢跑，提交后仍至少间隔 200ms。SQLite／PG 的原子合同同时断言完整 UTC 毫秒，整数文本投影避免 Any 的 i32 截断。
- CHK-002：waiting_requests_reload_current_rpm_without_resetting_deadline 及 PG 合同验证 300→60、1→300 两次变化；队首不使用旧快照 RPM，配置更新及时唤醒，截止时间不变。
- CHK-003：capacity_reason_matches_pending_work_and_wait_budget 区分 wait_budget、pending_submissions 和 ready；浏览器同时验证对应中文原因。
- CHK-004：浏览器从第 3 页缩至 1 条时仅额外回读一次第一页；继续归零时留在第一页，按钮和内容一致。
- 修复期间误用 cargo fmt --all 触及依赖排版，已按干净基线只撤回该命令产生的 craftls/rustls 格式变化；最终依赖目录没有变更，按项目 cargo fmt --check 和完整测试重新验证。
