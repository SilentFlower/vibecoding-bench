# 实施计划：账号 scratchpad 磁盘持久化

## 顺序

1. [ ] Brief 评审后激活本子任务，经 trellis-route 进入 inline 实施，读取 implement.jsonl、PRD、设计和适用 orchestrator、节点迁移、备份规范。以当前共享工作区为基线。
2. [ ] 补齐隔离挂载原型：两账号、多session、写改删、目录重命名、权限及符号链接；比较容器逻辑树与 upper 树，实际重建卷并恢复。能力不足与挂载失败验证保守退出。
3. [ ] 提取最小 scratchpad 内部模块，集中处理路径、协议、卷归属、能力核验、挂载回执与流式转存；公共API加中文docstring。保留现有角色和安全边界。
4. [ ] 接入 account_isolation 创建及 AccountRuntime 空闲维护保护，覆盖系统更新、旧CLI移除、故障恢复、评审交接、后台预热和普通API路径。转存完成前保全源文件。
5. [ ] 接入源节点 fence 前转存与目标节点挂载，更新精确运行态排除和持久文件的备份／迁移验收。调整涉及的镜像构建上下文及发布材料。
6. [ ] 故障注入覆盖每个转存阶段、磁盘满、未知归属、坏链接、忙碌、挂载能力不足、重复回执及失败回退。核对最新凭据和环境代次。
7. [ ] 运行聚焦测试和真实Docker离线验收，验证真实CLI的合成历史会话续跑。配对测量tmpfs、页缓存、磁盘与CLI操作，同宿主模拟sender负载交错测量性能。
8. [ ] 执行 Check-All、Spec 评估及精确提交计划，按各自流程完成交付。

## 验证命令与场景

以下现有测试命令从仓库根执行；新增测试模块在实现后登记精确名称。

```bash
PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_account_runtime test_project_review_runtime test_cluster_environment test_cluster_migration_files test_cluster_archive test_cluster_runtime_host test_storage_backup
```

- 隔离Docker验收新增专用脚本并记录命令，使用本地同批镜像、合成身份和模拟上游。真实CLI的首次会话、保全文件、重建、resume与兄弟session归属逐项验收。
- 3×8 MiB文件作为可重复tmpfs对照；使用现场样本同大小的合成文件验证流式转存内存上界。
- sender测试固定版本、并发、输入、日志和响应节奏，记录吞吐、TTFT、p50/p95/p99、冷启动和CPU。将磁盘写入及迁移操作与基线交错重复，解释波动，可重复退化停止接纳。
- 完整及精简备份真实恢复到独立目录；节点迁移包含源导出、目标导入、目标续跑、源回退及部分失败重试。

## 高风险位置与回退点

- `account_isolation.py`：挂载参数、UID、标签及原角色启动顺序。
- `account_runtime.py`：租约、旧实例停止、各重建入口和并发控制。
- `cluster_environment.py`、`cluster_migration_files.py`、`storage_backup.py`及其实际排除策略入口：停源时序、数据完整性、临时元数据重建。
- 数据发布前保留旧CLI；发布后保留持久文件及转存回执。具备识别新布局的兼容版本才可回退，回退前核对全部新增文件和原tmpfs容量。

## Check-All 修复续行

用户已选择修复全部：CHK-001、FBK-001、FBK-002。

- [x] CHK-001：补齐登录草稿镜像夹具，验证旧布局删除、重试与对账。
- [x] FBK-001：绑定源启动身份，覆盖同次启动继续写入、导出中重启与真实重启恢复。重启后未确认恢复的快照继续阻挡新转存，保护唯一旧副本。
- [x] FBK-002：登记并核验工作目录协议，动态排除已归属目录；未知同名资料保全并阻挡挂载接管。
- [x] 运行定向测试、真实Docker复现回归、完整编排测试，再执行Check-All重检。

### 本轮验证事实

- 完整回归基线：`PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator`，1939项、784.602秒，成功，跳过2项。
- 最终增补保护的受影响模块：`PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_cli_scratchpad test_login_drafts test_account_runtime test_project_review_runtime test_cluster_environment test_cluster_migration_files test_cluster_archive test_cluster_runtime_host test_storage_backup`，248项、35.006秒，全部通过。完整回归启动后补充的源快照保护由这组当前代码回归覆盖。
- 真实Docker：`deploy/flower2api/verify_scratchpad_storage.py`，10个场景通过，证据为 `research/docker-repair-final-functional.json`。
- 最终12个Python文件语法与受检文件diff检查通过。固定sender及同宿主写入的既有6组、720次配对性能证据继续有效；本轮改动位于转存恢复和挂载协议核验，实际sender请求路径保持原合同。
- Check-All full重检：CHK-001、FBK-001、FBK-002均解决。发行镜像在实际节点的单账号灰度沿发布阶段执行。

## 发布候选准备

- 用户已要求发布。线上与远端flower2api均为v1.15.3，源码b26e5454bc695611966de8be44d182e3dacdc807。
- 本次发行候选从该正式源码提取临时文件治理及必要的存储盘点依赖，在隔离目录验证。共享工作区的人工节点集群实现继续沿原任务持有；其scratchpad迁移接线随集群交付保存。
- 正式版本的本机备份、停止/唤醒、评审交接、原路径和会话恢复为本次发行验收。远程节点支持沿原R5保留，并由共享工作区已验证的集群接线承接。
- 发布前展示实际范围、版本说明、验证及Git计划，沿正式签名发行与原实例更新链执行。

### FBK-003修复

- [x] 增加存储恢复能力与激活声明，旧发行继续严格解析。
- [x] 在更新器准入、列表与回退投影，以及宿主失败恢复中核验布局兼容。
- [x] 准备账号组件摘要保持原值的兼容候选，再准备启用候选；验证跳过兼容阶段会拒绝。
- [x] 使用旧账号镜像和兼容代码实际恢复迁盘文件，并核对原会话与账号归属。
- [x] 运行发行、更新器和宿主恢复回归，重检后记录后台回执终态。

## 开工前检查

- [ ] PRD、design、implement、brief 新鲜度一致，产品未决问题已收敛。
- [ ] 通过 Brief owner 的实际确认模式；随后 task.py start。
- [ ] 共享工作区变更归属和当前规范已核对。
- [ ] 线上操作、真实数据迁移与发布按各自授权边界处理。
