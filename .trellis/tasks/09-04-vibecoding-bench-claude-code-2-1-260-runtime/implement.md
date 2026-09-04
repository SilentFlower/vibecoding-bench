# 实施计划

## 1. 默认版本同步

- [x] 将 worker Dockerfile、entrypoint shell/Node fallback、orchestrator 默认值、两份
      Compose、`.env.example`、WebUI、README 和测试更新到 2.1.260。
- [x] 核对普通、批量、抓包、continue、quota、OAuth refresh 和 login worker 的版本
      传递路径。

## 2. run 版本快照

- [x] 在 `_SCHEMA` 和 `init_db()` 中增加 `runs.claude_code_version`。
- [x] 提取小范围版本解析/回退辅助函数，保持现有校验错误语义。
- [x] 更新普通、批量、养号和抓包 run INSERT，原子保存版本快照。
- [x] 把快照放入 scheduler task payload，`Runner.start_run()` 优先使用快照。
- [x] `continue_run_start()` 对历史 NULL 快照执行一次兼容补写；
      `Runner.start_continue()` 使用 run 快照。
- [x] 在 run/capture API 中暴露快照。

## 3. 测试

- [x] 更新默认 2.1.260 断言和所有 worker 创建路径测试。
- [x] 增加新旧 SQLite schema、全部 run 创建入口和排队版本稳定性测试。
- [x] 增加抓包 2.1.260、全局改 2.1.257 后 continue 仍为 2.1.260 的回归测试。
- [x] 增加历史 NULL 快照回退补写和新 run 使用新全局版本测试。
- [x] 运行 `python3 -m unittest orchestrator.test_main`。
- [x] 运行两份 `docker compose ... config --quiet` 和默认值 `rg` 审计。
- [x] 执行 Check-All。

## 4. 发布与生产验收

- [ ] 提交并推送可构建代码，等待三镜像同 SHA tag 与 `latest` 发布成功。
- [ ] 备份生产 DB、页面版本覆盖和旧镜像信息。
- [ ] pull 并 force recreate bench 服务，确认所有生产默认值为 2.1.260。
- [ ] 创建生产抓包 run，核验 API 快照、worker `claude --version` 和 continue 版本稳定性。
- [ ] 记录后续抓包任务需要的环境与回滚证据。
