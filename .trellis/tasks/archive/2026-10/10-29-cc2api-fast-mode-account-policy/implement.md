# Fast 账号策略实施计划

## 开工前

- [x] 固化用户接受的禁止回落／允许透传行为，核对现有账号字段、两种客户端和三条正文分支。
- [x] 核对 count_tokens 独立入口、重试公共正文、既有 CCH 刷新与压缩编码合同。
- [x] 完整展示从三件套生成的 Brief，并取得首次开工确认；此前不运行 task.py start、不修改产品代码。
- [x] 取得确认后启动本任务，按 trellis-route 选择实现方式，并加载 trellis-before-dev；没有新增用户决定时不重复评审已确认范围。

## 实现顺序

1. **共享策略与单测**：在 rewriter 使用现有 JSON 类型实现精确根字段过滤，账号允许或无删除时保留原字节；复用已有根级 CCH 刷新能力，覆盖顺序稳定、完整 token、已有／无／歧义 CCH、280/293 与 billing 透传。
2. **Messages 接入**：在账号循环的正文分支汇合处执行策略，最终 header 使用新正文；保持原请求输入不可变，覆盖普通、identity-only 和 attribution 分支。
3. **count_tokens 接入**：账号循环按公共原文派生各账号正文；401 复用当前账号正文，换号重新派生，保留专用 beta 和独立发送语义。
4. **实际 Gateway 回归**：复用现有 service、接收器和压缩测试助手，检查允许／禁止、有／无 beta、两客户端及 stream 模式、特殊分支、换号与认证恢复。用真实 TCP 核对修改后的 CE／CL 与最终字节。
5. **注释与 UI**：更新账号字段注释、Accounts 提示，维持开关默认值、回填、保存和 API 字段不变。
6. **规范同步与检查**：更新 Fast 场景与后台状态分类有限例外；保持其它协议和请求压缩合同。完成 Check-All 后按规范评估、精确 Git 范围计划继续，不提前部署或提交未评审范围。

## 验证命令

在 `cc2api/` 执行：

```bash
cargo fmt --check
cargo test fast_mode
cargo test cch
cargo test
git diff --check
```

- 新增 Gateway 用例应以可辨识的 fast_mode 名称覆盖本任务矩阵；没有覆盖到的相关旧回归可由本次完整 cargo test 复用，不机械重跑。
- 协议原有 bench 创建默认禁止合同使用既有测试验证，在父仓执行：

```bash
.venv/bin/python -m unittest discover -s orchestrator -p 'test_main.py' -k test_sync_creates_cc2api_account_with_fast_mode_disabled
```

在 `cc2api/web/` 执行：

```bash
npm run build
```

- 写入实际执行结果与限制，不把规划中命令记录为已通过；本轮未新增 DB 行为，不为同一实现补镜像式测试。

## 所有权与回滚

- 产品范围：`cc2api/src/service/rewriter.rs`、`cc2api/src/service/gateway.rs`、`cc2api/src/model/account.rs`、`cc2api/web/src/components/Accounts.vue`。
- 父仓范围：本任务文件、Fast 协议场景及后台状态分类规范的对应条目，完成后核对实际 gitlink。
- 保留父仓预存的协议研究文档改动、338 项未跟踪基线与其它任务材料；不清理或纳入本任务。
- 回滚按本任务实际差异逐文件处理，不回退其它任务、重置账号配置或改动数据库。
