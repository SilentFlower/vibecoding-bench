<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { api, type SchedulingDetail, type SchedulingSession, type SchedulingSessions } from '../api';
import { schedulingReasonLabel } from '../lib/scheduling';
import { Button } from '@/components/ui/button';
import { ChoiceSelect, SearchInput, Pagination } from '@/components/ui/controls';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { NoticeStrip } from '@/components/ui/notice-strip';
import { EntityBlock } from '@/components/ui/entity-card';
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const props = defineProps<{ open: boolean; accountId: number; accountName: string; embedded?: boolean; antigravity?: boolean }>();
const emit = defineEmits<{ 'update:open': [value: boolean] }>();
const detail = ref<SchedulingDetail | null>(null);
const sessions = ref<SchedulingSessions | null>(null);
const error = ref('');
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
watch(pageSize, () => { page.value=1;syncVisibility(); });
const state = ref('all');
const prefix = ref('');
const appliedPrefix = ref('');
const rangeMs = ref(300000);
const localNow = ref(Date.now());
const receivedAt = ref(0);
let generation = 0;
let controller: AbortController | null = null;
let refreshTimer: ReturnType<typeof setInterval> | null = null;
let clockTimer: ReturnType<typeof setInterval> | null = null;

const summary = computed(() => detail.value?.summary);
const estimatedServerNow = computed(() => (detail.value?.snapshot.observed_at_ms ?? 0) + Math.max(0, localNow.value - receivedAt.value));
const stale = computed(() => Boolean(error.value) || (receivedAt.value > 0 && localNow.value - receivedAt.value > 12000));
const nextLabel = computed(() => {
  if (!summary.value || stale.value) return '待刷新';
  const next = summary.value.next_send_at_ms;
  if (props.antigravity && !summary.value.capacity.can_queue && (next == null || next <= estimatedServerNow.value)) return schedulingReasonLabel(summary.value.capacity.reason);
  if (props.antigravity && (next == null || next <= estimatedServerNow.value)) return '当前可接单';
  if (next == null) return '未配置发送间隔';
  const remaining = next - estimatedServerNow.value;
  return remaining > 0 ? `${(remaining / 1000).toFixed(1)} 秒后（预计）` : '已到预计时刻，待刷新';
});
const chartStart = computed(() => (detail.value?.snapshot.observed_at_ms ?? 0) - rangeMs.value);
const chartEnd = computed(() => (detail.value?.snapshot.observed_at_ms ?? 0) + 60000);
const events = computed(() => detail.value?.snapshot.events.filter(event => event.submitted_at_ms >= chartStart.value) ?? []);
const factors = computed(() => summary.value ? [
  ['负载', summary.value.factors.load],
  ...(!props.antigravity ? [['额度', summary.value.factors.quota] as const] : []),
  ['健康', summary.value.factors.health], ['首输出延迟（汇总）', summary.value.factors.latency],
  ...(summary.value.config.reset_weight && summary.value.factors.reset != null ? [['重置偏好', summary.value.factors.reset] as const] : []),
  ...(summary.value.config.queue_weight && summary.value.factors.queue != null ? [['排队偏好', summary.value.factors.queue] as const] : []),
] as const : []);
const waitBasisLabel = computed(() => ({ pacing: '按发送间隔估算', sampled: '按成功请求总耗时估算（账号汇总）', pressure: '按队列压力比较，预计时长未知' }[summary.value?.factors.wait_basis ?? 'pressure']));

/** 将绝对提交时间映射到同一时间轴。@param time UTC 毫秒。@return SVG 横坐标。 */
function x(time: number): number {
  return 30 + Math.min(1, Math.max(0, (time - chartStart.value) / Math.max(1, chartEnd.value - chartStart.value))) * 940;
}

/** 格式化采集时间，缺失不伪装为当前时间。@param time UTC 毫秒。@return 中文本地时间。 */
function timeLabel(time?: number): string {
  return time ? new Date(time).toLocaleTimeString('zh-CN', { hour12: false }) : '未采集';
}

/** 判断某绑定当前是否有请求。@param row 会话行。@return 活跃或闲置标签。 */
function sessionState(row: SchedulingSession): string {
  return Object.values(row.phases).some(n => n > 0) ? '活动中续租' : `${Math.max(0, Math.ceil((row.expires_at_ms - estimatedServerNow.value) / 60000))} 分钟`;
}

