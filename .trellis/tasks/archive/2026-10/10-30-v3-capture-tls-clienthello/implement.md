# TLS ClientHello 实施计划

## 执行方式与所有权

- 用户明确要求子 agent 实施，并授权完成验证、提交推送、Actions 和部署。
- Collector 实施 agent：`images/sidecar/recorder.py`、新增 `images/sidecar/tls_clienthello.py`、sidecar 单元测试、`images/sidecar/Dockerfile`，以及可复用真实 TLS 验证入口。
- 入口／预览实施 agent：`orchestrator/main.py`、`account_runtime.py`、`pi_terminal.py`、`capture_artifacts.py`，`images/account/network-context.py`、`webui/app.js` 与对应测试；不编辑 Collector 所有权文件。
- 主会话：任务材料、集成复核、必要 spec、精确 Git／部署／线上核对；不回退其他工作。统一字段与元数据以 design.md 为准，细节收敛后同步文档。

## 步骤

1. [x] 固定 SDK 与已有六样本、官方 JA3 向量核对，完成入口／预览研究。
2. [x] 收敛 PRD、design、implement，配置 JSONL，展示完整 Brief 后按本次预授权启动。
3. [x] Collector 新增严格解析、私有追加 hook、JA3、HTTP 连接关联及固定错误回归。
4. [x] 入口传播 CAPTURE_CONTEXT、白名单与真实冻结版本；实现有界安全摘要／预览及共用 UI。
5. [x] 冻结各 agent 修改范围和验证摘要；主会话复核数据流、私有字段／版本／连接及旧证据保留。
6. [x] 运行真实 11.1.3 TLS＋HTTPS 关联验证与接口／共用渲染验证，记录命令、版本、断言和未覆盖边界；真实线上浏览器随部署验收。
7. [x] 通过 trellis-route 进入 Check-All，修复本范围内问题；更新权威 spec 与失效的 TLS 待办前置说明。
8. [x] 展示精确提交计划并按用户预授权推送；当前任务记录独立提交并完成 Close。
9. [x] 等本提交对应 Actions 成功，核同批镜像与实际源码，按 us SOP 部署及健康验收、旧镜像定向回收。
10. [x] 核对线上新 `tls_clienthello.jsonl`、版本／来源、JA3 与实际 Claude HTTP 连接关联，保留原工作和会话，记录完成事实。

## 验证范围

- Collector：解析向量／GREASE／合法空值／异常、原始内容与公开字段分离；现有 HTTP 阶段和额度回归。
- 网络与入口：network-context 实际子进程环境；普通／续聊冻结版本和 Projects/warmup 当前 source，停止／失败不删数据。
- API/UI：capture 摘要与两空间受限预览、总预算、半行／损坏／链接／恶意嵌套字段；三入口共用详情的安全显示与历史兼容。
- 集成：固定 11.1.3 真实 TLS1.2/1.3 与 HTTP keep-alive 连接键，独立本体解析和 JA3 复算；不以纯构造器或 mock 替代回调触发。
- 部署：匹配父/子 revision、源摘要、鉴权、Projects/warmup、SQLite、身份／计划／原工程保留；线上真实产物单列证据，不把合成结果算官方样本。

## 回退与边界

- 修改仅为兼容新增采集和摘要，捕获关闭不引入新握手或模型请求；采集失败不改转发行为。
- 不升级 cc2api TLS，不清理其他任务，不覆盖账号数据／历史证据；主会话记录当前 retained 基线与精确所有权。
- 需要部署排空时遵守已有作业／输入门禁，优先等待原轮收口；回退批次保留新旧证据，不恢复旧凭据。
