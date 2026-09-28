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

- [x] 确认可用环境；bench 构建成功后部署并完成远程抓包。
- [x] 收集 Opus 5.5 单轮/工具/多轮/continue，并补充 Sonnet 5、Fable 5.1、Haiku、Opus 4.8、Sonnet 4.5；Opus 5 明确标记为本轮未观察。
- [x] 比较 260/280 的 identity、header/body、CCH、cc_version、bootstrap、telemetry。
- [x] 补充脱敏差异矩阵与最小 synthetic fixture，原始 flow/正文保持忽略。
- [x] 必要证据齐备后进入 cc2api 默认画像改动。

## 3. cc2api

- [x] 基于抓包新增 2.1.280 画像与 Opus 5.5 精确子画像，保留旧画像。
- [x] 对齐 rewriter/gateway/telemetry/oauth/bootstrap/访问策略消费者。
- [x] 更新 settings 默认、组合迁移、账号 identity 和管理页。
- [x] 补充精确模型、参数保留、thinking/tool_choice 与旧画像隔离回归。
- [x] 补充新库、旧默认、自定义任一组合成员、显式回滚与幂等迁移回归。
- [x] 在 cc2api 执行 `cargo fmt --check`、`cargo test`；完整测试含 CCH 时不重复该组。
- [x] 在 cc2api/web 执行 `npm run build`。

## 4. 联合验收

- [x] 真实样本复算 CCH、cc_version、beta/body 顺序；六类模型的 billing 请求全部命中。
- [x] 验证 API/原生 CLI 的 Opus 5.5 行为及其他模型回归。
- [x] 完成 Check-All，区分真实验证、单测和仅审查部分。
- [x] 更新协议规范，准备两仓精确 diff 与提交说明。
- [x] Git/镜像/生产发布按就绪结果执行对应流程，保留回滚证据。

## 风险位置

`version_profile.rs` 的旧常量复制、`db.rs` 的自定义组合保护、bench 页面覆盖优先级，以及 `rewriter.rs` 的 Opus 5.5 thinking/tool_choice 语义是重点审查处。

## 2026-09-23 当前进度

bench 的 9 个代码/配置/文档文件已完成；worker 镜像 `vibebench-worker:check-2.1.280` 构建成功，真实 entrypoint 登录模式启动通过，node 用户执行版本为 2.1.280。Dockerfile 已移除吞掉 npm 安装失败的 `|| true`。

59 项后端测试通过；shell、JS、两份 Compose 与 HTML 候选/绑定检查通过。旧 run/排队快照和临时 worker 使用新配置的行为由现有回归覆盖。

离线 CLI 检查确认精确模型、精确模型 `[1m]` 和 `opus[1m]` 均解析为 `claude-opus-5-5`，后两者附带 1M beta。该检查用固定 400 响应结束，不代表真实推理或 OAuth wire 验证。

bench 业务提交 `23b0150` 与任务进度提交 `d0219a9` 已推送；GitHub Actions run
`35760335940` 成功构建三个镜像。远程 bench 已部署 tag `d0219a9`，worker 与
orchestrator 实测均为 2.1.280，HTTP 健康检查为 200。

真实抓包和原生二进制调试确认 CCH seed 不变；2.1.280 会清空所有精确字符串 model
字段，包括 advisor 工具里的嵌套 model，并删除顶层 max_tokens。六类模型样本按该规则
全部复算命中。Opus 5.5 为 128000/adaptive/max，Fable 5.1 初始主请求不再自动带
fallback。cc2api 已加入独立 2.1.280 画像、synthetic fixture、默认迁移和管理页选项；
首轮 520 项回归暴露的 17 项均为旧默认断言，更新后 520 项通过，新增定向 CCH、画像、
迁移测试也已通过。最终 `cargo fmt --check`、完整 `cargo test`（526 项 lib、53 项集成）
和前端构建均通过；Check-All 发现的 count_tokens fallback beta 路由边界已修复，并新增定向
回归通过。原生 CLI 的 Opus 5.5 单轮、工具、多轮与 continue 由真实抓包验证，API 参数路径
由最终回归覆盖；Sonnet 5、Fable 5.1、Haiku、Opus 4.8 与 Sonnet 4.5 样本全部复算命中。

bench 阶段完成 full Check-All：当前变更未发现 CHK/FBK 问题；DOC-001 已将两份部署规范的当前默认版本同步至 2.1.280。三件套与假设仅完成 bench 范围验证，cc2api 协议、迁移及联合验收仍未验证，整个任务保持进行中。

cc2api 阶段完成 full Check-All：除已闭环的 count_tokens fallback beta 边界外，最终变更未发现
剩余 CHK/FBK；DOC-001 已同步最终回归和检查状态。真实抓包与复算、单元/集成测试、构建验证
已分别记录。

cc2api 提交 `61e9721` 与父仓 gitlink/协议规范提交 `a0bb346` 已推送。cc2api GitHub Actions
run `35773016381` 和父仓 run `35773103555` 均成功。生产容器已部署 `sha-61e9721` 对应的
不可变镜像 digest `sha256:5471b9dd7baeba6f65e6a6794a2f7db20d36231aef4a646a2fa627b1ab9a7551`；
内外网 HTTP 均为 200，容器 running、重启次数 0，近期 timeout/panic/error 计数为 0。

部署前已生成 SQLite 在线备份和 Compose 备份。迁移后 DB 完整性为 ok，默认画像为 2.1.280，
允许范围为 `2.1.89-2.1.280`，4 个账号的 canonical env 均为 2.1.280 和目标 build time。
远端 system-role 列表属于管理员自定义值，自动迁移按约定保留；依据 Opus 5.5 抓包中的
`messages[].role=system`，发布时显式追加 `claude-opus-5-5` 并保留原列表。加载配置的短暂
重启切断了当时一个流式连接，Claude Code 自动非流式重试；重启后连续健康检查和日志核对正常。

下一步：无；任务可完成，后续常规运行监控沿用现有运维流程。
