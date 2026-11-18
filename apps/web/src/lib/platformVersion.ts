const versionPattern = /^v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;
const prefix = '平台版本：';

/** 校验运行时提供的规范平台版本。@param value 实际接口字段。@return 规范版本或未知值。 */
export function parsePlatformVersion(value: unknown): string | null {
  // JavaScript的结束锚点也匹配末尾换行之前，须核对匹配范围覆盖完整字符串。
  return typeof value === 'string' && versionPattern.exec(value)?.[0] === value ? value : null;
}

/**
 * 从已验签说明首行提取展示版本。
 * @param changes 已验签的普通文本说明。
 * @return 规范版本；旧发行返回空值。
 */
export function releaseVersion(changes: string): string | null {
  const first = changes.split('\n')[0] ?? '';
  const version = first.startsWith(prefix) ? first.slice(prefix.length) : '';
  return parsePlatformVersion(version);
}

/**
 * 展示变更正文，正式版本首行由独立标题呈现。
 * @param changes 已验签说明。
 * @return 原说明或去掉受控版本首行的正文。
 */
export function releaseNotes(changes: string): string {
  return releaseVersion(changes) ? changes.slice(changes.indexOf('\n') + 1).trim() : changes;
}
