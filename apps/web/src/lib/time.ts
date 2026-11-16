/**
 * 按浏览者时区展示持久化时间，缺失或非法值保持可见。
 * @param value 接口保存的带时区时间戳。
 * @param includeTimeZone 是否在日期时间后显示 IANA 时区，默认显示。
 * @return 本地日期时间、可选的 IANA 时区，或未观测。
 */
export function formatLocalTime(value?: string | null, includeTimeZone = true): string {
  if (!value) return '未观测';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '未观测';
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  });
  const formatted = formatter.format(date);
  return includeTimeZone ? `${formatted} · ${formatter.resolvedOptions().timeZone}` : formatted;
}
