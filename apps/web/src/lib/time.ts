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

/**
 * 只展示本地时分秒，用于同一次操作内的步骤时间。
 * @param value 接口保存的带时区时间戳。
 * @return 本地 HH:MM:SS，缺失或非法值返回「—」。
 */
export function formatLocalClock(value?: string | null): string {
  const date = value ? new Date(value) : null;
  if (!date || !Number.isFinite(date.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(date);
}

/**
 * 紧凑展示本地月日与时分，用于摘要格等窄位；完整时间放在 title 中。
 * @param value 接口保存的带时区时间戳。
 * @return 本地 MM/DD HH:MM，缺失或非法值返回「—」。
 */
export function formatLocalShort(value?: string | null): string {
  const date = value ? new Date(value) : null;
  if (!date || !Number.isFinite(date.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date);
}
