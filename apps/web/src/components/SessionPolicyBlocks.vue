<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { api, type SessionPolicyBlock, type SessionPolicyBlockCounts } from '../api';
import { formatLocalTime } from '../lib/time';
import { useToast } from '../composables/useToast';
import { Button } from './ui/button';
import { PageHeader } from './ui/page-header';
import { Badge, type BadgeVariants } from './ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { SearchInput, Pagination, InfoTooltip } from './ui/controls';
import { ConfirmationDialog } from './ui/feedback';
import { TableCard } from './ui/table-card';
import { Toolbar } from './ui/toolbar';
import { Segmented, type SegmentedOption } from './ui/segmented';
import { NoticeStrip } from './ui/notice-strip';
import { Empty } from './ui/empty';
import { ShieldCheck, SlidersHorizontal, RefreshCw, Search, AlertCircle } from './ui/icon';
import '../session-blocks.css';

const { show: toast } = useToast();
const rows = ref<SessionPolicyBlock[]>([]);
const state = ref('active');
const prefix = ref('');
const submittedPrefix = ref('');
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const loading = ref(false);
const fetching = ref(false);
const error = ref('');
const loaded = ref(false);
const now = ref(Date.now());
const target = ref<SessionPolicyBlock | null>(null);
const releasing = ref(false);
const releaseError = ref('');
const counts = ref<SessionPolicyBlockCounts | null>(null);
const states = [{ value:'active',label:'封禁中' }, { value:'expired',label:'已到期' }, { value:'released',label:'已解除' }, { value:'all',label:'全部记录' }] as const;
// 计数来自接口（同一前缀、不随状态筛选变化）；旧网关不返回时显示「—」，不按当前页推算。
const stateOptions = computed<SegmentedOption[]>(() => states.map(item => ({ ...item, count: counts.value?.[item.value] ?? '—' })));
const labels: Record<string,string> = { active:'封禁中',expired:'已到期',released:'已解除' };
const reasons: Record<string,string> = { reasoning_extraction:'推理提取拦截',safeguard:'安全策略拦截',usage_policy:'使用政策拒答',content_policy:'内容策略拒答',refusal:'上游拒答' };
let alive = true;
let generation = 0;
let serverObservedAt = Date.now();
let clientObservedAt = performance.now();
let controller: AbortController | undefined;
let clock: ReturnType<typeof setInterval>;
let refresh: ReturnType<typeof setInterval>;

/** 取消旧读取并更新当前页，失败时保留已有记录。@param requested 目标页。@param silent 是否静默刷新已提交的查询。@return 完成。 */
async function load(requested = page.value, silent = false): Promise<void> {
  // 后台轮询沿用已提交条件，避免输入到一半就改变列表。
  const value = silent ? submittedPrefix.value : prefix.value.trim().toLowerCase();
  if (value.length > 64 || !/^[0-9a-f]*$/.test(value)) { error.value='请输入会话匿名标识的十六进制前缀';return; }
  if (!silent) submittedPrefix.value = value;
  controller?.abort();
  controller = new AbortController();
  const current = ++generation;
  fetching.value = true;
  loading.value = !silent;
  if (!silent) error.value = '';
  try {
    const query = new URLSearchParams({ state:state.value,session_prefix:value,page:String(requested),page_size:String(pageSize.value) });
    let result = await api.sessionPolicyBlocks(query.toString(),controller.signal);
    if (requested > 1 && result.total <= (requested-1)*pageSize.value) {
      requested=1;query.set('page','1');result=await api.sessionPolicyBlocks(query.toString(),controller.signal);
    }
    if (!alive || current!==generation) return;
    rows.value=result.items;total.value=result.total;counts.value=result.counts ?? null;page.value=requested;loaded.value=true;error.value='';
    // 以服务端快照加本地单调耗时显示倒计时，避免管理员电脑时钟偏差误判到期。
    serverObservedAt=result.observed_at_ms;clientObservedAt=performance.now();now.value=serverObservedAt;
  } catch (cause) {
    if (alive && current===generation && !(cause instanceof Error && cause.name==='AbortError')) error.value=(cause as Error).message || '封禁记录读取失败';
  } finally { if (alive && current===generation) { loading.value=false;fetching.value=false; } }
}

/** 清空查询并恢复封禁中列表。@return 无。 */
function resetFilters(): void {
  prefix.value='';
  if (state.value!=='active') state.value='active';
  else void load(1);
}

