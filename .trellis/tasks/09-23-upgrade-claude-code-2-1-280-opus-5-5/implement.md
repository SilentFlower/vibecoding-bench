# 实施计划

## 1. bench

- [x] 读取 before-dev 对应规范与目标类型/函数，更新默认版本和 Opus 5.5 候选。
- [x] 核对普通、批量、养号、抓包、continue、quota、refresh、login 版本传参。
- [x] 隔离环境运行目标 CLI `--version` 并验证模型解析。
- [x] 运行 `PYTHONPATH=orchestrator /tmp/vibebench-280-venv/bin/python -m unittest orchestrator.test_main`：59 项通过。
- [x] 运行 `bash -n images/worker/entrypoint.sh`、`node --check webui/app.js`。
- [x] 两份 Compose 执行 `config --quiet`；远程配置使用测试路径满足必填变量。
- [x] 记录新/旧 run 快照回归及 bench 可用于采集的状态。

## 2. 抓包

- [ ] 确认可用环境；必要部署走具体计划。
- [ ] 收集 Opus 5.5 单轮、工具、多轮、continue，核对其他现有模型和辅助请求。
- [ ] 比较 260/280 的 identity、header/body、CCH、cc_version、bootstrap、telemetry。
- [ ] 补充脱敏差异矩阵与最小 fixture，区分未观察项。
- [ ] 必要证据齐备才进入 cc2api 默认画像改动；否则记录具体缺口。

## 3. cc2api

- [ ] 基于抓包新增 2.1.280 画像与 Opus 5.5 精确子画像，保留旧画像。
- [ ] 对齐 rewriter/gateway/telemetry/oauth/bootstrap/访问策略消费者。
- [ ] 更新 settings 默认、组合迁移、账号 identity 和管理页。
- [ ] 补充精确模型、参数保留、thinking/tool_choice 与旧画像隔离回归。
- [ ] 补充新库、旧默认、自定义任一组合成员、显式回滚与幂等迁移回归。
- [ ] 在 cc2api 执行 `cargo fmt --check`、`cargo test`；完整测试含 CCH 时不重复该组。
- [ ] 在 cc2api/web 执行 `npm run build`。

## 4. 联合验收

- [ ] 真实样本复算 CCH、cc_version、beta/body 顺序。
- [ ] 验证 API/原生 CLI 的 Opus 5.5 行为及其他模型回归。
- [ ] 完成 Check-All，区分真实验证、单测和仅审查部分。
- [ ] 更新协议规范，准备两仓精确 diff 与提交说明。
- [ ] Git/镜像/生产发布按就绪结果执行对应流程，保留回滚证据。

## 风险位置

`version_profile.rs` 的旧常量复制、`db.rs` 的自定义组合保护、bench 页面覆盖优先级，以及 `rewriter.rs` 的 Opus 5.5 thinking/tool_choice 语义是重点审查处。

## 2026-09-23 当前进度

bench 的 9 个代码/配置/文档文件已完成；worker 镜像 `vibebench-worker:check-2.1.280` 构建成功，真实 entrypoint 登录模式启动通过，node 用户执行版本为 2.1.280。Dockerfile 已移除吞掉 npm 安装失败的 `|| true`。

59 项后端测试通过；shell、JS、两份 Compose 与 HTML 候选/绑定检查通过。旧 run/排队快照和临时 worker 使用新配置的行为由现有回归覆盖。

离线 CLI 检查确认精确模型、精确模型 `[1m]` 和 `opus[1m]` 均解析为 `claude-opus-5-5`，后两者附带 1M beta。该检查用固定 400 响应结束，不代表真实推理或 OAuth wire 验证。

cc2api 尚未修改。抓包阶段缺少可用环境：本地数据库无账号，仅存凭据已过期；文档中远程实例的 SSH 主机密钥与 known_hosts 不符，连接已按默认校验拒绝。已请求当前实例 SSH 信息或已有 280 抓包 run ID。未修改 known_hosts、真实账号或生产服务。

bench 阶段完成 full Check-All：当前变更未发现 CHK/FBK 问题；DOC-001 已将两份部署规范的当前默认版本同步至 2.1.280。三件套与假设仅完成 bench 范围验证，cc2api 协议、迁移及联合验收仍未验证，整个任务保持进行中。

下一步：取得有效抓包入口，完成真实协议矩阵，再实施 cc2api 默认画像、模型与迁移。
