# 实施与验证

1. 跟踪 services/orchestrator/agy_auth.py、Gateway agy_account.rs、agy_credentials.rs、handler/router.rs 与账号管理页面，核对登录会话 ID 的生成和取锁顺序。
2. 合成续期在凭据落盘后注入首次核验失败，验证重启、空闲账号、幂等提交、模型目录失败、双账号、永久错误及过期路径。
3. 并发生成授权链接和刷新，覆盖工具端取消、迟到回包、进程重启及起链失败。
4. 在仓库根用 PYTHONPATH=services/orchestrator 运行 python -m unittest test_agy_auth test_agy_auth_api；Gateway 运行 cargo test --locked --lib agy；管理 API 和页面在隔离环境验证。