/** 只在详情可见时读取，避免旧响应覆盖新账号或新筛选。@return 当前轮加载结束。 */
async function refresh(): Promise<void> {
  if (!props.open || document.hidden || loading.value || props.accountId <= 0) return;
  const current = generation;
  const accountId = props.accountId;
  const requestedPage = page.value;
  const requestedPageSize = pageSize.value;
  const requestedState = state.value;
  const requestedPrefix = appliedPrefix.value;
  const currentController = new AbortController();
  controller = currentController;
  loading.value = true;
  try {
    let [snapshot, rows] = await Promise.all([
      api.accountScheduling(accountId, currentController.signal),
      props.antigravity ? Promise.resolve(null) : api.accountSchedulingSessions(accountId, requestedPage, requestedState, requestedPrefix, currentController.signal, requestedPageSize),
    ]);
    if (current !== generation || !props.open || accountId !== props.accountId) return;
    let resolvedPage = requestedPage;
    if (rows && requestedPage > 1 && (requestedPage - 1) * rows.page_size >= rows.total) {
      // 会话随到期或状态变化减少；最多回读一次第一页，避免留在无法返回的空页。
      rows = await api.accountSchedulingSessions(accountId, 1, requestedState, requestedPrefix, currentController.signal, requestedPageSize);
      if (current !== generation || !props.open || accountId !== props.accountId) return;
      resolvedPage = 1;
    }
    detail.value = snapshot;
    sessions.value = rows;
    page.value = resolvedPage;
    receivedAt.value = Date.now();
    localNow.value = receivedAt.value;
    error.value = '';
  } catch (cause) {
    if (current === generation && !currentController.signal.aborted) {
      error.value = cause instanceof Error ? cause.message : '读取调度状态失败';
    }
  } finally {
    if (current === generation) {
      loading.value = false;
      controller = null;
    }
  }
}

/** 取消旧读取并清理计时器。@return 无。 */
function stop(): void {
  generation++;
  controller?.abort();
  controller = null;
  loading.value = false;
  if (refreshTimer) clearInterval(refreshTimer);
  if (clockTimer) clearInterval(clockTimer);
  refreshTimer = null;
  clockTimer = null;
}

/** 跟随可见性管理刷新；本地倒计时不发送后端请求。@return 无。 */
function syncVisibility(): void {
  stop();
  if (!props.open || document.hidden) return;
  void refresh();
  refreshTimer = setInterval(() => { void refresh(); }, 5000);
  clockTimer = setInterval(() => { localNow.value = Date.now(); }, 1000);
}

/** 应用有界筛选，不把任意文本送入摘要查询。@return 无。 */
function applyFilter(): void {
  const value = String(prefix.value).trim().toLowerCase();
  if (!/^[0-9a-f]{0,64}$/.test(value)) { error.value = '请输入十六进制会话摘要前缀'; return; }
  appliedPrefix.value = value;
  page.value = 1;
  syncVisibility();
}

/** 翻页并取消旧页的读取。@param value 目标页。@return 无。 */
function changePage(value: number): void {
  if (value < 1 || !sessions.value || value > Math.max(1, Math.ceil(sessions.value.total / pageSize.value))) return;
  page.value = value;
  syncVisibility();
}

watch(() => [props.open, props.accountId] as const, () => {
  detail.value = null;
  sessions.value = null;
  error.value = '';
  receivedAt.value = 0;
  page.value = 1;
  prefix.value = '';
  appliedPrefix.value = '';
  state.value = 'all';
  syncVisibility();
}, { immediate: true });
onMounted(() => document.addEventListener('visibilitychange', syncVisibility));
onUnmounted(() => { stop(); document.removeEventListener('visibilitychange', syncVisibility); });
</script>

