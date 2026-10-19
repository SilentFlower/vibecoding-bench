# 实施计划

- [x] 只读核对生产 profile/HOME/备份结构、文件摘要与账号归属。
- [x] 临时隔离复现真实解绑后 claim/sync/release 抹除 RT，无真实上游请求。
- [x] 完成 Brief 评审后启动任务，进入 trellis-route(target=implement)，按 before-dev 读取规范。
- [x] 新增与生产一致的失败回归，覆盖 AT-only HOME、后台刷新失败收尾、已有本地轮换和绑定 AT-only。
- [x] 修复解绑所有权交接与 release 降级覆盖，检查维护、旧兼容绑定入口和启动对账；补齐权限、锁序、失败/重复调用保护。
- [x] 扩展隔离真实堆栈：创建/绑定→正式远端删除→页面解绑→后台失败收尾→再次创建，核对两库、RT、AT-only 回切与原身份。
- [x] 执行 Python 必要全量、语法、diff 检查与联合镜像堆栈验证，记录实际日志和 exit code。
- [ ] 按 Pre-Check → Check-All → 缺陷复盘 → Update-Spec → Trellis Push 推进；Git 操作沿用精确范围确认。
- [ ] CI 发布同批镜像，重验实际交付物；线上停机新备份、受控恢复明确丢失 RT、切换同批镜像并核对本地结构/身份及其他容器。

## 重点文件

- `orchestrator/account_runtime.py`：所有权交接、完整性检查和本地回写。
- `orchestrator/main.py`：已有 owner/profile 保护、解绑/旧兼容入口与错误提示，按实际需要调整。
- `orchestrator/test_deleted_binding.py`：真实临时 SQLite 与运行时回归；`orchestrator/test_login_drafts.py` 为合成完整凭据补齐真实 CLI 必有的 expiry，未提交草稿收尾不回写正式 profile。
- `deploy/v3/verify_deleted_binding.py`：扩展已有真实页面/API/两库场景，避免另造重复夹具。
- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`：按最终实现在 Update-Spec 阶段补齐交接契约。

## 验证命令

```bash
/tmp/v3-unbind-venv/bin/python -m unittest discover -s orchestrator -p 'test_*.py'
python3 deploy/v3/manage.py build --release <全新批次> --manifest <新清单>
/tmp/v3-unbind-venv/bin/python deploy/v3/verify_stack.py --manifest <新清单> --browser --deleted-binding
git diff --check
```

Docker 地址池若仍耗尽，仅复用已验证的临时非重叠子网包装，不 prune 或停止他人资源。上线守卫失败时保留备份和当前秘密，不恢复旧数据库、不强行创建远端账号。
