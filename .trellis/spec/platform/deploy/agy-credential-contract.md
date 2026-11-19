# AGY 固定原版凭据研究合同

## 1. Scope / Trigger

- 修改 `deploy/flower2api/verify_agy_credentials.py`、合成测试或 AGY 受管凭据研究夹具时适用。
- 本合同描述 AGY 1.5.9 的验证入口及原生观测边界。正式账号、运行环境和 Gemini 路由接入须独立验收。
- Claude Code 正式抓包继续遵循 [官方协议抓包](./official-protocol-capture.md)。账号所有权共同约束由 [account-runtime-v3](../../orchestrator/backend/account-runtime-v3.md) 持有。

## 2. Signatures

```bash
python3 deploy/flower2api/verify_agy_credentials.py [--output <脱敏摘要路径>]
python3 verify_agy_credentials.py --native-config <私有配置路径> [--output <脱敏摘要路径>]
```

- 默认入口只运行合成离线测试，结果为 `evidence=offline_fixture`、`native_verified=false`，返回测试数、失败数、错误数、跳过数及 passed。零测试、跳过或失败均返回非零退出码。
- 原生配置只接受 `{"run_id":"<字母数字开头的1至64位标识>"}`；后续字符允许字母数字、下划线和连字符。配置文件须为当前用户所有的私有普通 JSON 文件。
- 固定测试根为 `/opt/agy-runtime/oauth-test-1.5.9`，原测试容器为 `agy-oauth-test-159`、UID 为 `1001:1001`。目录探针的模型提交数为零。
- 固定原版 SHA256：`39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43`。

## 3. Contracts

### 凭据及单一所有者

- 原生 consumer OAuth 文件为 HOME 下 `.gemini/antigravity-cli/antigravity-oauth-token`，包含 `auth_method=consumer`、`token.access_token`、`token.expiry` 及可选 `token.refresh_token`，身份元数据字段为 `id_token_email`。
- 管理侧要求完整 RT；业务工作副本删除 RT 或使用显式空串。验证器要求 expiry 为带时区字符串。原生目录接受缺失 expiry、改变身份标签的观测只用于说明解析边界；正式管理侧须严格校验有效期并通过已认证状态核对身份。
- 原生目录探针先打开固定根下 `credential-contract.lock`，校验当前用户所有、普通文件及私有权限，使用 `LOCK_EX|LOCK_NB`。环境重检、停止、唯一管理 helper、工作副本实验、恢复和最终摘要落盘均在锁内。并发探针在环境访问前拒绝。锁文件保持固定 inode，进程退出由操作系统释放锁。
- 合成 `CredentialLab` 按账号文件锁串行，持久状态为 `generation/phase/operation_id/document`。刷新前原子写入 pending；成功提交 AT、可选新 RT、expiry 和新代次；省略新 RT 时保留当前 RT。未知结果进入 reconcile，旧代 CAS 发布被拒绝。
- 提交已 rename 而确认失败时，重新读取磁盘，保留已落盘新 RT 和原 operation_id。原始历史快照用于溯源，恢复采用当前权威材料。

### 原生采用与响应观察

- 有效 AT 下，RT 缺省与空串分别通过原生模型目录验证。RT 缺省下文本、真实工具回填和遥测有原生证据；RT 空串在这些组合下保持待验证。
- 常驻进程在凭据文件替换后继续读取原代 AT。工具等待期间发布不同有效 AT 后，原工具轮保持原 worker 和调用归属，后续 TokenSource 仍消费原代。后续产品接入采用新 worker 读取新代、旧 worker 保留在途工作的方案，并独立验收其准入和回收。
- OAuth SSE 观察点为 `codeassistclient.toStreamResponseChunk`，记录原生 Scanner 逻辑块。外层 `response` 包含 Gemini candidates、usageMetadata；最终 STOP 与完整控制终态共同判定实验成功。HTTP 线字节及正式对外 SSE 桥接属于独立验收。
- 文本片段匹配不能替代整体成功；已观察到输出正确片段后控制终态 503，以及 MAX_TOKENS 对应控制 500。
- 原生 code/signal、观察器退出、事件流关闭及业务队列排空分别记录。遥测样本数按实际采集事件计数。
- 原始 AT、RT、令牌摘要、真实身份映射和完整业务块留在私有目录。仓库只保存代次归属、布尔结论、计数、字段名及逻辑块摘要。

## 4. Validation & Error Matrix

| 条件 | 处理 |
| --- | --- |
| 私有文件共享权限、错误所有者、符号链接或损坏结构 | 拒绝读取，公开错误保持脱敏 |
| 非法 run_id 或额外配置键 | 在原生操作前拒绝 |
| 接管锁被占用 | 受控拒绝，原所有者继续刷新及恢复 |
| 固定执行体、容器身份、运行状态或活动进程不符 | 拒绝实验 |
| 管理刷新结果未知 | 保留 reconcile 及停止状态，按当前权威凭据对账 |
| 旧代发布、pending 或 reconcile | 拒绝发布工作副本 |
| 恢复门槛不齐、SSE 已发送或工具待回填 | 离线参考模型拒绝重新提交 |

## 5. Scenarios and Examples

- 正常：默认命令执行合成回环刷新、CAS、进程和故障实验，输出离线摘要。原生目录模式需要单独具备适用测试环境授权。
- 边界：同账号探针 A 在管理刷新后等待恢复，探针 B 以另一个 run_id 启动。B 在进入环境重检前被拒绝；A 恢复并落盘后，新探针才可进入。
- 错误使用：看到磁盘 AT2 后，将旧工具轮移交给新 worker，或认定原进程已热切换。
- 正确处理：保留旧 worker、conversation、toolCall 与凭据代次；新请求的代次切换按运行环境准入合同验收。
- 后续门槛：真实认证错误分类、有界恢复、SSE 首包后换代、工具跨 AT 实际到期、原生取消、重新授权及额度语义分别验证。单项观测不扩展成整个平台能力结论。

## 6. Tests Required

```bash
python3 -m unittest discover -s deploy/flower2api -p 'test_agy_credentials.py'
PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s deploy/flower2api
```

- 合成刷新：并发一次有效刷新、RT 轮换及省略新 RT、旧代回执、断连/坏响应、提交前失败、rename 后确认失败及杀进程恢复。
- 真实本地子进程：探针预检与刷新阶段的竞争拒绝、恢复完成后再准入、持有者中断后的锁释放，以及共享权限/链接锁在环境访问前拒绝。
- 请求参考模型：同账号、新代、AT 有效且改变、单次恢复及原截止时间；已发送 SSE、工具等待和重复/跨归属回填隔离。
- 部署回归：历史 `V3_NATIVE_RELEASE_PUBLIC_KEY` 与旧 pilot 字段按平台镜像合同兼容读取；上游行尾夹具先规范化固定 LF 原件再构造 CRLF，保留坏摘要及父链接拒绝断言。
- 真实实验单独记录固定制品、账号环境、显式预算及停止结果。离线通过只计入合成合同验证。
