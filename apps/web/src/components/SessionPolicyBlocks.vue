<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { api, type SessionPolicyBlock } from '../api';
import { formatLocalTime } from '../lib/time';
import { useToast } from '../composables/useToast';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { SearchInput, ChoiceSelect, Pagination, InfoTooltip } from './ui/controls';
import { ConfirmationDialog } from './ui/feedback';
import { ShieldCheck, Settings2, RefreshCw, Search } from './ui/icon';

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
const states = [{ value:'active',label:'封禁中' }, { value:'expired',label:'已到期' }, { value:'released',label:'已解除' }, { value:'all',label:'全部记录' }];
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
    rows.value=result.items;total.value=result.total;page.value=requested;loaded.value=true;error.value='';
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

/** 将持久化毫秒交给公共本地时间格式化器。@param milliseconds UTC 毫秒。@return 本地时间与时区。 */
function date(milliseconds: number): string { return formatLocalTime(new Date(milliseconds).toISOString()); }

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
    <header class="page-heading"><div><p class="page-eyebrow">网关</p><h2>会话封禁</h2><p class="page-description">查看策略拒答触发的会话封禁，以及到期和解除记录。</p></div>
      <router-link :to="{ name:'settings',query:{ category:'scheduling',section:'session-policy-block' } }"><Button variant="outline"><Settings2 :size="15" />封禁设置</Button></router-link>
    </header>
    <section class="session-block-panel">
      <form class="session-block-toolbar" @submit.prevent="load(1)">
        <ChoiceSelect v-model="state" label="封禁状态" :options="states" />
        <SearchInput v-model="prefix" label="搜索会话" placeholder="输入会话匿名标识前缀" maxlength="64" @search="load(1)" />
        <Button type="submit" :disabled="loading"><Search :size="14" />查询</Button>
        <Button type="button" variant="outline" :disabled="loading" @click="load()"><RefreshCw :size="14" :class="{'animate-spin':loading}" />刷新</Button>
      </form>
      <p class="session-block-note">时间按本地时区显示 · 每 5 秒刷新 · 重复拦截保持原到期时间</p>
      <p v-if="error" class="session-block-error" role="alert">{{ error }}<span v-if="loaded"> · 当前保留上次读取结果</span><Button variant="outline" size="sm" @click="load()">重试</Button></p>
      <div class="session-block-records" :aria-busy="loading">
        <Table>
          <TableHeader><TableRow><TableHead>会话 / 触发来源</TableHead><TableHead class="block-source-column">访问令牌 / 账号</TableHead><TableHead>封禁状态</TableHead><TableHead class="block-time-column">封禁时间</TableHead><TableHead class="block-count-column">本地拦截</TableHead><TableHead>操作</TableHead></TableRow></TableHeader>
          <TableBody>
            <TableRow v-for="row in rows" :key="row.id" :data-block-id="row.id">
              <TableCell><div class="block-identity"><ShieldCheck :size="17" /><div>
                <InfoTooltip label="查看完整会话匿名标识" title="会话匿名标识"><template #trigger><code>{{ row.session_key.slice(0,12) }}</code></template><span class="break-all">{{ row.session_key }}</span></InfoTooltip>
                <small>{{ reasons[row.reason] || '上游策略拒答' }}</small><small>{{ row.model || '模型未记录' }}</small>
                <small class="block-mobile-source">{{ row.token_name || `访问令牌 ${row.api_token_id}` }} · {{ row.account_name || `账号 ${row.account_id}` }}</small>
              </div></div></TableCell>
              <TableCell class="block-source-column"><span>{{ row.token_name || (row.api_token_id===0?'默认调用域':`访问令牌 ${row.api_token_id}`) }}</span><small>{{ row.account_name || `账号 ${row.account_id}` }}</small></TableCell>
              <TableCell><Badge variant="outline" :class="{'block-active':status(row)==='封禁中'}">{{ status(row) }}</Badge><small>{{ remaining(row) }}</small><small class="block-mobile-source">已拦截 {{ row.blocked_request_count }} 次</small><InfoTooltip label="查看封禁到期时间" title="到期时间"><template #trigger><span class="block-time-link">到期时间</span></template><p>封禁于 {{ date(row.blocked_at_ms) }}</p>{{ date(row.expires_at_ms) }}<p v-if="row.released_at_ms">解除于 {{ date(row.released_at_ms) }}</p></InfoTooltip></TableCell>
              <TableCell class="block-time-column"><small>{{ date(row.blocked_at_ms) }}</small></TableCell>
              <TableCell class="block-count-column"><span class="tabular-nums">{{ row.blocked_request_count }} 次</span><small v-if="row.last_blocked_at_ms">{{ date(row.last_blocked_at_ms) }}</small></TableCell>
              <TableCell><div class="block-actions"><router-link v-if="row.source_request_id" :to="{name:'requests',query:{correlation_id:row.source_request_id}}"><Button size="sm" variant="outline">关联请求</Button></router-link><Button v-if="status(row)==='封禁中'" size="sm" variant="outline" @click="confirmRelease(row)">解除封禁</Button><span v-else-if="!row.source_request_id" class="text-muted-foreground">—</span></div></TableCell>
            </TableRow>
            <TableRow v-if="!rows.length"><TableCell :colspan="6" class="session-block-empty"><div class="block-empty-content">
              <ShieldCheck :size="28" />
              <strong>{{ loading && !loaded?'正在读取封禁记录…':error && !loaded?'封禁记录暂时不可用':submittedPrefix?'暂无匹配的封禁记录':state==='active'?'当前没有封禁中的会话':'暂无匹配的封禁记录' }}</strong>
              <p>{{ error && !loaded?'请稍后重试读取封禁记录。':submittedPrefix || state!=='active'?'可以调整封禁状态或会话匿名标识。':'触发策略拒答后的会话封禁会显示在这里。' }}</p>
              <Button size="sm" variant="outline" :disabled="loading" @click="resetFilters">重置查询</Button>
            </div></TableCell></TableRow>
          </TableBody>
        </Table>
      </div>
      <footer class="session-block-pagination"><Pagination :page="page" v-model:page-size="pageSize" :total="total" :disabled="loading" label="会话封禁分页" @update:page="value=>load(value)" /></footer>
    </section>
    <ConfirmationDialog :open="!!target" title="解除会话封禁" :message="`解除后，会话 ${target?.session_key.slice(0,12) || ''} 可继续请求。此次封禁记录将保留。`" confirm-label="解除封禁" :busy="releasing" :error="releaseError" @cancel="target=null" @confirm="release" />
  </div>
