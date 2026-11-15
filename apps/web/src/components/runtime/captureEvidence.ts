/** 保持原TLS展示白名单，附加内部字段不进入可视详情。@param entry 公开观测。@return 安全展示对象。 */
export function tlsFields(entry: Record<string,unknown>): Record<string,unknown> {
  const keys = ['direction','client_connection_id','capture_context','capture_context_status','parse_status','target_status','legacy_version','supported_versions','cipher_suites','signature_algorithms','supported_groups','ec_point_formats','sni','fields_incomplete'];
  const value = Object.fromEntries(keys.filter(key => key in entry).map(key => [key,entry[key]]));
  const objects = (key: string) => Array.isArray(entry[key]) ? entry[key].filter(item => item && typeof item === 'object') as Record<string,unknown>[] : [];
  value.extensions = objects('extensions').map(item => ({type:item.type,length:item.length}));
  value.key_share = objects('key_share').map(item => ({group:item.group,key_exchange_length:item.key_exchange_length}));
  value.alpn_protocols = objects('alpn_protocols').map(item => item.text ?? '非文本协议');
  const ja3 = entry.ja3 && typeof entry.ja3 === 'object' ? entry.ja3 as Record<string,unknown> : {};
  value.ja3 = {string:ja3.string,md5:ja3.md5}; return value;
}

