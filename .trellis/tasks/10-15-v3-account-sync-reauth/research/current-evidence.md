# 当前证据

## 同步断点

- `orchestrator/account_runtime.py:1740`：identity_import 要求 runtime/identity.json，文件不存在就提示先完成 CLI 任务。
- `images/sidecar/recorder.py:707`：仅完整 /v1/messages body 的 request hook 写身份文件。
- `images/account/network-context.py:167`：passthrough 使用原始字节 relay，不执行 Recorder。
- 只读线上核对：目标账号未绑定 cc2api、环境代次为 2、identity.json 不存在；其固定 HOME 已有 64 位 userID 和 machineID。未记录真实字段值。
- `orchestrator/main.py:10803`：环境页也只判断同一个观察文件，所以展示同样过时。

## 官方身份来源实证

官方本地二进制版本为 2.1.293，SHA256 为 8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978。嵌入请求构造调用持久 userID 读取函数来填 metadata.user_id.device_id；该函数只接受 64 位小写十六进制。machineID 有独立的生成与读取路径。

以合成 userID 与不同的 machineID 运行实际 CLI，在 network=none 容器内访问本地 SSE 服务。2 条模型请求的 device_id 均匹配 userID，账号 UUID 与合成登录身份一致；结果见 official-cli-identity-result.json。此结论仅覆盖当前版本，不推定其他版本映射不变。

## 重授权

- `orchestrator/main.py:5316`：commit_bound 校验原绑定、登录身份及环境代次，提交前落盘操作记录；通过 import_credentials／import_status 确认远端结果。
- `orchestrator/account_runtime.py:1518`：finish_bound_login 把权威 AT/RT 写管理 profile，主 HOME 经 sync_credentials 仅发布 AT；保留原 userID。
- `orchestrator/main.py:9149`：有 binding_id 才调用 commit_bound；未绑定走本地保存。
- `webui/app.js:1201`：已有 credentials_synced 成功分支，但本地重授权未明确提示尚未绑定。
- 已运行 Python test_login_reauth 18 项与 Rust login_import 4 项，全部通过；未做真实账号重授权，也未改变生产凭据。

## 任务边界

用户已说明付款时使用链式代理且出口相同；不再基于付款出口不同解释封禁。本任务只处理同步和重授权的产品正确性，不尝试规避或解除上游账号限制。原有 Flower 升级与其它任务文件保留。
