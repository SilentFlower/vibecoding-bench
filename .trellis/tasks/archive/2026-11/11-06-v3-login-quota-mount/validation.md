# 验证记录

## 原故障复现

- 命令：`PYTHONPATH=orchestrator .venv/bin/python -m unittest test_account_runtime.AccountRuntimeTests.test_saved_login_draft_repairs_quota_mount_once_and_preserves_data`
- 修改产品代码前执行，1 个用例失败。
- 失败断言：正式账号再次准备后，实际形状的网络 Mounts 中仍没有 `/quota-accounts/1` 只读挂载。
- 夹具通过原 `ensure()` 创建无 ID 草稿，再经原 `_row()` 绑定正式 ID，未伪造挂载检查结果。

## 修复后聚焦验证

| 命令 | 实际结果 | 范围 |
| --- | --- | --- |
| `PYTHONPATH=orchestrator .venv/bin/python -m unittest test_account_runtime test_login_drafts` | 111 个通过，28.371 秒 | 挂载补齐、幂等、并发、占用保护、失败对账及登录提交恢复 |
| `PYTHONPATH=orchestrator .venv/bin/python -m unittest test_account_runtime.AccountRuntimeTests.test_api_transport_keeps_missing_cli_quota_mount_without_waiting_on_itself` | 1 个通过，0.201 秒 | 显式导入 `call` 后重验 API 自持许可仍可准备传输 |
| `PYTHONPATH=images/sidecar .venv/bin/python -m unittest discover -s images/sidecar -p test_recorder.py` | 31 个通过，0.140 秒 | 原有额度和认证保护保持 |
| `.venv/bin/python -m py_compile orchestrator/account_runtime.py orchestrator/test_account_runtime.py deploy/v3/verify_login_drafts.py` | 退出 0 | 当前三个变更文件语法有效 |
| `git diff --check` | 退出 0 | 当前 diff 无空白错误 |

使用现有本地 `.venv`，没有新增依赖或修改依赖清单。

## 本地 Docker／浏览器验证

- 命令主体：`.venv/bin/python -u deploy/v3/verify_stack.py --manifest .deploy/v3-ownership-implementation/release-a6.json --source-overlay --browser --reauth`；子进程 PATH 前置现有 `.venv/bin`。
- 使用合成 CLI、合成 OAuth 产物、随机部署与独立 SQLite，不调用真实 OAuth 或付费模型。
- 首次执行未通过：新增容器探针只保留了非零退出状态，没有异常正文；静态复核发现探针将新账号允许缺省的 `windows` 当作必填字段，已按 `QuotaGuard.snapshot`／Recorder 实际合同修正，并保留探针异常正文。原挂载隔离、只读和资料保留断言不变。
- 首次日志：`.deploy/v3-login-quota-mount/docker-attempt-1.log`。最终重跑日志：`.deploy/v3-login-quota-mount/docker.log`，整体退出 0。
- 最终随机部署 `stack-verify-4c83f8bbfb`：真实草稿提交后首次准备增加一代，网络角色具备本账号专属只读额度挂载，容器读取 JSON 成功、写入被拒、未见其他账号目录；同一环境／画像／HOME 凭据保持，重复准备代次不变。Recorder 观察多个 0.2 秒周期，没有发布失败暂停信号。
- 既有真实 Chrome／HTTP／SQLite／Docker 重授权、草稿重启恢复、提交、完整删除、统一会话与退出继续通过；最终 stop、备份、旧哨兵容器及数据库不变检查通过，随机部署资源由脚本 finally 精确清理。
- 重跑期间只补充了 Recorder 等待原因的中文注释，没有改变执行逻辑；结束后当前验证脚本再次语法检查通过，`git diff --check` 退出 0。
- 该本地 dirty 清单及源码覆盖只验证当前 Python 改动和实际容器合同，不作为正式镜像发布或生产部署证据。
