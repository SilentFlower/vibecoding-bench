# Claude Code 2.1.260 部署证据

## 结论与取证边界

- cc2api 已于 `2026-09-05 07:01:21 +08:00` 完成生产 recreate，镜像、HTTP、数据库及版本迁移检查通过。
- 用户随后反馈真实 Claude Code 使用正常；这是用户侧成功使用证据，未指定模型集合，不能扩展为四模型、bootstrap/hello 和 continue 全部验收通过。
- 用户明确停止模型测试。后续仅整理本地历史结果和静态材料，不再发送模型请求或启动 run。
- 本记录于 `2026-09-05` 从同一会话的原始工具结果恢复；下面的时间均为历史观察时间，不代表本轮重新查询生产。
- 两条手工 Opus 请求不具备真实客户端请求的完整结构，不作为升级成败的验收依据。缺少身份块已确认，429 的确切原因未证实。
- 联合回滚已完成材料可用性核验，完整非破坏性恢复演练未执行。2026-09-05 用户确认取消该演练要求，保留未执行说明，不再阻塞收尾；不将其描述为演练通过。

## 可追溯来源

原始会话 ID：`01a069e7-cbcf-7c42-89ea-474d8bcadd1d`。原始会话保留在本机，不提交原始输出、凭据、完整请求或响应正文。

| 历史时间（UTC） | 工具调用 ID | 内容 |
| --- | --- | --- |
| 2026-09-04 22:28:02 | `call_qCE03QUQRtzxcZjKY3mhiPWg` | registry digest、迁移前设置与账号摘要 |
| 2026-09-04 22:28:25 | `call_0Mr5kRMNaqQaDgeXEui85cK7` | bench 环境版本、schema、HTTP、DB |
| 2026-09-04 22:28:45 | `call_z50XoME78Y2NFl3rAHpAa9RL` | bench 页面版本及 run 版本分布 |
| 2026-09-04 23:00:18 | `call_02bgoV5hF0K6GL3kwwUkD9X4` | 精确镜像 pull、旧镜像及网关连接数 |
| 2026-09-04 23:00:43 | `call_pxFtn9W3LtqijDD8gt3lMwX1` | 两套 DB 备份路径、hash 和权限 |
| 2026-09-04 23:01:22 | `call_UnC3sYzjZMP4ST4W0AZkArMA` | 网关 recreate、启动时间、HTTP |
| 2026-09-04 23:02:01 | `call_CL4iKalDqDYV0yoLvKkyVnpq` | 镜像、迁移后 DB、配置保留、启动日志 |
| 2026-09-04 23:06:39 | `call_frLwss00hEHIQ41TAGDZrSHD` | 第一条手工 Opus 请求返回 429 |
| 2026-09-04 23:07:39 | `call_STM6vUrImvoyhZ6ww8zUYBll` | 第二条手工请求的通用错误分类 |
| 2026-09-04 23:10:36 | `call_kuNdKUR8kacUQlufgiQUne9K` | 旧镜像、备份完整性、配置比对 |
| 2026-09-04 23:11:13 | `call_4CoXCjO6zNo5kzBzHpK5C5uc` | 后续流量日志计数，不能据此归因 |
| 2026-09-04 23:12:38 | `call_y73vRQ7BhZRHgxOrxYomVv2G` | 停测后无残留请求进程 |

## 发布产物

- cc2api 提交：`7aecda39da8719f6d61af07274038bb6eb1389e5`。
- 父仓 gitlink/规范提交：`c42d696`；协议归档提交：`478eaf1`。
- GitHub Actions run：`33923480410`，历史结果为成功。
- 镜像：`ghcr.io/silentflower/claude-code-gateway:sha-7aecda3`。
- SHA tag、当时的 `latest` 和生产 inspect 返回值均对应 `sha256:23ca7ce18ddac31f9e0c2ee95d35c75e92ec3dd417719c6bfe41848c41acd8fc`。
- 部署前网关 image ID：`sha256:06701eb10f03bd665527f059b25085dfc0640c1467794ac5c51db9027a17b96d`。
- pull 后网关 `established_5674=0`，随后 force recreate；未部署或停止 bench。
- bench 当时仍有直连上游的活跃 run；不能将网关低连接窗口记作 bench 所有 run 已归零。

