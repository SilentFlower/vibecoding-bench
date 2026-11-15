<script setup lang="ts">
import { computed } from 'vue';
import { InfoTooltip } from '@/components/ui/controls';
import type { WindowUsageStats } from '../api';

const props = defineProps<{
  stats?: WindowUsageStats | null;
  label: string;
}>();

/** 当前统计是否仍属于未到期的额度周期或最近滚动时间段。 */
const current = computed(() => {
  const stats = props.stats;
  if (stats?.basis === 'quota' && Date.parse(stats.ends_at) <= Date.now()) return null;
  return stats;
});

/** 提示费用的覆盖范围，帮助判断能否与官方百分比对照。 */
const description = computed(() => {
  const stats = current.value;
  if (!stats) return '尚未提供本地用量统计';
  const range = stats.basis === 'quota' ? '当前额度周期' : `最近 ${props.label}`;
  const notes = [`${range}内经过网关的请求，费用按模型 API 单价折算`];
  if (stats.unpriced_requests) notes.push(`${stats.unpriced_requests} 次请求费用未知`);
  if (stats.partial_requests) notes.push(`${stats.partial_requests} 次请求用量不完整`);
  return notes.join('；');
});

/**
 * 紧凑显示请求数或 Token，不改变用于汇总的原始精度。
 * @param value 原始数量。
 * @return K／M 缩写或完整整数。
 */
function compact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
  return String(value);
}
</script>

<template>
  <div v-if="current" class="usage-stats">
    <InfoTooltip :label="`查看${label}完整费用统计`" content-class="usage-cost-bubble">
      <template #trigger><span class="usage-stats-line"><template v-if="current.basis === 'rolling'">最近 {{ label }} · </template>{{ compact(current.requests) }} 请求 · {{ compact(current.tokens) }} Token · <template v-if="current.requests > 0 && current.unpriced_requests === current.requests">费用未知</template><template v-else>{{ current.unpriced_requests || current.partial_requests ? '已知' : '折算' }} ${{ current.cost_usd.toFixed(2) }}</template><template v-if="current.estimated_total_cost_usd != null"> · 预计总费用 ${{ current.estimated_total_cost_usd.toFixed(2) }}</template></span></template>
      <header><span>{{ label === '5h' ? '5 小时' : label === '7d' ? '7 天' : label }}用量统计</span><small>网关记录</small></header>
      <dl class="usage-bubble-grid">
        <div><dt>请求数</dt><dd>{{ current.requests.toLocaleString('zh-CN') }}</dd></div>
        <div><dt>Token</dt><dd>{{ current.tokens.toLocaleString('zh-CN') }}</dd></div>
        <div><dt>{{ current.unpriced_requests || current.partial_requests ? '已知费用' : '折算费用' }}</dt><dd>{{ current.requests > 0 && current.unpriced_requests === current.requests ? '费用未知' : (current.unpriced_requests || current.partial_requests ? '已知 $' : '折算 $') + current.cost_usd.toFixed(2) }}</dd></div>
        <div v-if="current.estimated_total_cost_usd != null"><dt>预计总费用</dt><dd>${{ current.estimated_total_cost_usd.toFixed(2) }}</dd></div>
      </dl>
      <p>{{ description }}</p>
      <p v-if="current.estimated_total_cost_usd != null" class="usage-bubble-estimate">预计总费用由当前费用与官方用量比例估算。</p>
    </InfoTooltip>
  </div>
  <p v-else class="usage-record-start">统计待更新</p>
</template>
