# 技术设计

## 数据流

1. handle_request_inner 完成解码并解析原始 JSON 后，在会话封禁与正文策略前冻结原始 session。
2. 正文来源复用 extract_session_id_from_body。缺省时从原始 HeaderMap 读取唯一会话头，避免 HashMap 合并重复头。正文值优先；诊断边界校验失败时保持未知。
3. 诊断 helper 将有效完整值写入 TraceContext.request.original_session_id: Option<String>，后续会话映射仅影响原有尝试摘要。
4. 字段使用 serde default 兼容旧 JSON，保持可空语义。复用 request_diagnostics.summary_json、既有异步写入、分页和详情读取，沿用原 SQL 与表结构。
5. DiagnosticRequest TypeScript 接口增加可选可空字段；列表增加列并复用复制交互，详情概览展示完整值。长值受控换行或省略，复制始终取完整值。
6. 请求版本复用 last_attempt.profile_version。现有 prepare_observation 从实际账号画像取得版本，prepare_native_attempt 用实际 observation.source_version 覆盖。在现有“模型 / 转发方式”列中显示“转发方式 · 完整版本”，版本口径为末次尝试；详情沿用每次尝试版本。
7. 前端复用现有 tokens.output_tokens / duration_ms 计算平均 TPS，公式为 output_tokens * 1000 / duration_ms。仅 outcome=success、partial=false 且字段为有效有限非负 token 数和正时长时输出一位小数；其余保持未知。保留真实零 token。列表使用末次尝试，详情使用当前尝试；复用一个计算入口并在提示中注明包含首输出等待。
8. formatLocalTime 增加默认包含时区的可选参数，列表时间显式关闭时区文字；其它调用沿默认展示。datetime 属性仍保留原始时间。

## 边界与兼容

- 只在已有已鉴权 /v1/messages 根诊断作用域内记录；count_tokens、Hello、遥测沿原链路。
- 保存值不 trim、不截断；要求非空白、无控制字符、UTF-8 字节长度 <=256。重复头不构造合并值。正文有提取结果时按正文优先，不以头值替换异常正文标识。
- 普通 API 未携带会话时为 None。上游 SDK 生成的 session 不作为客户端原始值。
- 请求版本采用实际尝试记录。账号基础版本、客户端 UA 和当前配置默认版本均不作为列表缺失值的填充来源。
- info/debug 均保存原始会话。依据用户要求，在默认匿名摘要规范中增加唯一明确例外；继续保持尝试会话散列以及日志和正文白名单。
- 原始值为管理端记录内容，采用 Vue 文本插值和既有管理鉴权。记录保留期与有界异步队列保持七天及 16 KiB 上限。
- 旧 JSON 读取为 None。旧程序忽略新增 JSON 字段；回退程序继续处理旧表结构。旧记录以“未提供”展示。

## 受影响位置

- services/gateway/src/model/request_diagnostics.rs：根字段及兼容性。
- services/gateway/src/service/diagnostics.rs：冻结方法及定向测试。
- services/gateway/src/service/gateway.rs：入站采集点、现有测试构造和真实链路回归。
- services/gateway/src/store/diagnostics_store.rs：测试构造与持久化验证。
- apps/web/src/api.ts、components/RequestDiagnostics.vue、lib/time.ts、必要的 request-design.css：类型、时间格式与展示。
- deploy/flower2api/verify_management_ui.py：合成页面验证。
- .trellis/spec/gateway/backend/settings-database.md、.trellis/spec/web/frontend/ui-guidelines.md、frontend-guidelines.md：新合同。

## 风险与回退

- 入口冻结位置决定本地拒绝是否带原始会话，测试须覆盖正文策略前采集。
- 历史数据只保存散列，原始会话缺失采用明确空态。
- 原先“完整 session 不持久化”的规范须同步新增原始字段例外。
- 回退为撤销新增采集与展示提交；持久 JSON 对旧程序兼容，数据沿原保留期清理。