/** 按服务端状态与当前时间显示自然到期。@param row 封禁记录。@return 中文状态。 */
function status(row: SessionPolicyBlock): string {
  return row.state==='active' && row.expires_at_ms<=now.value ? '已到期' : labels[row.state] || '状态待确认';
}

/** 展示到期倒计时，截止时间仍由服务端裁决。@param row 封禁记录。@return 可读时长。 */
function remaining(row: SessionPolicyBlock): string {
  if (row.state==='released') return '已提前解除';
  const minutes = Math.ceil((row.expires_at_ms-now.value)/60000);
  if (minutes<=0) return '已到期';
  const hours = Math.floor(minutes/60);
  return hours ? `剩余 ${hours} 小时 ${minutes%60} 分钟` : `剩余 ${minutes} 分钟`;
}

/** 状态徽标色：封禁中为危险色，已解除为成功色，其余中性。@param row 封禁记录。@return 徽标变体。 */
function statusVariant(row: SessionPolicyBlock): BadgeVariants['variant'] {
  const value = status(row);
  return value==='封禁中' ? 'destructive' : value==='已解除' ? 'success' : 'secondary';
}

/** 将持久化毫秒交给公共本地时间格式化器；时区已在工具栏说明一次，单元格不再重复。@param milliseconds UTC 毫秒。@return 本地日期时间。 */
function date(milliseconds: number): string { return formatLocalTime(new Date(milliseconds).toISOString(), false); }

/** 建立解除确认，保持当前行上下文。@param row 用户选择的封禁。@return 无。 */
function confirmRelease(row: SessionPolicyBlock): void { target.value=row;releaseError.value=''; }

/** 执行明确确认的单条解除，失败保留窗口与错误。@return 完成。 */
async function release(): Promise<void> {
  if (!target.value || releasing.value) return;
  releasing.value=true;releaseError.value='';
  try {
    await api.releaseSessionPolicyBlock(target.value.id);
    if (!alive) return;
    target.value=null;toast('会话封禁已解除', 'success');await load();
  } catch (cause) { if (alive) releaseError.value=(cause as Error).message || '解除失败，请重试'; }
  finally { if (alive) releasing.value=false; }
}

watch(state, () => { void load(1); });
watch(pageSize, () => { void load(1); });
onMounted(() => {
  void load();
  clock=setInterval(() => { now.value=serverObservedAt + performance.now() - clientObservedAt; },1000);
  refresh=setInterval(() => { if (document.visibilityState==='visible' && !fetching.value && !target.value && !releasing.value) void load(page.value,true); },5000);
});
onUnmounted(() => { alive=false;generation++;controller?.abort();clearInterval(clock);clearInterval(refresh); });
</script>

