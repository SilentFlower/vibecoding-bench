# 实现验证记录

## 最终验证

验证日期：2026-10-29；产品基线：cc2api `6780ea453050b76d9657488e75660e837bbe4f30`。以下命令已实际执行，退出码均为 0。

| 工作目录 | 命令 | 结果 | 最终日志 |
| --- | --- | --- | --- |
| `cc2api/` | `cargo fmt --check` | 通过 | `/tmp/cc2api-fast-mode-fmt.log` |
| `cc2api/` | `cargo test fast_mode` | 13 通过：12 个库测试及 1 个配置集成测试 | `/tmp/cc2api-fast-mode-focused.log` |
| `cc2api/` | `cargo test cch` | 40 通过，0 失败 | `/tmp/cc2api-fast-mode-cch.log` |
| `cc2api/` | `cargo test` | 767 通过，0 失败，3 个既有 PostgreSQL 用例忽略 | `/tmp/cc2api-fast-mode-full.log` |
| `cc2api/web/` | `npm run build` | TypeScript 与 Vite 构建通过 | `/tmp/cc2api-fast-mode-web.log` |
| 父仓 | `.venv/bin/python -m unittest discover -s orchestrator -p 'test_main.py' -k test_sync_creates_cc2api_account_with_fast_mode_disabled` | 1 通过 | `/tmp/cc2api-fast-mode-bench.log` |
| 两仓 | 受检范围 `git diff --check` | 通过 | 本会话工具结果 |
| 父仓 | `python3 .trellis/scripts/task.py validate .trellis/tasks/10-29-cc2api-fast-mode-account-policy` | 两份清单各 5 个有效条目，无截断警告 | 本会话工具结果 |

## 行为证据

- 新增两个 Rewriter 测试验证精确根字段、嵌套值与顺序、异常值、公共输入不变和允许时无删减。
- 新增实际 Gateway 矩阵覆盖 280/293、API/CC、stream 三态、Fast beta 有／无、允许／禁止和 count_tokens；校验正文、专用 beta 与已有 CCH。
- 后台测试先断言真实 detector 命中，再验证 identity-only 及 attribution；根键清理关闭时 Fast 策略仍有效，允许时身份旁路原始字节不变，Strip 的已有 CCH 按最终正文刷新。
- 原始 TCP 接收器验证明文及已有全部编码用例的真实 Content-Encoding、唯一 Content-Length、无 Transfer-Encoding、最终逻辑正文与 CCH。
- Messages 429 与 count_tokens 401 均覆盖允许→禁止、禁止→允许换号；双层压缩下每次出站匹配实际账号策略。
- 既有 OAuth 401 与两阶段 signature 压缩回归新增 Fast 输入断言；完整测试已执行这些用例，禁止字段在重试中不会恢复。

## 被测产品文件 SHA-256

```text
src/service/rewriter.rs f73c9256668cddb1bc7eb5b8ee18e7bd07f2bafcc6897a0c5ccace7f08658b8c
src/service/gateway.rs 3009e3f7ca00e815c43b15a7133aaf3d9ddd02e225dfb249358ab7a3b7c62ac4
src/model/account.rs cfb6ea6e342f527f6ac41b2d06b196d311b35e049b272df933af8a66c36257a3
web/src/components/Accounts.vue 011b3fefae0a4df50d60770664c5c5ee4443d7d8d1f62d40ac81d48e92000e06
```

## 已解决的验证过程问题

- 早次编译退出 101：测试模块未显式导入 Value／strip_empty_text_blocks；补齐导入后重跑通过。
- 早次定向测试退出 101：11 个库测试通过、1 个分类夹具失败。带 billing 的夹具没有命中窄 identity-only detector；现按真实识别规则分别构造两条旁路，并在发送前断言 detector 命中，最终全通过。
- 系统 Python 执行 bench 测试退出 1，原因是缺少 docker 模块；使用项目现有 `.venv/bin/python` 后通过，未安装或修改系统依赖。

## 限制

- 忽略项为既有 diagnostics、usage limits 与 profile settings 的 PostgreSQL 集成用例，分别要求独立临时数据库 DSN；本任务不改数据库合同。
- 本地合成测试不证明官方账号的 Fast 资格、速度或实际费用；未使用真实凭据、调用官方模型或部署。
- R13-02 的 API beta 合并边界保留原行为；没有把本轮允许账号的正文保留等同于该问题已修复。
