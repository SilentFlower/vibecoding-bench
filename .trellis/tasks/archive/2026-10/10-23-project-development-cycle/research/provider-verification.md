# 外接需求方模型连通验证

## 用户指定配置

- 服务：`https://ai.flower-cli.com/v1`。
- 协议：OpenAI 兼容 Chat Completions；请求路径 `/chat/completions`。
- 主模型：`gemini-3-flash-agent`。
- 备用模型：`deepseek-flash`，用于主模型额度不足、限流或暂时不可用。
- 凭据仅保存在 `.deploy/project-development-cycle/requester.env`，目录 0700、文件 0600，已核实被 Git 忽略。文档不记录凭据值。

## 实测结果

已按用户提供的接口与凭据进行最小请求，每个模型各生成一次，未发送项目源码、业务对话或 Claude 账号信息。

| 模型 | 模型列表 | 生成状态 | 返回内容验证 | 生成耗时 | 请求报告的 token |
| --- | --- | --- | --- | --- | --- |
| gemini-3-flash-agent | GET /models 200，存在指定名称 | POST /chat/completions 200 | 正常 choices/message，内容为 OK，finish_reason=stop | 4.072 秒 | 输入 259／输出 63／总计 322 |
| deepseek-flash | GET /models 200，存在指定名称 | POST /chat/completions 200 | 正常 choices/message，内容为 OK，finish_reason=stop | 2.663 秒 | 输入 35／输出 12／总计 47 |

脱敏回执：

- `.deploy/project-development-cycle/provider-probe.json`。
- `.deploy/project-development-cycle/fallback-probe.json`。

上述两次最小生成请求只用了 `model`、`messages`、`max_tokens=128` 和 `stream=false`，未启用额外工具或结构化输出扩展。其证据不覆盖真实完整任务的上下文长度、成本和缓存效果；后续合成 JSON 动作另列如下。

## 接入边界

- 本地配置和两个模型的最小连通已经完成。外部需求方现已接入完整任务循环；主备降级、原会话追问、失败修复与恢复已由隔离 HTTPS 替身、真实 SQLite 和 Docker 验证。该证据不代表真实模型业务质量或真实缓存收益。
- 不通过耗尽真实余额验证降级；主模型失败、备用成功和主备均失败等分支使用受控模拟验证，再在已授权试点观察实际行为。
- 接口格式参考 [OpenAI Docs：Create chat completion](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。第三方模型、认证和可用性以本次实际接口响应为准。

## 实际 JSON 动作与原会话交接

在用户授权的最小连通范围内，另做一次不含真实项目源码或账号材料的合成协议请求。指定接口返回合法需求方动作，经正式客户端解析、持久化和原生消息驱动，在同一个隔离开发者会话被确认消费。请求数 1，真实 Claude 调用 0；回执为 `.deploy/project-development-cycle/real-action-probe.json`，不包含密钥。

页面动态配置、三个模型的有序降级、密钥替换和恢复环境值，另由本机 HTTPS 替身与真实浏览器/API/SQLite验证。真实供应商的多模型业务质量、成本和缓存收益仍未评估。

## 美国 v3 部署核验

用户确认精确提交计划并追加部署授权后，已部署 `ci-39950873699-1`。指定地址及两个模型通过受鉴权配置接口保存，密钥仅在服务器私有设置中持久化，上传临时副本已删除；正式镜像重新读取与真实浏览器空密钥保存、刷新均通过。服务容器 `GET /models` 能读取两个指定模型，部署验收未发送生成请求。

正式镜像的 66 个源码文件与业务提交一致，内容为 30 个就绪项目／36 个完整任务，70 个待准入项目如实保留。旧项目批次、账号身份、17,003 个持久文件和 9 个无关容器核对不变，停机备份已通过隔离恢复。回执保存在忽略的 `.deploy/project-development-cycle/deployment/`：`verification.json`、`browser-result.json`、`provider-connectivity.json`、`postcheck.json`。
