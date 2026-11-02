# R3-02／04 技术研究结论

## 证据

原研究round3的重复beta和query冻结案例已核对，当前Gateway逻辑仍存在。原生query新核对详见native-query-evidence.json：592条不同Messages均只有一个beta=true，280七份.flow逐条与JSONL一致；293远端SSH连接超时，原件未读，裸路径报告不等于query证据。全部已读取请求无Content-Encoding，Accept-Encoding只是响应编码协商。

## 重复beta最小方案

当前extract_headers只有count_tokens与普通Gateway两个入口。已有pub(crate) merge_anthropic_beta(required:&str,incoming:&str)->String，Gateway已显式导入，按逗号拆分、trim、精确去重并保留首次顺序；无需改变可见性或Rewriter。

对beta专用headers.get_all("anthropic-beta").iter()折叠合并。同名值迭代按插入顺序；不要依赖普通HeaderMap::iter的整体顺序。其它头继续原覆盖与to_str失败跳过语义。有效空beta与完全不可转字符串的beta保持差别，不顺手新增UA策略。

合并后仍按既有账号1M/Fast白名单、版本、safeguard/title/后台精确画像处理。API普通Messages本来不合入普通客户端1M，不借此扩大能力；额外未知token仍保持首次顺序，不做全量排序。

## URL最小方案

对requires_upstream_beta_query命中的精确路径，把所有解码后精确同名beta归一成一个beta=true；无beta则末尾追加；有beta可保留首次出现位置并去掉后续同名项。键比较正确处理一次百分号解码，不把原query全部解析后重编码。

其它query原始片段、编码、顺序和重复值保留；其它端点不扩大。count_tokens专用URL本来固定唯一beta=true，保持原合同。研究中的synthetic_client_id是合成键，不新增该名字的黑名单；样本未出现其它键不等于未知扩展非法。

## 验证

实际Gateway+loopback覆盖280/293 CC允许/禁止1M的两行交换、重叠空段/空白/大小写头名/相似日期、Fast开关、293safeguard/title、API画像不变、独立count_tokens、UA/request-id/Auth旧语义。构造前移除profile_request自动beta，再HeaderMap.append。

URL覆盖缺省/true/false/空/重复混合/编码同名beta、其它query原始编码与重复保真、非目标路径和count_tokens；不能只测HashMap或直接Rewriter。保留R2字段清理/Session、CCH和stream三态。产品共享Gateway，等R2交接后顺序实施。