</template>

<style scoped>
.session-block-page{display:grid;gap:20px;min-width:0}
.session-block-page>.page-heading{margin-bottom:8px}
.session-block-panel{min-width:0;background:var(--card);border:1px solid var(--ui-border);border-radius:12px;overflow:hidden}
.session-block-toolbar{display:flex;align-items:flex-end;flex-wrap:wrap;gap:9px;padding:20px 24px 12px}
.session-block-toolbar>:first-child{width:150px}
.session-block-toolbar>:nth-child(2){flex:1;min-width:180px}
.session-block-toolbar :deep([data-slot=button]){font-size:var(--ui-font-small);height:var(--ui-control-height)}
.session-block-note{padding:0 24px 16px;color:#68788e;font-size:var(--ui-font-small);line-height:1.7}
.session-block-error{display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:12px 24px;color:var(--ui-danger);background:var(--ui-field-surface);font-size:var(--ui-font-small)}
/* 样式从页面容器穿透到表格，避免组件内部节点缺少父级作用域标记而失效。 */
.session-block-records :deep(table){width:100%;table-layout:fixed;font-size:var(--ui-font-small)}
.session-block-records :deep(th){padding:13px 12px;background:#fafbfd;color:#65758b;font-size:var(--ui-font-small);font-weight:600;white-space:normal}
.session-block-records :deep(th:nth-child(1)){width:25%}
.session-block-records :deep(th:nth-child(2)){width:18%}
.session-block-records :deep(th:nth-child(3)){width:18%}
.session-block-records :deep(th:nth-child(4)){width:17%}
.session-block-records :deep(th:nth-child(5)){width:10%}
.session-block-records :deep(th:nth-child(6)){width:12%}
.session-block-records :deep(td){white-space:normal;overflow-wrap:anywhere;padding:17px 12px;color:#52647d;font-size:var(--ui-font-small);vertical-align:middle;border-color:#eef1f6}
.session-block-records small{display:block;margin-top:7px;color:#6b7b91;font-size:var(--ui-font-small);line-height:1.6}
.session-block-records :deep(.session-block-empty){padding:40px 16px;text-align:center}
.block-empty-content{display:grid;justify-items:center;gap:12px;color:#68788e;line-height:1.7}
.block-empty-content>svg{color:#8e7ca3}
.block-empty-content>strong{font-size:var(--ui-font-body);font-weight:500;color:#405670}
.block-empty-content>p{font-size:var(--ui-font-small)}
.block-identity{display:flex;align-items:flex-start;gap:10px}
.block-identity>svg{color:var(--ui-muted);margin-top:3px;flex-shrink:0}
.block-identity code{font-size:var(--ui-font-small);color:#405670}
.block-actions{display:flex;flex-wrap:wrap;gap:8px}
.block-actions :deep([data-slot=button]){font-size:var(--ui-font-small);white-space:normal;height:auto;min-height:30px}
.block-active{color:var(--ui-danger);border-color:var(--ui-border)}
.block-time-link{display:inline-block;margin-top:7px;font-size:var(--ui-font-small);color:#6b7b91;text-decoration:underline dotted;text-underline-offset:3px}
.session-block-pagination{padding:16px 24px;border-top:1px solid var(--ui-border)}
.block-mobile-source{display:none!important}
@media(max-width:1050px){.block-time-column{display:none}}
@media(max-width:720px){
  .block-source-column,.block-count-column{display:none}
  .block-mobile-source{display:block!important}
  .session-block-toolbar{padding:16px;gap:8px}
  .session-block-toolbar>:nth-child(2){min-width:0;flex-basis:calc(100% - 158px)}
  .session-block-note{padding:0 16px 12px}
  .session-block-records :deep(td),.session-block-records :deep(th){padding:12px 8px}
  .session-block-records :deep(th:nth-child(1)){width:38%}
  .session-block-records :deep(th:nth-child(3)){width:34%}
  .session-block-records :deep(th:nth-child(6)){width:28%}
  .block-identity>svg{display:none}
  .block-identity{gap:0}
  .block-actions{flex-direction:column;align-items:flex-start}
  .session-block-pagination{padding:12px}
  .session-block-page{gap:16px}
  .page-heading{align-items:flex-start;gap:12px;flex-wrap:wrap}
}
</style>
