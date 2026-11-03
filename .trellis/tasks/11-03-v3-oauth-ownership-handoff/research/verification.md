# 凭据交接验证记录

## 范围与隔离

沿用用户已确认的 PRD、design 和必测场景。仅本地随机部署、合成账号和本地上游；不调用真实模型、OAuth、邮件或其他外部业务。Chrome/CDP、requests、SQLite 和本次临时 PostgreSQL 均可用。项目尚无 e2e-playbook，本次新增的任务场景不写入通用 playbook。

## 跨层场景表

| ID | 路径 | 操作与可观察期望 |
| --- | --- | --- |
| O-S1 | HTTP + 两库 + HOME | 正式同步创建：原设备、新目标与归属同事务创建；绑定后 HOME 仅 AT |
| O-S2 | HTTP + DB + 上游计数 + UI | 解绑暂停，模型/count_tokens/测试/额度/强制刷新均无上游连接；页面显示本地管理；RPM/并发/优先级仍可编辑 |
| O-S3 | 容器 + HTTPS + 两库 + 文件 | Node 原生刷新经真实账号代理访问本地 TLS 上游，连续轮换三次后重绑原 ID；远端持有最后 RT，HOME AT-only，设备/缓存/配置不变 |
| O-S4 | HTTP + 两库 + UI | 原提交成功后人为丢弃响应，控制进程退出；页面保留交接中，在线管理 API 对账后 ready，可继续关联原号 |
| O-S5 | HTTP + DB + 文件 | 删除前破坏合成管理凭据；仍可无 RT 地退休并软删除本地账号，远端暂停，ID/HOME 保留 |
| O-S6 | Chrome + HTTP + 两库 + 文件 | 复用 --browser --reauth：成功/错误身份/取消/部分写入/重启和原租约收口，人工停用与限流保持 |
| O-S7 | Chrome + HTTP + 两库 + 文件 | 复用 --browser --deleted-binding：远端明确删除后的收口、原 HOME/设备保留和本地独立运行 |

各场景失败即停止该次验证，保留非秘密错误元数据；修复或校正夹具后重跑。verify_stack 的 finally 只移除本次随机部署资源和临时目录，保留其他部署哨兵。

## 已执行证据

- Python 全量 ` .venv/bin/python -m unittest discover -s orchestrator`：1105 项通过、1 项跳过，620.137 秒。后续归属恢复修复以聚焦最终版覆盖：在 orchestrator 运行 `../.venv/bin/python -m unittest test_credential_ownership test_login_reauth test_deleted_binding test_credential_publication test_account_runtime test_main`，197 项通过，57.090 秒。
- Rust 最终 `cargo fmt --check` 与 `cargo test --locked --quiet -- --test-threads=2` 通过：lib 748 项通过、1 项忽略，其余所有集成测试通过。默认高并发曾出现 localhost 用量异步超时；单独重跑及限制线程的完整回归通过。
- SQLite 与独立临时 PostgreSQL 的 `credential_ownership_storage` 合同通过；PostgreSQL 最终 1 项通过，0.97 秒，临时容器已移除。两次幂等迁移、CAS 与凭据/回执同事务、坏记录隔离、删除清理语义一致。
- 部署工具 54 项通过，2.390 秒；Vue `npm run build`、原生 JS `node --check`、Python 编译与双仓 diff 格式检查通过。
- 本地联合 a6 镜像形成完整清单。由于公开 crates.io/PyPI 下载超时，本地同 Cargo.lock 使用已有 registry 和 host 下载的公开 wheels 离线构建；生产 Dockerfile 保持正式源。a1–a4 失败，未用于部署。
- 以下三个真实隔离命令均以退出码 0 完成：`PYTHONUNBUFFERED=1 PATH="$PWD/.deploy/v3-ownership-implementation/bin:$PATH" .venv/bin/python deploy/v3/verify_stack.py --manifest .deploy/v3-ownership-implementation/release-a6.json --source-overlay --browser --ownership`、分别替换最后参数为 `--reauth`、`--deleted-binding`。
- O-S1–O-S5 通过：真实 HTTP/两库/Node HTTPS/原代理/Chrome 验证暂停后零上游、配置热编辑、三次 RT 轮换、原 ID 重绑、AT-only、设备/缓存保留、提交回包丢失及控制进程退出后对账、坏凭据删除仍暂停原网关账号。
- O-S6 通过：真实 WS/tmux 输入、同 SID 重连/新票据、授权码投递回执、错误身份拒绝/取消、输出组件失败、四种布局、草稿刷新/进程退出/管理器重启/清理故障与完整删除；独立未知 CLI 版本可以保存且不伪造 cc2api 设备证明。
- O-S7 通过：远端删除、调度器重启、页面解绑、完整 RT 交接、真实后台刷新失败收尾与再次创建；身份、两库及 AT-only 一致。
- 三套测试均完成停机、隔离合成备份恢复和离线导入幂等；各自随机资源移除，其他部署哨兵的进程、启动时刻和数据库字节保持。没有调用真实外部 OAuth 或模型。
- 最新 Rust 401 停用与维护并发修复由最终 Rust 全套覆盖；Python 最新源码通过显式只读 overlay 验证，overlay 摘要随日志记录。a6 不是生产发布批次，最终联合 CI 由父任务验收。
- 对原保留基线的 348 个文件逐一比对 SHA256，均保持不变。

## 验收映射

| AC | 实现及验证 |
| --- | --- |
| OA1 | CredentialActivity 覆盖发送生命周期与刷新；暂停同账号 sticky 返回维护，作用域外正常。Rust 归属并发/调度合同、O-S2 零连接和热配置通过 |
| OA2 | 同代 return/finish、HOME 权威 RT 与绑定原子记录；O-S3 三次真实 Node/TLS 刷新、原 ID/最新 RT/设备/缓存/策略通过 |
| OA3 | reauth 原租约和导入回执 import_operation_id；原有重授权聚焦及 O-S6 成功/错误身份/取消/策略保留通过 |
| OA4 | prepare/commit/finish/status、source_phase/代次与 refresh_pending；六个落盘边界、响应丢失、重启、迟到回执和未知刷新关闭测试通过 |
| OA5 | 新建/旧绑定/来源不明显式授权/远端明确删除分流；197 项聚焦及 O-S1/O-S7 通过 |
| OA6 | SQLite/PostgreSQL 实际合同；无令牌归属/回执/证明和批量列表，Chrome 真实显示及静态秘密边界通过 |
| OA7 | O-S1–O-S7 真实 Chrome/HTTP/SQLite/Docker/合成 HTTPS 全部通过；实际第三方 OAuth 不以合成结果代替 |

## 上线后验证（父任务承接）

- 使用最终同批 CI 清单部署 US；保留当前配置、RAM、账号与工作，不做生产备份或清理。
- 核对两服务/账号镜像能力协议 1、只读归属状态与恢复页面、无秘密返回、现有任务及管理接口正常。
- 不自动执行真实授权、解绑、刷新或模型请求；真实供应商 OAuth 可用性依赖用户实际授权流程。
