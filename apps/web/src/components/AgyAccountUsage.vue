<script setup lang="ts">
import { computed } from 'vue';
import { ArrowRight, ChevronRight } from '@/components/ui/icon';
import type { Account, AgyUsageWindow } from '../api';
import AgyQuotaRow from './AgyQuotaRow.vue';

const props = defineProps<{ account: Account; expanded?: boolean }>();
const quota = computed(() => props.account.usage_data?.platform_quota);
const groups = computed(() => quota.value?.groups?.items ?? []);
const models = computed(() => quota.value?.models?.items ?? []);
const gateway = computed(() => props.account.agy_request_usage);
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1, notation: 'compact' });
const gatewayPeriods = [{ key: 'five_hour', label: '近 5 小时' }, { key: 'seven_day', label: '近 7 天' }] as const;

/** 显示已记录 Token 及可观察的缺口。@param stats 单个窗口。@return 紧凑统计文案。 */
function tokenLabel(stats: AgyUsageWindow): string {
  if (stats.requests === 0) return '';
  if (stats.tokens == null) return 'Token 未记录';
  return `${number.format(stats.tokens)} Token${stats.partial_requests ? '（部分记录）' : ''}`;
}
</script>

<template>
  <section class="agy-account-usage" aria-label="反重力用量">
    <header>
      <h3>平台额度</h3>
      <router-link :to="{name:'requests',query:{account:String(account.id)}}">请求记录<ArrowRight :size="12" /></router-link>
    </header>
    <div class="agy-usage-section agy-platform-quota">
      <p v-if="!quota">未刷新</p>
      <p v-else-if="!groups.length && !models.length">{{ quota.status === 'unavailable' ? '读取失败' : '未提供额度' }}</p>
      <p v-else-if="quota.status === 'unavailable'" class="agy-quota-note">刷新失败 · 显示上次读数</p>
      <p v-else-if="quota.groups && quota.groups.observed_at_ms < quota.checked_at_ms" class="agy-quota-note">共享额度为上次读数</p>
      <p v-else-if="!groups.length && models.length">
        共享额度未提供<template v-if="!expanded"> · {{ models.length }} 个模型有读数</template>
      </p>
      <div v-if="groups.length" class="agy-quota-groups">
        <section v-for="group in groups" :key="group.windows[0]?.id" class="agy-quota-group" :aria-label="group.name">
          <h4>{{ group.name }}</h4>
          <ul class="agy-quota-windows">
            <AgyQuotaRow v-for="window in group.windows" :key="window.id" :reading="window"
              :label="window.period === '5h' ? '5 小时' : '每周'" />
          </ul>
        </section>
      </div>
      <details v-if="expanded && models.length" class="account-capability-details" :open="!groups.length">
        <summary>按模型查看（{{ models.length }}）<ChevronRight :size="14" /></summary>
        <p v-if="quota?.models && quota.models.observed_at_ms < quota.checked_at_ms" class="agy-quota-note">上次读数</p>
        <ul class="agy-quota-windows agy-model-quotas">
          <AgyQuotaRow v-for="model in models" :key="model.model" :reading="model" :label="model.model" />
        </ul>
      </details>
    </div>
    <div v-if="expanded" class="agy-usage-section">
      <h3>网关用量</h3>
      <div v-if="gateway" class="agy-gateway-windows">
        <div v-for="period in gatewayPeriods" :key="period.key">
          <span>{{ period.label }}</span>
          <div class="agy-gateway-reading">
            <strong>{{ number.format(gateway[period.key].requests) }}</strong> 请求
            <small v-if="tokenLabel(gateway[period.key])">{{ tokenLabel(gateway[period.key]) }}</small>
          </div>
        </div>
      </div>
      <p v-else>暂不可用</p>
    </div>
  </section>
</template>
