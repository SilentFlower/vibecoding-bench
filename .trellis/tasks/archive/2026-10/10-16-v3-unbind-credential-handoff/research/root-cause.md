# 根因与只读证据

- 线上批次 `ci-38831776288-1`，父提交 c70dc4a，cc2api ec108e7。账号 id=3 `10-15` 绑定 null；profile/HOME/access 均 AT-only；profile 与 HOME 当前 SHA256 均为 `a60b2d2a967630db32db93ae2d518c4592109847791517a250595ad21bb2cf26`。
- 部署前备份管理 profile SHA256 为 `fbf8bb1552279cddf395035582eff7dc9218297b4d091354566600022f98c1f2`，有 RT；备份 HOME 已是上面的 AT-only 摘要。现有秘密没有在工具输出或本任务中记录。
- 当前 profile mtime `2026-10-16T01:13:36.147841+00:00`，HOME mtime `01:13:32.863832+00:00`，后台 refresh failed。创建两次均为 HTTP 400，远端账号数仍为 0。
- 只读恢复核对：当前和备份 AT、expiry 相同；当前 profile/HOME 与备份 profile/HOME 的 userID、accountUuid、organizationUuid、emailAddress 全部一致；无 active run、execution.json 或 login-commit.json。当前容器 ready/running，需上线时重新核对并受控停止。
- `/tmp/v3-create-rt-audit.py` 与 `/tmp/v3-create-rt-recovery-proof.py` 是本轮临时只读远端脚本，未发送 OAuth/usage/模型请求。
- 临时 Python 隔离调用既有 DeletedBindingTests.setUp、真实 main.delete_account_cc2api_binding、AccountRuntime.claim/sync_credentials/release：解绑后 RT=True，release 后 RT=False，exit 0。只用合成 token、临时 SQLite 与 mock Docker/管理 HTTP。
- 上轮即时身份核对结论在当时成立，但不覆盖此后异步收尾；应将验收延长到下一次使用凭据的边界，而非单纯比较解绑前后文件。

## 缺陷分析：解绑后的 RT 降级覆盖

### 1. 根因类别

- B 跨层契约、C 传播遗漏、D 验证缺口、E 隐式假设：DB 绑定从远端变成本地，但 HOME 的 AT-only 角色没有迁移，release 仍假定本地 HOME 永远完整。

### 2. 上次修复为何遗漏

1. 只修复远端 404 导致的解绑门禁，未追踪下一个刷新消费者。
2. “保留 HOME”误写成凭据字节不变，夹具把不完整凭据作为成功预期。
3. 上线即时 21 个摘要全部相同属实，却不代表随后后台收尾也安全；需要跨时间边界验证。

### 3. 预防机制

| 优先级 | 机制 | 实际动作 | 状态 |
| --- | --- | --- | --- |
| P0 | 所有权交接 | 明确 take_ownership，绑定仍 AT-only，独立 HOME 轮换不回滚 | 已实现 |
| P0 | 数据保护 | release 校验完整 AT/RT/expiry；未提交草稿不写正式 profile | 已实现 |
| P0 | 失败恢复 | 无令牌意图记录、摘要与归属校验，重启保持隔离，重复解绑续办 | 已实现 |
| P1 | 连续场景 | 创建/绑定→删除→解绑→真实后台失败收尾→再次页面创建 | 最终堆栈已通过 |

### 4. 系统性检查

- 同类边界：正常解绑、远端删除、维护、release、后台刷新 finally、启动 reconcile 和登录草稿。旧 warmup 接口 null 本来表示保留绑定，没有新增解除关联语义。
- 设计改进：凭据来源不再只由文件存在或 DB null 决定；无法完整交接时保留证明和原秘密。
- 验证改进：检查下一次使用与失败收尾，保留身份和轮换断言，不把合成成功当成真实授权恢复。

### 5. 知识沉淀

- [x] 原因、失败验证和最终测试证据记录在本文件。
- [ ] 在 Update-Spec 阶段补充 v3 所有权交接的可执行契约；不新增重复的通用原则。

## 最终实施验证

- `/tmp/v3-handoff-red.log`：先执行失败回归，13 项中 3 项失败，证明交接缺失和身份保护缺口。
- `/tmp/v3-handoff-all-c.log`：最终 288 项，82.124 秒，exit 0。较早首轮五个登录草稿失败源于合成完整凭据缺 expiry；真实 CLI 具备该字段，已补齐夹具，同时修复未提交草稿不应回写正式 profile 的边界。
- `/tmp/v3-handoff-build-c.log`：正式 canonical 联合构建 C exit 0；清单 `/tmp/v3-handoff-c-manifest.json`，release `handoff-20261016-c`。A/B 不是最终源码；C 补齐本地账号删除不依赖 RT 的原兼容边界。
- 最终冻结 SHA256 `bbb037f5c669657a8ada78df16314409dbad8e740a531c8a40e763bde09d9cd9` 与当前源码输入重算一致。
- `/tmp/v3-handoff-stack-c.log`：真实 Chrome、HTTP/WS/SSE、两库和真实容器后台刷新失败收尾、再次页面创建、AT-only 回切、旧 Cookie 拒绝、停机备份/离线导入幂等/旧哨兵保护，exit 0。OAuth 探测仅用失败替身，不访问真实上游。第一轮夹具错误地比较创建前的毫秒 expiry，与远端规范化后的快照不同，已改为创建完成后的真实管理快照。
- Python AST/py_compile、`git diff --check` 通过；原 55 项 dirty 的 tracked diff 和 untracked 内容摘要匹配建任务基线，cc2api 子仓 clean。
- 上线恢复与部署尚未执行，保留为上线后验收，不计已通过。