## 数据库与配置备份

备份时间戳：`20260904T230043Z`。历史操作使用 SQLite 数据库备份 API，不直接复制在线 DB。

| 项目 | 备份目录 | DB SHA256 |
| --- | --- | --- |
| cc2api | `/root/claude-code-gateway/backups/deploy-20260904T230043Z-claude-code-2.1.260` | `141cfb0eb9f035f1a81092ff5496267c527eb6bea1a4d23ba9a6af5fb1861769` |
| bench | `/root/vibecoding-bench/.deploy-backups/20260904T230043Z-cc2api-claude-code-2.1.260` | `06ae0c1d61b5dc078065c63dfa8db93f6aa222ca915983f3a1f4058f0314bcca` |

两份 DB 备份权限均为 `600`，后续只读复查 `integrity_check` 均为 `ok`；配置备份与当时生产文件匹配。
目录权限和旧 bench 三镜像完整清单未形成可复核输出，不能补写为通过。
本次 bench 备份来自已运行 2.1.260 的 `abc2c98`，不能把它直接当成升级前 2.1.257 的 bench 快照。

## cc2api 部署结果

- 容器 ID：`06df76b82094`，状态 `running`。
- 启动时间：`2026-09-04T23:01:21.369042326Z`。
- HTTP 根路径：`200`；在线数据库 `integrity_check=ok`。
- profile：`2.1.257 -> 2.1.260`。
- allowed range：`2.1.89-2.1.257 -> 2.1.89-2.1.260`。
- 4 个账号的 `canonical_env.version/version_base` 均为 `2.1.260`，`build_time=2026-09-03T19:41:35Z`，Node `v26.3.0`。
- Compose 曾提示持久化 volume 非其创建；本次复用了该 volume，随后 DB 完整性和设置比对正常，未删除或重建数据 volume。

以下摘要部署前后完全一致：

| 保留项 | SHA256 或实际值 |
| --- | --- |
| 排除版本项后的 settings | `13529f2b6a82974694986c5e69578292e549d16da141050dacff4ed29c8a9294` |
| 账号能力配置 | `e20ee5a12f494a490bd53e1961846553b4199a5a2eaee4a12d1732bc9ce76301` |
| canonical env 非身份字段 | `bca431c08dda31ec0cce08b3fdf8c16e8d5fb0e0276b823fb4cda24e34aef477` |
| bootstrap 选项 | `b7a297d8b21a26a14a8da12e96942ebdab83abbd8291ac1913e4e19e4eae46df` |
| allowed UA | `5233f41291ee5914176ab3253b16d1c7fff784ad66f32358bfa3628f4758efda` |
| system-role 模型 | `claude-opus-5,claude-fable-5,claude-opus-4-8,claude-sonnet-5,claude-fable-5-1` |
| 1M allowlist 分布 | `opus,claude-sonnet-5`，4 个账号 |

启动检查窗口内 `panic`、迁移错误、本地版本拒绝、system-role 拒绝和 CCH 错误计数均为 0。
这是特定窗口的观察，不代表所有模型行为都已覆盖。

## bench 一致性

