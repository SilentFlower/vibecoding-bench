# 反重力镜像验收复用实施计划

1. 在 `.github/workflows/v3-release.yml` 将 AGY 镜像实测放入原完整构建条件。构建侧保留实际探针和导出顺序。
2. 更新 `deploy/flower2api/test_system_workflow.py` 验证可信复用、显式完整构建及签名兼容门禁。用 `test_system_candidate_build.py` 覆盖候选来源和原 attempt 反重力验收结果，补齐已有回归没有覆盖的失败三态。补齐真实 Docker 换批夹具缺失的 AGY 能力及账号源摘要标签，以覆盖当前清单合同。
3. 同步 `deploy/flower2api/SYSTEM-UPDATES.md` 和 `.trellis/spec/platform/deploy/platform-online-update.md` 的受信候选验收合同。
4. 执行 `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_system_workflow test_system_candidate_build test_agy_images test_publication`。在可用的 Docker 上以 `FLOWER2API_CANDIDATE_DOCKER=1` 验证镜像文件层与配置同一性。核对 YAML、Bash 语法和发布范围。
5. 下次正式发布核对受信候选采用日志、重复验收状态、兼容演练与签发结果，按历史实测与新实测对比耗时。这一验证随既有发版流程执行。
