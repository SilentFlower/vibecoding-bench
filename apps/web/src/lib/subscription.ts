/** 按真实套餐元数据生成标签。@param type 原始类型。@param tier 真实分级。@return 套餐名称。 */
export function subscriptionLabel(type?: string | null, tier?: string | null): string {
  const key = type?.trim().toLowerCase();
  if (key === 'ultra' || (key === 'max' && tier === 'default_claude_max_20x')) return 'Ultra';
  return ({ pro: 'Pro', max: 'Max', team: 'Team', enterprise: 'Enterprise' } as Record<string, string>)[key ?? ''] ?? (type || '套餐未知');
}

/** 区分官方空窗口与未知读数。@param data 官方用量对象。@param fallback 有效窗口的文案。@return 5 小时说明。 */
export function fiveHourLabel(data: { five_hour?: unknown } | null | undefined, fallback: string): string {
  return data?.five_hour === null ? '当前未返回5小时窗口' : fallback;
}

/** 额度进度条的语义色调，样式按 data-tone 取 token。 */
export type UsageBarTone = 'success' | 'warning' | 'danger';

/** 按已用比例统一额度进度条色调。@param pct 已用百分比。@return 语义色调：≥80 危险，≥50 警示，否则成功。 */
export function usageBarTone(pct: number): UsageBarTone {
  if (pct >= 80) return 'danger';
  if (pct >= 50) return 'warning';
  return 'success';
}
