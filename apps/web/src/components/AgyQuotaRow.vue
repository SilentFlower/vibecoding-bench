<script lang="ts">
import type { AgyQuotaReading } from '../api';

const percent = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1, style: 'percent' });
const amount = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1, notation: 'compact' });
const dateTime = new Intl.DateTimeFormat('zh-CN', {
  month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
});

/** 本地化上游重置时刻。@param resetAt 上游时刻。@return 重置文案，缺失时为空。 */
function resetLabel(resetAt?: string | null): string {
  if (!resetAt) return '';
  const date = new Date(resetAt);
  if (!Number.isFinite(date.getTime())) return '';
  return date.getTime() <= Date.now() ? '已到重置时间' : `${dateTime.format(date)} 重置`;
}
</script>

<script setup lang="ts">
import { computed } from 'vue';
import { usageBarColor } from '../lib/subscription';

const props = defineProps<{ label: string; reading: AgyQuotaReading }>();
const used = computed(() => props.reading.remaining_fraction == null ? null : 1 - props.reading.remaining_fraction);
const reset = computed(() => resetLabel(props.reading.reset_at));
</script>

<template>
  <li class="agy-quota-window">
    <span class="agy-quota-label">{{ label }}</span>
    <span v-if="reading.remaining_fraction != null && used != null" class="agy-quota-value">
      已用 {{ percent.format(used) }} · <strong>剩余 {{ percent.format(reading.remaining_fraction) }}</strong>
    </span>
    <strong v-else-if="reading.remaining_amount != null" class="agy-quota-value">剩余 {{ amount.format(reading.remaining_amount) }}</strong>
    <span v-else class="agy-quota-value">额度未知</span>
    <small v-if="reset" class="agy-quota-reset">{{ reset }}</small>
    <div v-if="used != null" class="usage-window-bar" aria-hidden="true">
      <i :class="usageBarColor(used * 100)" :style="{width: used * 100 + '%'}" />
    </div>
  </li>
</template>