<template>
  <div class="session-block-page">
    <PageHeader title="会话封禁" description="查看策略拒答触发的会话封禁，以及到期和解除记录。">
      <template #actions><router-link :to="{ name:'settings',query:{ category:'scheduling',section:'session-policy-block' } }"><Button variant="outline"><SlidersHorizontal :size="15" />封禁设置</Button></router-link></template>
    </PageHeader>
    <TableCard class="session-block-panel">
      <template #toolbar>
        <!-- 表单包住整行工具栏，搜索框回车与「查询」都提交同一条件。 -->
        <form class="session-block-toolbar" @submit.prevent="load(1)">
          <Toolbar>
            <Segmented v-model="state" :options="stateOptions" label="封禁状态" />
            <SearchInput v-model="prefix" label="搜索会话" placeholder="输入会话匿名标识前缀" maxlength="64" @search="load(1)" />
            <Button type="submit" :disabled="loading"><Search :size="14" />查询</Button>
            <Button type="button" variant="outline" :disabled="loading" @click="load()"><RefreshCw :size="14" :class="{'animate-spin':loading}" />刷新</Button>
            <template #end><span class="session-block-note">时间按本地时区显示 · 每 5 秒刷新 · 重复拦截保持原到期时间</span></template>
          </Toolbar>
        </form>
      </template>
      <NoticeStrip v-if="error" tone="danger" role="alert" class="session-block-error"><AlertCircle />{{ error }}<span v-if="loaded"> · 当前保留上次读取结果</span><template #end><Button variant="outline" size="sm" @click="load()">重试</Button></template></NoticeStrip>
      <div class="session-block-records" :aria-busy="loading">
        <Table class="fui-table-fixed">
          <!-- 固定布局按表头宽度分列；窄屏隐藏的列连同表头一起隐藏，其余列按比例重分。 -->
          <TableHeader><TableRow><TableHead class="block-col-session">会话 / 触发来源</TableHead><TableHead class="block-col-source block-source-column">访问令牌 / 账号</TableHead><TableHead class="block-col-state">封禁状态</TableHead><TableHead class="block-col-time block-time-column">封禁时间</TableHead><TableHead class="block-col-count block-count-column">本地拦截</TableHead><TableHead class="block-col-actions fui-table-end">操作</TableHead></TableRow></TableHeader>
          <TableBody>
            <TableRow v-for="row in rows" :key="row.id" :data-block-id="row.id">
              <TableCell>
                <InfoTooltip label="查看完整会话匿名标识" title="会话匿名标识"><template #trigger><code class="fui-table-mono">{{ row.session_key.slice(0,12) }}…</code></template><span class="break-all">{{ row.session_key }}</span></InfoTooltip>
                <span class="fui-table-sub">{{ reasons[row.reason] || '上游策略拒答' }} · {{ row.model || '模型未记录' }}</span>
                <span class="fui-table-sub block-mobile-source">{{ row.token_name || `访问令牌 ${row.api_token_id}` }} · {{ row.account_name || `账号 ${row.account_id}` }}</span>
              </TableCell>
              <TableCell class="block-source-column">{{ row.token_name || (row.api_token_id===0?'默认调用域':`访问令牌 ${row.api_token_id}`) }}<span class="fui-table-sub">{{ row.account_name || `账号 ${row.account_id}` }}</span></TableCell>
              <TableCell>
                <Badge as="span" :variant="statusVariant(row)" dot>{{ status(row) }}</Badge>
                <span class="fui-table-sub">{{ remaining(row) }} · <InfoTooltip label="查看封禁到期时间" title="到期时间"><template #trigger><span class="block-time-link">到期时间</span></template><p>封禁于 {{ date(row.blocked_at_ms) }}</p>{{ date(row.expires_at_ms) }}<p v-if="row.released_at_ms">解除于 {{ date(row.released_at_ms) }}</p></InfoTooltip></span>
                <span class="fui-table-sub block-mobile-source">已拦截 {{ row.blocked_request_count }} 次</span>
              </TableCell>
              <TableCell class="fui-table-num block-time-column">{{ date(row.blocked_at_ms) }}</TableCell>
              <TableCell class="fui-table-num block-count-column"><b class="fui-table-strong">{{ row.blocked_request_count }} 次</b><span v-if="row.last_blocked_at_ms" class="fui-table-sub">最近 {{ date(row.last_blocked_at_ms) }}</span></TableCell>
              <TableCell><div class="fui-table-ops block-actions"><router-link v-if="row.source_request_id" :to="{name:'requests',query:{correlation_id:row.source_request_id}}"><Button size="sm" variant="outline">关联请求</Button></router-link><Button v-if="status(row)==='封禁中'" size="sm" variant="outline" @click="confirmRelease(row)">解除封禁</Button><span v-else-if="!row.source_request_id" class="block-no-action">—</span></div></TableCell>
            </TableRow>
            <TableRow v-if="!rows.length"><TableCell :colspan="6" class="session-block-empty">
              <Empty :title="loading && !loaded?'正在读取封禁记录…':error && !loaded?'封禁记录暂时不可用':submittedPrefix?'暂无匹配的封禁记录':state==='active'?'当前没有封禁中的会话':'暂无匹配的封禁记录'" :description="error && !loaded?'请稍后重试读取封禁记录。':submittedPrefix || state!=='active'?'可以调整封禁状态或会话匿名标识。':'触发策略拒答后的会话封禁会显示在这里。'">
                <template #icon><ShieldCheck /></template>
                <template #actions><Button size="sm" variant="outline" :disabled="loading" @click="resetFilters">重置查询</Button></template>
              </Empty>
            </TableCell></TableRow>
          </TableBody>
        </Table>
      </div>
      <template #footer><Pagination :page="page" v-model:page-size="pageSize" :total="total" :disabled="loading" label="会话封禁分页" @update:page="value=>load(value)" /></template>
    </TableCard>
    <ConfirmationDialog :open="!!target" title="解除会话封禁" :message="`解除后，会话 ${target?.session_key.slice(0,12) || ''} 可继续请求。此次封禁记录将保留。`" confirm-label="解除封禁" :busy="releasing" :error="releaseError" @cancel="target=null" @confirm="release" />
  </div>
</template>