- 生产 tag：`abc2c98`，worker/sidecar 当时均引用该 tag。
- `.env` 与 WebUI 的 `claude_code_version` 均为 `2.1.260`。
- HTTP `200`，DB `integrity_check=ok`；`runs.claude_code_version` 和 `runs.claude_effort_level` 均存在。
- 22:28:45 UTC 的版本分布包括：2.1.260 `running=4`、`success=50`、`stopped=3`、`timeout=2`；历史 NULL 值仍保留，未做无依据批量回填。
- 23:09 UTC 的自然运行汇总仍为 2.1.260。bench 请求直连 Anthropic，这些成功 run 不能证明请求经过 cc2api。
- run 快照及 continue 逻辑沿用已完成的 [bench 运行时研究与回归记录](../../archive/2026-09/09-04-vibecoding-bench-claude-code-2-1-260-runtime/research.md)。本次未重新启动生产 continue，不能记录为本轮动态验收通过。

## 手工请求与用户反馈

历史上仅发送了两条手工 Opus 请求，模型 `claude-opus-5`，参数包含 `max_tokens=64`、`stream=true` 和 adaptive thinking。
请求设置了 Claude Code 2.1.260 UA，但未提供真实客户端的 system 身份块，也没有完整的工具、会话结构。
该 UA 会被识别为 `ClientType::ClaudeCode`，所以不能把差异归因于被识别成普通 API 客户端。

第一条返回 `429`、`message_start=0`、`message_stop=0`，多模型脚本随后停止；第二条仅用于读取错误类别，得到 `rate_limit_error / Error`。
未向 Sonnet、Fable、Haiku 发送该测试。下游两次请求与日志中的上游尝试次数不是同一计数口径。
23:11 UTC 的日志查询记录了上游 429 共 12 次、HTTP 200 和传输完成均为 0；其具体归因未证实，不能隐藏该窗口，也不能将其当作用户随后实际使用结果。

用户随后原话为“我去claude code里面用都正常啊”。记录为用户报告的实际使用正常，不扩展到未指定的四模型完整矩阵。
用户指出身份块缺失；这是已确认的请求结构问题。早前把身份块缺失直接视为 429 原因、把实际使用正常视为全部验收完成的说法过强，本记录予以收窄。
用户要求停测后，已核验无残留请求进程。后续不重放、不补造身份块探测、不更改生产账号设置。

## 回滚证据与剩余边界

历史只读复查已确认：旧 cc2api 镜像仍存在；cc2api 备份 profile/range 为 `2.1.257 / 2.1.89-2.1.257`；两份 DB 备份完整性正常；配置备份比对正常；当前 Compose 可解析。
首次从备份目录直接解析 Compose 因相对 `env_file` 路径失败；后续仅确认当前目录 Compose 与备份文件比对正常，不能把它描述为独立备份目录解析或完整恢复演练通过。

将来确需联合回滚时，遵循 [操作与恢复边界](rollback-plan.md) 和 [部署规范](../../../spec/vibecoding-bench/deploy/remote-deploy.md)。
本版本完整回滚脚本的静态验证、生产备份临时副本的 `.backup/.restore` 演练、旧 worker 实际 CLI 版本及三镜像追加解析均未执行。
用户已明确本次不再补做这些演练，作为已知限制保留。该决定不授权实际回滚，也不改变将来故障处置时的前提要求。

## 验收映射

| PRD 验收项 | 当前证据 | 状态 |
| --- | --- | --- |
| 目标镜像、HTTP、DB | 精确镜像 pull/inspect，HTTP 200，DB ok | 通过 |
| profile/range、账号迁移、自定义设置保留 | 4 个账号版本和前后摘要一致 | 通过 |
| 实际使用与协议证据 | 用户实际使用正常；复用既有协议证据，说明四模型和 bootstrap/hello 未逐项取证 | 按本次收尾范围通过，不追加请求 |
| bench 默认与 run 快照 | env/WebUI、DB 分布、已有回归记录 | 通过，明确生产 continue 未重跑 |
| 回滚材料与未演练说明 | 旧镜像和 DB 可用，操作边界及未演练说明已记录 | 材料核对通过，完整演练本次取消 |

保持已运行的 2.1.260。用户确认的收尾范围已满足，接下来提交、归档任务记录并汇总父任务；不再因未做完整演练重新打开阻塞。