<template>
  <component :is="embedded ? 'section' : Dialog" :class="{'embedded-scheduling': embedded}" :open="open" @update:open="emit('update:open', $event)">
    <component :is="embedded ? 'div' : DialogContent" class="scheduling-dialog" :class="{'embedded-scheduling-content':embedded}">
      <DialogHeader v-if="!embedded">
        <DialogTitle>{{ accountName }} · 调度详情</DialogTitle>
        <DialogDescription>只读查看 API 网关绑定与真实提交，每 5 秒刷新。会话数、请求数和上游池槽位分别统计。</DialogDescription>
      </DialogHeader>
      <div class="scheduling-scroll">
      <NoticeStrip v-if="error" tone="warning" role="alert" class="scheduling-error">{{ error }}<span v-if="detail"> · 保留上次快照，数据已陈旧</span></NoticeStrip>
      <p v-if="!detail && loading" class="scheduling-note">正在读取调度快照…</p>
      <template v-if="detail && summary">
        <div class="scheduling-meta">
          <span>智能排序 · {{ schedulingReasonLabel(summary.capacity.reason) }} · 常规请求容量快照</span>
          <span>{{ stale ? '快照已陈旧' : '观测于 ' + timeLabel(summary.observed_at_ms) }}</span>
        </div>
        <div class="scheduling-metrics">
          <EntityBlock v-if="!antigravity"><p>已绑定／活跃会话</p><strong>{{ summary.bound_sessions }} / {{ summary.active_sessions }}</strong></EntityBlock>
          <EntityBlock><p>正在执行的请求</p><strong>{{ summary.phases.running }}</strong></EntityBlock>
          <EntityBlock><p>最近 60 秒提交</p><strong>{{ summary.submissions_last_60s }}</strong><small v-if="summary.observed_at_ms - summary.history_available_from_ms < 60000" class="is-warning">采集不足 60 秒</small></EntityBlock>
          <EntityBlock><p>按上次快照最早可发</p><span>{{ nextLabel }}</span></EntityBlock>
        </div>
        <div class="scheduling-phases">
          <span>等并发 {{ summary.phases.waiting_concurrency }}</span><span>准备环境 {{ summary.phases.preparing }}</span><span>等发送 {{ summary.phases.waiting_send }}</span><span>退避 {{ summary.phases.backoff }}</span><span>无当前绑定请求 {{ summary.unbound_requests }}</span>
        </div>
        <div class="scheduling-section">
          <div class="scheduling-section-head">
            <h3>真实提交时间轴</h3>
            <div class="scheduling-range"><button type="button" :aria-pressed="rangeMs === 60000" @click="rangeMs = 60000">最近 1 分钟</button><button type="button" :aria-pressed="rangeMs === 300000" @click="rangeMs = 300000">最近 5 分钟</button></div>
          </div>
          <div class="scheduling-timeline"><svg viewBox="0 0 1000 115" role="img" aria-label="真实提交点和预计最早许可时刻" class="scheduling-chart">
            <line class="scheduling-axis" x1="30" y1="55" x2="970" y2="55" stroke-width="2" />
            <line class="scheduling-now" :x1="x(detail.snapshot.observed_at_ms)" y1="20" :x2="x(detail.snapshot.observed_at_ms)" y2="80" stroke-dasharray="4 4" />
            <circle v-for="(event, index) in events" :key="event.request_id + ':' + event.submitted_at_ms + ':' + index" class="scheduling-event" :cx="x(event.submitted_at_ms)" cy="55" r="3.5"><title>{{ timeLabel(event.submitted_at_ms) }} · 已提交</title></circle>
            <template v-if="summary.next_send_at_ms != null && summary.next_send_at_ms > detail.snapshot.observed_at_ms">
              <line class="scheduling-next" :x1="x(summary.next_send_at_ms)" y1="25" :x2="x(summary.next_send_at_ms)" y2="80" stroke-dasharray="3 4" />
              <circle class="scheduling-next-dot" :cx="x(summary.next_send_at_ms)" cy="55" r="6" stroke-width="2"><title>预计最早可发，不代表已预订</title></circle>
            </template>
            <text class="scheduling-label" x="30" y="100" font-size="12">{{ rangeMs / 60000 }} 分钟前</text><text class="scheduling-label" :x="x(detail.snapshot.observed_at_ms)" y="100" font-size="12" text-anchor="middle">快照时刻</text><text class="scheduling-label" x="970" y="100" font-size="12" text-anchor="end">未来许可参考</text>
          </svg></div>
          <p class="scheduling-note">实心点表示{{ antigravity ? '已观测到原生模型启动' : 'Gateway 向 sender 发起提交' }}。空心点表示预计最早许可。历史从 {{ timeLabel(detail.snapshot.history_available_from_ms) }} 起采集，重启后留空。</p>
          <p v-if="detail.snapshot.history_truncated" class="scheduling-note is-warning">事件缓冲已截断 {{ detail.snapshot.dropped_events }} 条，时间轴不是完整历史；60 秒统计使用独立时间桶。</p>
          <p v-if="events.length === 0" class="scheduling-note">当前采集窗口内没有记录到提交点。</p>
        </div>
        <div class="scheduling-factors">
          <div v-for="factor in factors" :key="factor[0]"><div class="scheduling-factor-label"><span>{{ factor[0] }}</span><span>{{ (factor[1] * 100).toFixed(0) }}</span></div><div class="scheduling-factor-bar"><i :style="{ width: Math.max(0, Math.min(100, factor[1] * 100)) + '%' }" /></div></div>
        </div>
        <p v-if="antigravity" class="scheduling-note">优先级数值越小越先接单。同优先级比较负载、健康和首输出延迟。额度不计分，工具回填保留原账号。</p>
        <p v-else class="scheduling-note">归一化偏好越高越优，仅影响新会话。延迟取成功请求的首个有效文字、思考或工具输出；图中为账号汇总，实际选号按模型、思考参数和流式方式分别比较。未知健康与延迟按满分起步，额度未知按中性计算。</p>
        <p v-if="summary.config.queue_weight && summary.factors.wait_score != null" class="scheduling-note">基础偏好 {{ (summary.factors.score * 100).toFixed(1) }} · 等待排序偏好 {{ (summary.factors.wait_score * 100).toFixed(1) }} · {{ waitBasisLabel }}<span v-if="summary.factors.estimated_wait_ms != null"> · 预计等待 {{ (summary.factors.estimated_wait_ms / 1000).toFixed(1) }} 秒</span>。等待排序单独计算运行负载和等待代价。</p>
        <p v-if="!antigravity && summary.factors.quota_state === 'reset_pending'" class="scheduling-note is-warning">旧额度周期已结束，等待自动刷新用量。</p>
        <p v-else-if="!antigravity && summary.factors.quota_state === 'unknown'" class="scheduling-note">尚无有效额度观测，额度分暂按中性计算。</p>
        <div v-if="!antigravity" class="scheduling-section scheduling-sessions">
          <h3>网关绑定会话</h3>
          <div class="scheduling-filters">
            <ChoiceSelect :model-value="state" @update:model-value="value => { state = value; applyFilter(); }" label="会话活跃状态" :options="[{value:'all',label:'全部绑定'},{value:'active',label:'活跃'},{value:'idle',label:'闲置'}]" />
            <SearchInput v-model="prefix" placeholder="搜索脱敏摘要前缀" label="会话摘要前缀" @search="applyFilter" />
            <Button variant="outline" @click="applyFilter">筛选</Button>
          </div>
          <Table>
            <TableHeader><TableRow><TableHead>会话摘要</TableHead><TableHead>等槽／准备／等发／执行／退避</TableHead><TableHead>首次绑定</TableHead><TableHead>最近活动</TableHead><TableHead>闲置有效期</TableHead></TableRow></TableHeader>
            <TableBody>
              <TableRow v-for="row in sessions?.items ?? []" :key="row.session_key"><TableCell class="scheduling-session-key">{{ row.session_key.slice(0, 12) }}</TableCell><TableCell>{{ row.phases.waiting_concurrency }} / {{ row.phases.preparing }} / {{ row.phases.waiting_send }} / {{ row.phases.running }} / {{ row.phases.backoff }}</TableCell><TableCell>{{ timeLabel(row.created_at_ms) }}</TableCell><TableCell>{{ timeLabel(row.last_seen_at_ms) }}</TableCell><TableCell>{{ sessionState(row) }}</TableCell></TableRow>
              <TableEmpty v-if="sessions?.items.length === 0" :colspan="5">当前筛选没有有效绑定</TableEmpty>
            </TableBody>
          </Table>
          <Pagination v-model:page-size="pageSize" :page="page" :total="sessions?.total ?? 0" :disabled="loading" unit="个绑定" label="绑定会话分页" @update:page="changePage" />
          <p class="scheduling-note">摘要按 API Token 隔离；一个会话可有多个请求。无 ID、尚未绑定或已换绑定但仍在旧账号执行的请求计入无当前绑定请求；此处不展示官方聊天内容。</p>
        </div>
      </template>
      </div>
    </component>
  </component>
</template>
