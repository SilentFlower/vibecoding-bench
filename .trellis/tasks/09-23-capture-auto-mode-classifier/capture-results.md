# Claude Code 2.1.280 正式抓包结果

全部样本通过正式 `orchestrator → worker → sidecar MITM → 账号既有 upstream proxy →
api.anthropic.com` 链路生成。原始文件仅保存在远端受限目录，目录权限 `0700`、文件权限 `0600`。

| 模型 | 模式 | Run ID | 目标请求 | 结果 | 受限证据 |
|------|------|--------|----------|------|----------|
| Opus 5.5 | bypassPermissions | `60a629e62b2b` | 2 | 2×200 | `data/flows/9-4/11028/60a629e62b2b/capture_index.json` |
| Opus 5.5 | auto | `79a8a302a857` | 2 | 2×200 | `data/flows/9-4/11029/79a8a302a857/capture_index.json` |
| Opus 5.5 | plan | `511bd09cca39` | 2 | 2×200 | `data/flows/9-4/11030/511bd09cca39/capture_index.json` |
| Opus 5.5 | manual | `6fd6edf93b42` | 2 | 2×200 | `data/flows/9-4/11031/6fd6edf93b42/capture_index.json` |
| Opus 5.5 | acceptEdits | `441f19e8baef` | 2 | 2×200 | `data/flows/9-4/11032/441f19e8baef/capture_index.json` |
| Opus 5.5 | dontAsk | `4efcda96ea45` | 2 | 2×200 | `data/flows/9-4/11033/4efcda96ea45/capture_index.json` |
| Opus 4.8 | auto | `8c62caf4dfee` | 2 | 2×200 | `data/flows/9-4/11034/8c62caf4dfee/capture_index.json` |
| Opus 4.8 | plan | `02fd6e30e529` | 2 | 2×200 | `data/flows/9-4/11036/02fd6e30e529/capture_index.json` |
| Sonnet 4.5 | auto | `f396ad9e8d4a` | 5 | 5×200 | `data/flows/9-4/11037/f396ad9e8d4a/capture_index.json` |
| Sonnet 4.5 | plan | `db99298087f9` | 6 | 6×200 | `data/flows/9-4/11038/db99298087f9/capture_index.json` |

## 协议结论

- 所有目标请求的 identity 均为 `claude-cli/2.1.280 (external, cli)`、Stainless `0.112.1`、
  runtime `node`、runtime version `v26.3.0`。
- 所有目标请求保留原始 JSON 字节语义，CCH 全量复算命中；初始请求的确定性 `cc_version`
  后缀全部命中，Sonnet 线程续轮均为三位小写十六进制，并在各自 run 内保持一致。
- Opus 5.5 的 manual、acceptEdits、dontAsk、bypassPermissions 使用同一普通画像，不含
  safeguards、`dangerous-tool-use-2026-09-03` 或 `afk-mode-2026-01-31`。
- Opus 5.5 与 Opus 4.8 的 Auto/Plan 都包含 `dangerous_tool_use` safeguards；每组 SSE 均有
  `message_delta.delta.safeguard_results`，非空 `status.tool_uses` 的键能关联同请求 tool-use ID。
- Sonnet 4.5 Auto/Plan 不含 safeguards 或 safeguard results，使用含
  `message-threads-2026-08-12` 的普通模型画像。

## 构建与部署

- `vibecoding-bench` 功能提交 `9fb297f`，六模式镜像构建 run `35813157934` 成功并已部署。
- `cc2api` 协议提交 `ded49ec`，CI Docker run `35819194824` 成功；父仓固定提交为 `b79319c`。
- 线上 `cc2api` 使用不可变摘要
  `sha256:acc469852e98466ecd779f3d538f55674f7d53b9c269a8e44bb279bd222b2276`，镜像 revision
  为 `ded49ecee38962972a56e4e77825b61b929dafb9`。部署前 5674 已建立连接数为 0。
- 容器重建后 restart count 为 0，本机与外部 HTTP 均返回 200，最近 200 行日志没有
  panic、fatal 或 error。
- 数据库 4 个账号的 `version` / `version_base` 均为 `2.1.280`，`build_time` 均为
  `2026-09-21T20:40:17Z`；默认 profile 为 `2.1.280`，允许范围为 `2.1.89-2.1.280`。
- 远端部署前 compose 备份位于
  `/root/claude-code-gateway/backups/deploy-20260923T0444Z-safeguards-ded49ec/docker-compose.yml`。
