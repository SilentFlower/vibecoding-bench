# Flow 抓包 Session 一致性核对

## 样本

- 来源：本地 `data/flows/*/*/*/http_capture.jsonl`。
- 端点：`/v1/messages?beta=true`。
- 总数：235 条。
- 仅解析 `X-Claude-Code-Session-Id` 和 `metadata.user_id.session_id` 后比较是否相等；未记录或输出完整 session、Authorization、请求正文。

## 结果

| 类型 | 数量 | 一致 | 不一致 |
| --- | ---: | ---: | ---: |
| 正常请求 | 222 | 222 | 0 |
| warmup probe | 13 | 12 | 1 |
| 合计 | 235 | 234 | 1 |

warmup probe 的判定形状为：`max_tokens=1`、无 tools、单条 user message、字符串内容长度为 5。唯一不一致样本使用 Claude Code `2.1.173` 和 Haiku，header/body session 均为 36 字符但短 hash 不同。

## 结论

- 正常 Claude Code message 请求的协议基线是 header/body session 一致。
- warmup probe 存在官方不一致样本，不能无条件把所有 `/v1/messages` header 改成 body session。
- 本任务应只在账号级 session 池实际把 body 从真实 session 改为不同 upstream session 时覆盖 header。
- Gateway warmup 拦截发生在账号 admission 和 session 池解析之前，该特殊路径不需要进入池映射。
