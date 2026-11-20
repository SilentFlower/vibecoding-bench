<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { Copy, Settings2, RefreshCw, Search, FileText, ArrowUpRight, ArrowRight, ShieldCheck, LayoutGrid, AlertCircle, Clock } from './ui/icon';
import { ChoiceSelect, SearchInput, DateTimeControl, InfoTooltip, Pagination } from './ui/controls';
import AccountFilterSelect from './AccountFilterSelect.vue';
import '../request-design.css';
import { formatLocalTime } from '../lib/time';
import { useToast } from '../composables/useToast';
import NativeStageDetails from './NativeStageDetails.vue';
import ExecutionNodeBadge from './runtime/ExecutionNodeBadge.vue';
import PlatformBadge from './PlatformBadge.vue';
import { api, type DiagnosticRequest, type DiagnosticAttempt, type NativeCapture } from '../api';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';

const toast = useToast();
const filtersOpen = ref(false);
const platform = ref(''), protocol = ref(''), kernelVersion = ref(''), requestedModel = ref(''), actualModel = ref('');
const platformOptions = [{value:'',label:'全部平台'},{value:'claude_code',label:'Claude Code'},{value:'antigravity',label:'Antigravity'},{value:'history_unknown',label:'历史未记录'}];
const protocolOptions = [{value:'',label:'全部协议'},{value:'anthropic_messages',label:'Messages'},{value:'gemini',label:'Gemini'},{value:'history_unknown',label:'历史未记录'}];
const outcome = ref('');
const since = ref<string | null>(null);
const until = ref<string | null>(null);
const counts = ref<{all:number;errors:number;processing:number} | null>(null);
const quick = ref('all');
const quickTabs=[{id:'all',label:'全部',icon:LayoutGrid},{id:'errors',label:'错误',icon:AlertCircle},{id:'processing',label:'处理中',icon:Clock}] as const;
const outcomeOptions=['success','in_progress','incomplete','local_rejected','local_response','mock','cache_hit','upstream_rejected','upstream_error','transport_error','body_error','cancelled'].map(value=>({value,label:outcomeLabel(value)}));
/** 快捷结果和具体结果使用同一查询维度。@param value 快捷结果。@return 无。 */
function chooseQuick(value: string): void { quick.value=value;outcome.value='';void load(); }
/** 清除筛选后重新查询。@return 无。 */
function resetFilters(): void { platform.value='';protocol.value='';kernelVersion.value='';requestedModel.value='';actualModel.value='';account.value='';outcome.value='';since.value=null;until.value=null;correlation.value='';quick.value='all';void load(); }
const tabs = [{id: 'overview', label: '概览'}, {id: 'chain', label: '请求链路'}, {id: 'performance', label: '性能'}, {id: 'raw', label: '原始数据'}] as const;
const activeTab = ref<typeof tabs[number]['id']>('overview');
const route = useRoute();
const linkedAccount = Number(route.query.account);
const account = ref(Number.isSafeInteger(linkedAccount) && linkedAccount > 0 ? String(linkedAccount) : '');
const correlation = ref(typeof route.query.correlation_id==='string' ? route.query.correlation_id : '');
const page = ref(1);
const pageSize = ref(20);
watch(pageSize, () => { page.value=1;void load(1); });
const total = ref(0);
const rows = ref<DiagnosticRequest[]>([]);
const selected = ref<DiagnosticRequest | null>(null);
const attempts = ref<DiagnosticAttempt[]>([]);
// 详情接口独立返回有序尝试，末次位置沿详情原记录读取。
const latestExecution = computed(() => attempts.value.length
  ? attempts.value[attempts.value.length - 1]?.execution_location : selected.value?.last_attempt?.execution_location);
const capture = ref<NativeCapture | null>(null);
const selectedAttempt = ref('');
const health = ref<Record<string, number>>({});
const error = ref('');
const loading = ref(false);
const dialogOpen = ref(false);
const detailLoading = ref(false);
const detailError = ref('');
const mode = ref<'info' | 'debug' | 'unknown'>('unknown');
const rejectedBody = ref<'preview' | 'full'>('preview');
const modeSaving = ref(false);
const modeError = ref('');
let listController: AbortController | null = null;
let detailController: AbortController | null = null;
const settingsController = new AbortController();
let listGeneration = 0;
let detailGeneration = 0;
let opener: HTMLElement | null = null;
let mounted = true;

/** 统一显示当前账号资料，缺失资料保留追溯标识。@param value 请求或尝试的账号投影。@return 名称及邮箱或缺失提示。 */
function accountLabel(value: Pick<DiagnosticRequest, 'account_id' | 'account_name' | 'account_email'>): string {
  if (value.account_id == null) return '未知账号';
  const name = value.account_name?.trim();
  const email = value.account_email?.trim();
  if (name && email && name !== email) return `${name} · ${email}`;
  return name || email || `账号信息缺失（ID ${value.account_id}）`;
}

const tpsDescription = '平均 TPS = 输出 token 数 ÷ 本次尝试耗时（秒），包含首输出等待，仅展示完整成功记录。';
/** 展示固定拒绝原因及其所属字段，未知历史值保持明确缺口。@param reason 原因码。@return 中文说明。 */
function rejectionLabel(reason?: string | null): string {
  return ({ native_entrypoint_unsupported: '调用入口不支持（billing.cc_entrypoint）', native_version_mismatch: '原生版本冲突（billing.cc_version）',
    native_billing_invalid: 'billing 结构错误（system 首段）', native_metadata_invalid: '身份结构错误（metadata）',
    unsupported_body_field: '正文根字段暂不支持', unsupported_message_field: '消息扩展字段暂不支持（messages）',
    unsupported_system_block: 'system 内容块暂不支持', invalid_message_role: '消息角色不符合当前接入格式（messages.role）',
    session_policy_block: '会话被本地策略拦截', request_policy: '请求被本地策略拦截',
    access_policy: '请求被准入策略拦截', request: '入站请求校验失败', admission: '请求未获准入',
    account_selection: '账号选择阶段返回', credentials: '账号凭据检查失败', runtime_prepare: '运行环境准备失败',
    gateway: '网关本地处理失败' } as Record<string, string>)[reason ?? ''] ?? reason ?? '具体拒绝原因未记录';
}
/** 计算完整成功尝试的平均输出速率。@param attempt 实际尝试摘要。@return 一位小数的 token/s 或未观测。 */
function averageTps(attempt?: DiagnosticAttempt | null): string {
  const tokens = attempt?.tokens?.output_tokens;
  const duration = attempt?.duration_ms;
  if (attempt?.outcome !== 'success' || attempt.partial !== false || typeof tokens !== 'number'
      || !Number.isSafeInteger(tokens) || tokens < 0 || typeof duration !== 'number'
      || !Number.isFinite(duration) || duration <= 0) return '未观测';
  return `${(tokens / (duration / 1000)).toFixed(1)} token/s`;
}

/** 开始读取并取消旧请求，防止旧账号内容覆盖当前选择。@return 读取归属。 */
function begin(): { version: number; signal: AbortSignal } {
  detailController?.abort();
  detailController = new AbortController();
  detailLoading.value = true;
  detailError.value = '';
  return { version: ++detailGeneration, signal: detailController.signal };
}

/** 加载有界列表。@param target 目标页。@return 读取结束。 */
async function load(target = 1): Promise<void> {
  const accountId = String(account.value).trim();
  if (accountId && !/^[1-9][0-9]*$/.test(accountId)) { error.value = '请输入正整数账号 ID'; return; }
  const query = new URLSearchParams({ page: String(target), page_size: String(pageSize.value) });
  for (const [key,value] of [['platform',platform.value],['entry_protocol',protocol.value],['kernel_version',kernelVersion.value],['requested_model',requestedModel.value],['actual_model',actualModel.value]]) if(value.trim())query.set(key,value.trim());
  if (accountId) query.set('account_id', accountId);
  if (outcome.value) query.set('outcome', outcome.value);
  else if (quick.value !== 'all') query.set('outcome',quick.value === 'errors' ? 'errors' : 'in_progress');
  for (const [key, value] of [['since', since.value], ['until', until.value]]) {
    if (value) {
      const time = new Date(value);
      if (!Number.isFinite(time.getTime())) { error.value = '请输入有效时间'; return; }
      query.set(key!, time.toISOString());
    }
  }
  if (correlation.value.trim()) query.set('correlation_id', correlation.value.trim());
  listController?.abort(); listController = new AbortController();
  const signal = listController.signal, version = ++listGeneration;
  loading.value = true; error.value = '';
  try {
    const result = await api.requestDiagnostics(query.toString(), signal);
    if (version !== listGeneration) return;
    rows.value = result.items; total.value = result.total; health.value = result.health; counts.value = result.counts ?? null; page.value = target;
  } catch (cause) {
    if (version === listGeneration && !signal.aborted) error.value = cause instanceof Error ? cause.message : '请求列表读取失败';
  } finally { if (version === listGeneration) loading.value = false; }
}

/** 打开实际请求详情。@param row 当前列表行。@return 尝试读取结束。 */
async function open(row: DiagnosticRequest, event: MouseEvent): Promise<void> {
  opener = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
  activeTab.value = 'overview';
  dialogOpen.value = true;
  const { version, signal } = begin();
  selected.value = row; attempts.value = []; capture.value = null; selectedAttempt.value = '';
  try {
    const result = await api.requestDiagnosticDetail(row.request_id, signal);
    if (version === detailGeneration && dialogOpen.value) { selected.value = result.request; attempts.value = result.attempts; }
  } catch (cause) {
    if (version === detailGeneration && !signal.aborted) detailError.value = cause instanceof Error ? cause.message : '请求详情读取失败';
  } finally { if (version === detailGeneration) detailLoading.value = false; }
}

/** 按需读取组装内容或发送前拒绝的入口证据。@param attempt 可选的上游尝试，省略时读取拒绝证据。@return 快照读取结束。 */
async function inspect(attempt?: DiagnosticAttempt): Promise<void> {
  const rejection = selected.value?.native_rejection;
  const captureId = attempt?.attempt_id ?? rejection?.capture_id;
  if (!selected.value || !captureId || (attempt && !canInspect(attempt))) return;
  activeTab.value = 'raw';
  const requestId = selected.value.request_id;
  const { version, signal } = begin();
  capture.value = null; selectedAttempt.value = captureId;
  try {
    // 后台副本允许晚于业务响应；只重读同次私有证据，沿原取消代次阻止迟到覆盖。
    for (let poll = 0; poll < 6; poll++) {
      const result = await api.nativeCapture(requestId, captureId, signal);
      if (version !== detailGeneration || !dialogOpen.value || signal.aborted) return;
      capture.value = result;
      const pending = result.snapshot?.wire_final?.reason === 'CAPTURE_PENDING'
        || ((attempt?.capture_status ?? rejection?.capture_status) === 'queued' && result.state === 'missing');
      if (!pending || poll === 5) break;
      await new Promise(resolve => setTimeout(resolve, 500));
      if (version !== detailGeneration || !dialogOpen.value || signal.aborted) return;
    }
  } catch (cause) {
    if (version === detailGeneration && !signal.aborted) detailError.value = cause instanceof Error ? cause.message : '采集内容读取失败';
  } finally { if (version === detailGeneration) detailLoading.value = false; }
}

/** 同步弹窗状态并作废关闭前的读取。@param value 新状态。@return 无返回值。 */
function setDialogOpen(value: boolean): void {
  dialogOpen.value = value;
  if (!value) {
    detailGeneration++; detailController?.abort(); detailLoading.value = false;
    selected.value = null; attempts.value = []; capture.value = null; selectedAttempt.value = ''; detailError.value = '';
  }
}

/** 将焦点返回打开详情的列表按钮。@param event 组件焦点事件。@return 无返回值。 */
function restoreFocus(event: Event): void {
  event.preventDefault();
  if (opener?.isConnected) opener.focus();
}

/** 读取实际设置，首次失败保持未知状态。@return 设置读取结束。 */
async function loadMode(): Promise<void> {
  try {
    const settings = await api.getSettings(settingsController.signal);
    if (mounted) {
      mode.value = settings.request_diagnostics_log_mode === 'debug' ? 'debug' : 'info';
      rejectedBody.value = settings.request_diagnostics_rejected_body === 'full' ? 'full' : 'preview';
    }
  } catch (cause) {
    if (mounted && !settingsController.signal.aborted) modeError.value = cause instanceof Error ? cause.message : '日志模式读取失败';
  }
}

/** 保存后续请求使用的诊断设置。@param value 日志模式或拒绝正文范围。@return 保存结束。 */
async function saveDiagnostics(value: string): Promise<void> {
  const logMode = value === 'info' || value === 'debug';
  if (!logMode && value !== 'preview' && value !== 'full') return;
  modeSaving.value = true; modeError.value = '';
  try {
    const key = logMode ? 'request_diagnostics_log_mode' : 'request_diagnostics_rejected_body';
    await api.updateSettings({ [key]: value });
    if (mounted) {
      if (value === 'info' || value === 'debug') mode.value = value;
      else rejectedBody.value = value;
    }
  } catch (cause) {
    if (mounted) modeError.value = cause instanceof Error ? cause.message : '诊断设置保存失败';
  } finally {
    if (mounted) { modeSaving.value = false; }
  }
}

/** 展示每次请求冻结的模式。@param value 实际模式。@return 中文标签。 */
function modeLabel(value?: string | null): string {
  return value === 'info' ? 'info（摘要）' : value === 'debug' ? 'debug（脱敏内容）' : '历史模式未知';
}

/** 显示持久化的采集状态。@param status 尝试采集状态。@return 中文标签。 */
function captureLabel(status?: string | null): string {
  return ({ queued: '后台采集已排队', saved: '已采集', disabled: '采集已关闭', dropped: '采集繁忙，已丢弃', failed: '采集失败', timeout: '采集超时，保存结果待核对' } as Record<string, string>)[status ?? ''] ?? '采集状态缺失';
}


const currentAttempt = computed(() => attempts.value.find(item => item.attempt_id === selectedAttempt.value) ?? attempts.value[0]);

/** 按冻结状态判断是否提供私有文件读取。@param attempt 当前尝试。@return 是否可读取。 */
function canInspect(attempt: DiagnosticAttempt): boolean {
  return ['native280_cc_prepared', 'native293_cc_prepared', 'agy_native'].includes(attempt.profile_selection ?? '') && attempt.log_mode !== 'info'
    && [null, undefined, 'saved', 'queued', 'timeout'].includes(attempt.capture_status);
}

/** 显示响应结果，保留未知服务端状态。@param value 持久结果。@return 中文标签。 */
function outcomeLabel(value: string): string {
  return ({success: '成功', in_progress: '处理中', incomplete: '未完整结束', cancelled: '已取消',
    upstream_error: '上游错误', local_rejected: '本地拒绝', body_error: '响应读取失败',
    timeout: '已超时', mock: '模拟响应', cache_hit: '命中缓存'} as Record<string, string>)[value] ?? value;
}

/** 结果色只依据持久终态。@param value 持久结果。@return 样式类。 */
function outcomeTone(value: string): string {
  return ['success', 'cache_hit'].includes(value) ? 'diagnostic-success' : value === 'in_progress' ? 'diagnostic-pending' : 'diagnostic-error';
}

/** 显示发生时平台，旧记录保留缺口。@param value 持久平台。@return 平台名。 */
function platformLabel(value?: string | null): string {return value==='antigravity'?'Antigravity':value==='claude_code'?'Claude Code':'历史未记录';}
/** 显示本次策略的请求状态和处理事实。@param attempt 实际尝试。@return 策略说明。 */
function policyLabel(attempt: DiagnosticAttempt): string {
  const value=attempt.context?.system_prompt_policy;
  if(!value)return '历史未记录';
  const effect=value.changed===true?`已替换 ${value.replaced_codepoints ?? '未知'} 个码点`:value.changed===false?'本次无替换':'处理回执未观测';
  return `${value.enabled?'开启':'关闭'} · ${effect}`;
}

/** 从发生时起止时间计算请求总时长。@param row 请求记录。@return 毫秒或未知。 */
function elapsed(row: DiagnosticRequest): number | null {
  if (!row.finished_at) return null;
  const duration = Date.parse(row.finished_at) - Date.parse(row.started_at);
  return Number.isFinite(duration) && duration >= 0 ? duration : null;
}

/** 格式化实测耗时并区分空值。@param value 毫秒。@return 可读耗时。 */
function milliseconds(value?: number | null): string {
  return value == null ? '未观测' : value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value} ms`;
}

/** 复制当前安全标识并兼容 HTTP 与弹窗焦点域。@param value 完整标识。@param event 触发事件。@return 复制结束。 */
async function copy(value: string, event: MouseEvent): Promise<void> {
  const trigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      toast.show('已复制', 'success');
      return;
    } catch {
      // 权限拒绝时继续使用当前点击允许的选中复制。
    }
  }
  const host = trigger?.closest('[role="dialog"]') ?? document.body;
  const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const selection = window.getSelection();
  const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index).cloneRange()) : [];
  const textarea = document.createElement('textarea');
  let copied = false;
  try {
    textarea.value = value;
    textarea.readOnly = true;
    textarea.tabIndex = -1;
    textarea.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none';
    // Reka 会把焦点限制在弹窗中，临时输入框必须属于同一焦点域。
    if (host.isConnected && trigger?.isConnected) {
      host.appendChild(textarea);
      textarea.focus({ preventScroll: true });
      textarea.select();
      textarea.setSelectionRange(0, value.length);
      copied = document.execCommand('copy');
    }
  } catch {
    copied = false;
  } finally {
    textarea.remove();
    if (focused?.isConnected) focused.focus({ preventScroll: true });
    if (selection) {
      selection.removeAllRanges();
      for (const range of ranges) selection.addRange(range);
    }
  }
  toast.show(copied ? '已复制' : '复制失败，请选择文本手动复制', copied ? 'success' : 'error');
}

/** 切换尝试时清理原快照与在途读取。@return 无返回值。 */
function changeAttempt(): void {
  detailGeneration++; detailController?.abort(); detailLoading.value = false;
  capture.value = null; detailError.value = '';
}

/** 页签支持左右方向键和首尾导航。@param event 键盘事件。@return 无返回值。 */
function tabKeys(event: KeyboardEvent): void {
  const index = tabs.findIndex(tab => tab.id === activeTab.value);
  const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length
    : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
    : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1;
  if (next < 0) return;
  event.preventDefault(); activeTab.value = tabs[next]!.id;
  (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
}

onMounted(() => { void load(); void loadMode(); });
onUnmounted(() => { mounted = false; listGeneration++; detailGeneration++; listController?.abort(); detailController?.abort(); settingsController.abort(); });
</script>

<template>
  <section class="requests-page" aria-label="请求记录">
    <header class="request-page-heading">
      <div class="page-heading"><div><p class="page-eyebrow">观测与诊断</p><h1>请求记录</h1><p class="page-description">从请求结果、用量到处理链路，快速找到需要关注的调用。</p></div></div>
      <div class="request-diagnostics-settings">
        <div class="request-mode"><ChoiceSelect :model-value="mode" label="后续请求日志" :options="[{value:'unknown',label:'读取中',disabled:true},{value:'info',label:'info · 摘要'},{value:'debug',label:'debug · 脱敏内容'}]" :disabled="modeSaving || mode === 'unknown'" @update:model-value="saveDiagnostics" /></div>
        <div v-if="mode === 'debug'" class="request-mode"><ChoiceSelect :model-value="rejectedBody" label="正文采集范围" :options="[{value:'preview',label:'限长预览'},{value:'full',label:'完整正文 · 脱敏'}]" :disabled="modeSaving" @update:model-value="saveDiagnostics" /></div>
      </div>
    </header>
    <p v-if="modeError" role="alert" class="text-destructive">{{ modeError }}</p>
    <section class="request-query-panel"><div class="request-quick-tabs" role="group" aria-label="请求快捷筛选"><button v-for="item in quickTabs" :key="item.id" type="button" :class="{active:quick===item.id && !outcome}" :aria-pressed="quick===item.id && !outcome" @click="chooseQuick(item.id)"><component :is="item.icon" :size="14" />{{ item.label }}<span>{{ counts?.[item.id] ?? '—' }}</span></button></div>
      <form @submit.prevent="load()"><div class="request-query-toolbar"><SearchInput v-model="correlation" label="请求关联 ID" placeholder="输入完整请求 ID / 响应关联 ID / 上游请求 ID" @search="load()" /><Button type="button" variant="outline" :aria-expanded="filtersOpen" aria-controls="request-filters" @click="filtersOpen=!filtersOpen"><Settings2 :size="14" />筛选<i v-if="account || outcome || since || until || platform || protocol || kernelVersion || requestedModel || actualModel" class="request-filter-dot" /></Button><Button type="submit" :disabled="loading"><Search :size="14" />查询</Button><Button type="button" variant="outline" :disabled="loading" @click="load(page)"><RefreshCw :size="14" />刷新</Button></div>
      <div v-show="filtersOpen" id="request-filters" class="request-filter-fields"><AccountFilterSelect v-model="account" platform="all" /><ChoiceSelect v-model="platform" label="账号平台" :options="platformOptions" /><ChoiceSelect v-model="protocol" label="入口协议" :options="protocolOptions" /><SearchInput v-model="kernelVersion" label="内核版本" placeholder="输入完整内核版本" @search="load()" /><SearchInput v-model="requestedModel" label="请求模型" placeholder="精确请求模型" @search="load()" /><SearchInput v-model="actualModel" label="实际模型" placeholder="实际提交模型标识" @search="load()" /><ChoiceSelect :model-value="outcome" label="具体结果" :options="[{value:'',label:'全部结果'},...outcomeOptions]" @update:model-value="value=>{outcome=value;quick='all'}" /><DateTimeControl v-model="since" label="开始时间" /><DateTimeControl v-model="until" label="结束时间" /><div class="request-filter-footer"><span>按浏览器本地时间查询 · 结束时间不包含边界时刻</span><button type="button" @click="resetFilters">重置条件</button></div></div><p v-if="error" role="alert" class="request-health">{{ error }}</p></form>
    </section>
    <p v-if="Object.values(health).some(value=>value>0)" role="status" class="request-health">诊断采集健康：{{ health }}</p>
    <div class="request-page-summary"><span><strong>{{ total }}</strong> 条匹配记录</span><span>本页成功 <b>{{ rows.filter(row=>['success','cache_hit'].includes(row.outcome)).length }}</b></span><span>本页错误 <b>{{ rows.filter(row=>outcomeTone(row.outcome)==='diagnostic-error').length }}</b></span><small>保留 7 天</small></div>
    <section class="request-records" :aria-busy="loading"><table><thead><tr><th>时间 / 请求</th><th>账号</th><th class="request-extra">模型 / 转发方式</th><th>结果</th><th class="request-extra">总耗时 / 首输出</th><th class="request-extra">Token（末次）</th><th class="request-extra">尝试</th><th class="request-extra">原始 Session ID</th><th>操作</th></tr></thead><tbody><tr v-for="row in rows" :key="row.request_id"><td><time :datetime="row.started_at">{{ formatLocalTime(row.started_at, false) }}</time><div class="request-id"><code>{{ row.request_id.slice(0,8) }}…</code><button type="button" :aria-label="`复制请求 ${row.request_id}`" @click="copy(row.request_id,$event)"><Copy :size="12" /></button><span>{{ row.log_mode || '模式未知' }}</span></div></td><td class="request-account-cell"><div class="request-account-identity"><InfoTooltip :label="`查看账号资料 ${row.account_name?.trim() || row.account_email?.trim() || accountLabel(row)}`"><template #trigger><strong class="request-account-name">{{ row.account_name?.trim() || row.account_email?.trim() || accountLabel(row) }}</strong></template><p>{{ row.account_name?.trim() || row.account_email?.trim() || accountLabel(row) }}</p><p v-if="row.account_email?.trim() && row.account_email.trim() !== row.account_name?.trim()">{{ row.account_email }}</p></InfoTooltip></div><div class="request-account-meta"><PlatformBadge :platform="row.context?.platform" /><ExecutionNodeBadge compact :node="row.last_attempt?.execution_location" :empty-label="row.attempt_count===0 ? '无执行尝试' : '节点未观测'" /></div></td><td class="request-extra"><strong>{{ row.last_attempt?.parameters?.model || row.last_attempt?.response_model || '未观测' }}</strong><small class="request-forwarding">{{ row.last_attempt?.context?.kernel === 'agy' ? 'AGY 原生运行时' : row.last_attempt?.profile_selection?.includes('native') ? '原生运行时' : row.last_attempt ? '原有转发' : '转发方式未观测' }} · {{ row.last_attempt?.profile_version || '未观测' }}</small></td><td><button type="button" class="request-result-button" @click="open(row,$event)"><span class="request-status" :class="outcomeTone(row.outcome).replace('diagnostic-','is-')"><i></i>{{ outcomeLabel(row.outcome) }}<small>{{ row.status_code ?? '待终结' }}</small></span></button></td><td class="request-extra"><strong>{{ milliseconds(elapsed(row)) }}</strong><small>首输出 {{ milliseconds(row.last_attempt?.first_output_ms) }}</small></td><td class="request-extra"><strong>{{ row.last_attempt?.tokens?.input_tokens?.toLocaleString() ?? '—' }} / {{ row.last_attempt?.tokens?.output_tokens?.toLocaleString() ?? '—' }}</strong><small>缓存读 {{ row.last_attempt?.tokens?.cache_read_tokens?.toLocaleString() ?? '—' }}</small><small data-cache-write>缓存写 {{ row.last_attempt?.tokens?.cache_write_tokens?.toLocaleString() ?? '—' }}</small><small data-average-tps :title="tpsDescription">平均 TPS {{ averageTps(row.last_attempt) }}</small></td><td class="request-extra">{{ row.attempt_count }}</td><td class="request-extra"><div v-if="row.original_session_id" class="request-session"><code :title="row.original_session_id">{{ row.original_session_id }}</code><button type="button" :aria-label="`复制原始 Session ID ${row.original_session_id}`" @click="copy(row.original_session_id,$event)"><Copy :size="12" /></button></div><small v-else>未提供</small></td><td><Button variant="ghost" size="sm" aria-label="详情" @click="open(row,$event)">详情<ArrowUpRight :size="13" /></Button></td></tr><tr v-if="!rows.length"><td colspan="9" class="request-empty"><FileText :size="28" /><strong>{{ loading ? '正在读取记录…' : '没有符合条件的请求' }}</strong><p>可以调整结果、时间或关联 ID。</p><Button size="sm" variant="outline" @click="resetFilters">重置查询</Button></td></tr></tbody></table></section>
    <footer class="request-list-footer"><p>模型、节点、Token、首输出取末次尝试；总耗时按请求起止时间计算。</p><Pagination v-model:page-size="pageSize" :page="page" :total="total" :disabled="loading" label="请求记录分页" @update:page="load" /></footer>
    <Dialog :open="dialogOpen" @update:open="setDialogOpen">
      <DialogContent class="request-workspace translate-x-0 translate-y-0 flex flex-col gap-0 overflow-hidden p-0" @close-auto-focus="restoreFocus">
        <DialogHeader class="request-detail-head">
          <span class="request-detail-eyebrow">请求诊断</span>
          <DialogTitle>请求详情</DialogTitle>
          <DialogDescription class="request-detail-identity"><code>{{ selected?.request_id }}</code><button v-if="selected" type="button" data-request-copy aria-label="复制完整请求 ID" @click="copy(selected.request_id, $event)"><Copy :size="13" /></button></DialogDescription>
        </DialogHeader>
        <div role="tablist" aria-label="请求详情分类" class="request-detail-tabs" @keydown="tabKeys"><button v-for="tab in tabs" :id="`request-tab-${tab.id}`" :key="tab.id" type="button" role="tab" :aria-selected="activeTab === tab.id" :aria-controls="`request-panel-${tab.id}`" :tabindex="activeTab === tab.id ? 0 : -1" :class="{active:activeTab === tab.id}" @click="activeTab = tab.id">{{ tab.label }}</button></div>
        <div class="request-detail-scroll">
          <p v-if="detailLoading" role="status" class="form-help">读取中…</p><p v-if="detailError" role="alert" class="text-destructive">{{ detailError }}</p>
          <section v-if="selected" :id="`request-panel-${activeTab}`" role="tabpanel" :aria-labelledby="`request-tab-${activeTab}`" tabindex="0" class="outline-none">
            <template v-if="activeTab === 'overview'">
              <div class="request-detail-hero"><div><span class="request-status" :class="outcomeTone(selected.outcome).replace('diagnostic-','is-')"><i></i>{{ outcomeLabel(selected.outcome) }}<small>{{ selected.status_code ?? '待终结' }}</small></span><h3>{{ selected.account_name || selected.account_email || accountLabel(selected) }}</h3><p>{{ selected.account_email || '暂无账号邮箱' }}</p></div><div><span>请求总耗时</span><strong>{{ milliseconds(elapsed(selected)) }}</strong></div></div>
              <div v-if="selected.error_stage" class="request-error-explanation"><AlertCircle /><div><strong>{{ outcomeLabel(selected.outcome) }}</strong><p v-if="attempts.at(-1)?.error_type === 'RESOURCE_EXHAUSTED'">上游额度不足或触发限流（RESOURCE_EXHAUSTED）</p><p>错误阶段：{{ selected.error_stage === 'upstream_model' ? '上游模型' : selected.error_stage }}{{ selected.status_code===200 ? (attempts.at(-1)?.partial === false ? ' · HTTP 200，模型响应已结束' : ' · HTTP 200，响应未完整结束') : '' }}</p></div></div>
              <div v-if="selected.native_rejection" class="request-error-explanation"><AlertCircle /><div><strong>{{ rejectionLabel(selected.native_rejection.reason) }}</strong><p>本次在上游发送前拒绝。入口采集状态：{{ captureLabel(selected.native_rejection.capture_status) }}<template v-if="selected.context?.input_rejection_field"> · <code>{{ selected.context.input_rejection_field }}</code></template></p><button type="button" class="btn small" :disabled="detailLoading" @click="inspect()">查看入站请求</button></div></div>
              <div v-else-if="selected.context?.input_rejection_reason" class="request-error-explanation"><AlertCircle /><div><strong>请求在上游发送前被拒绝</strong><p><code>{{ selected.context.input_rejection_reason }}</code><template v-if="selected.context.input_rejection_field"> · <code>{{ selected.context.input_rejection_field }}</code></template></p><button v-if="currentAttempt && canInspect(currentAttempt)" type="button" class="btn small" :disabled="detailLoading" @click="inspect(currentAttempt)">查看入站请求</button></div></div>
              <dl class="request-definitions"><dt>开始时间</dt><dd :title="selected.started_at">{{ formatLocalTime(selected.started_at) }}</dd><dt>结束时间</dt><dd :title="selected.finished_at ?? undefined">{{ formatLocalTime(selected.finished_at) }}</dd><dt>原始 Session ID</dt><dd><div v-if="selected.original_session_id" class="request-session request-session-full"><code>{{ selected.original_session_id }}</code><button type="button" :aria-label="`复制原始 Session ID ${selected.original_session_id}`" @click="copy(selected.original_session_id,$event)"><Copy :size="12" /></button></div><span v-else>未提供</span></dd><dt>账号平台</dt><dd>{{ platformLabel(selected.context?.platform) }}</dd><dt>入口协议</dt><dd>{{ selected.context?.entry_protocol ?? '历史未记录' }}</dd><dt>请求模型</dt><dd>{{ selected.context?.requested_model ?? '历史未记录' }}</dd><dt>响应关联 ID</dt><dd><code>{{ selected.response_request_id ?? '未观测' }}</code></dd><dt>发生时日志</dt><dd>{{ selected.log_mode || '历史模式未知' }}</dd><dt>尝试次数</dt><dd>{{ selected.attempt_count }}</dd><dt>末次执行节点</dt><dd><ExecutionNodeBadge compact :node="latestExecution" :empty-label="selected.attempt_count===0 ? '无执行尝试' : '节点未观测'" /></dd><dt>显示时区</dt><dd>{{ Intl.DateTimeFormat().resolvedOptions().timeZone }}</dd></dl>
              <section class="request-section"><div class="request-section-head"><h3>上游尝试</h3><span>{{ attempts.length }} 次</span></div>
                <article v-for="attempt in attempts" :key="attempt.attempt_id" class="request-attempt-summary"><div class="request-attempt-icon">{{ attempt.ordinal }}</div><div><strong>{{ attempt.account_name || attempt.account_email || accountLabel(attempt) }}</strong><small>{{ attempt.account_email || '暂无账号邮箱' }} · {{ attempt.parameters?.model || attempt.response_model || '模型未观测' }}</small><span>{{ captureLabel(attempt.capture_status) }} · {{ modeLabel(attempt.log_mode) }}</span><ExecutionNodeBadge compact :node="attempt.execution_location" /></div><div class="request-attempt-actions"><button type="button" class="btn small" @click="activeTab='chain'">查看链路<ArrowRight :size="13" /></button><button v-if="canInspect(attempt)" type="button" class="btn small" :disabled="detailLoading" @click="inspect(attempt)">阶段证据</button><router-link :to="{name:'environments',query:{gateway_account:String(attempt.account_id)}}" class="request-text-button">内容采集设置</router-link></div></article>
                <div v-if="!attempts.length && !detailLoading" class="request-empty-capture">此请求没有已记录的上游尝试。</div>
              </section>
            </template>
            <template v-else-if="activeTab === 'chain'">
              <div class="request-chain-heading"><h3>请求处理链路</h3><p>按实际提交顺序展示，每次尝试保留自己的账号与结果。</p></div>
              <article v-for="attempt in attempts" :key="attempt.attempt_id" class="request-chain-card"><header><span class="request-attempt-icon">{{ attempt.ordinal }}</span><div><h3>{{ attempt.account_name || attempt.account_email || accountLabel(attempt) }}</h3><p>{{ attempt.account_email || '暂无账号邮箱' }}</p></div><span class="request-status" :class="outcomeTone(attempt.outcome).replace('diagnostic-','is-')"><i></i>{{ outcomeLabel(attempt.outcome) }}<small>{{ attempt.status_code ?? '未观测' }}</small></span></header><dl class="request-definitions"><dt>执行节点</dt><dd><ExecutionNodeBadge compact :node="attempt.execution_location" /></dd><dt v-if="attempt.execution_location">环境代次</dt><dd v-if="attempt.execution_location">{{ attempt.execution_location.environment_id }} · {{ attempt.execution_location.generation }}</dd><dt>转发方式</dt><dd>{{ attempt.profile_selection }}</dd><dt>画像版本</dt><dd>{{ attempt.profile_version ?? '未观测' }}</dd><dt>上游模型</dt><dd>{{ attempt.response_model ?? '未观测' }}</dd><dt>上游请求 ID</dt><dd>{{ attempt.upstream_request_id ?? '未观测' }}</dd><dt>重试原因</dt><dd>{{ attempt.retry_reason ?? '未记录重试' }}</dd><dt>错误阶段</dt><dd>{{ attempt.error_stage ?? '未记录错误阶段' }}</dd><dt>账号平台 / 内核</dt><dd>{{ platformLabel(attempt.context?.platform) }} · {{ attempt.context?.kernel ?? '历史未记录' }} {{ attempt.context?.kernel_version ?? '' }}</dd><dt>实际提交模型</dt><dd>{{ attempt.context?.submitted_model ?? '历史未记录' }}</dd><dt>凭据代次</dt><dd>{{ attempt.context?.credential_generation ?? '未观测' }}</dd><dt>工作进程</dt><dd>{{ attempt.context?.worker_id ?? '未观测' }}</dd><dt>原生会话</dt><dd>{{ attempt.context?.conversation_id ?? '未观测' }}</dd><dt>原生控制收口</dt><dd>{{ ({completed:'已收口',cancelled:'已取消',error:'收口异常'} as Record<string,string>)[attempt.context?.control_state ?? ''] ?? '未观测' }} · {{ formatLocalTime(attempt.context?.control_observed_at) }}<span v-if="attempt.context?.control_error_code"> · <code>{{ attempt.context.control_error_code }}</code></span><span v-if="attempt.context?.control_recovery"> · 恢复判定 <code>{{ attempt.context.control_recovery }}</code></span></dd><dt>系统提示词转换</dt><dd>{{ policyLabel(attempt) }}</dd><dt v-if="attempt.context?.system_prompt_policy">规则 / 来源</dt><dd v-if="attempt.context?.system_prompt_policy">{{ attempt.context.system_prompt_policy.rule_version }} · {{ attempt.context.system_prompt_policy.source ?? '未观测' }}</dd><template v-if="attempt.context?.tool_turn"><dt>工具最近观测</dt><dd>{{ ({waiting:'等待结果',completed:'已收口',cancelled:'已取消',error:'收口异常',continuation:'后续HTTP'} as Record<string,string>)[attempt.context.tool_turn.state] ?? '未观测' }} · {{ formatLocalTime(attempt.context.tool_turn.observed_at) }}</dd><dt>前驱HTTP请求</dt><dd>{{ attempt.context.tool_turn.continuation_of_request_id ?? '首轮' }}</dd></template><dt>真实会话摘要</dt><dd>{{ attempt.sessions?.real_session_hash ?? '未观测' }}</dd><dt>上游会话摘要</dt><dd>{{ attempt.sessions?.upstream_session_hash ?? '未观测' }}</dd></dl></article>
              <div v-if="!attempts.length && !detailLoading" class="request-empty-capture">没有已记录的上游尝试。</div>
            </template>
            <template v-else-if="activeTab === 'performance'">
              <section v-for="attempt in attempts" :key="attempt.attempt_id" class="request-performance-card"><header><h3><InfoTooltip :label="'账号 ' + accountLabel(attempt)" title="尝试账号" portal-target=".request-workspace"><template #trigger>尝试 {{ attempt.ordinal }} · {{ attempt.account_name || attempt.account_email || accountLabel(attempt) }}</template><p>{{ attempt.account_name || '名称未提供' }}</p><p>{{ attempt.account_email || '邮箱未提供' }}</p><p>账号 ID：{{ attempt.account_id ?? '未知' }}</p></InfoTooltip></h3><span>{{ attempt.response_model || '模型未观测' }}</span></header><div class="request-performance-metrics"><div><span>{{ attempt.context?.kernel === 'agy' ? '发送器响应头耗时' : '响应头耗时' }}</span><strong>{{ milliseconds(attempt.ttft_ms) }}</strong></div><div><span>首次有效输出</span><strong>{{ milliseconds(attempt.first_output_ms) }}</strong></div><div><span>本次尝试耗时</span><strong>{{ milliseconds(attempt.duration_ms) }}</strong></div><div :title="tpsDescription"><span>平均 TPS</span><strong data-average-tps>{{ averageTps(attempt) }}</strong></div></div>
                <div v-if="attempt.runtime" class="request-runtime" data-native-runtime><div><strong>{{ attempt.runtime.warm_hit ? '命中热进程' : '本次等待初始化' }}</strong><span>PID {{ attempt.runtime.worker_pid }}</span></div><div class="request-runtime-metrics"><span>准备等待<b>{{ milliseconds(attempt.runtime.preparation_wait_ms) }}</b></span><span>获取进程<b>{{ milliseconds(attempt.runtime.checkout_ms) }}</b></span><span>进程启动<b>{{ attempt.runtime.worker_start_ms == null ? '沿用现有进程' : milliseconds(attempt.runtime.worker_start_ms) }}</b></span><span>本地准备合计<b>{{ milliseconds(attempt.runtime.prepared_ms) }}</b></span></div><p>本地准备包含等待与获取进程，各项存在包含关系。</p></div><p v-else class="form-help">原生进程与本地阶段：未观测</p>
                <div class="request-token-metrics"><div><span>输入 Token</span><strong>{{ attempt.tokens?.input_tokens?.toLocaleString('zh-CN') ?? '未观测' }}</strong></div><div><span>输出 Token</span><strong>{{ attempt.tokens?.output_tokens?.toLocaleString('zh-CN') ?? '未观测' }}</strong></div><div><span>缓存读取</span><strong>{{ attempt.tokens?.cache_read_tokens?.toLocaleString('zh-CN') ?? '未观测' }}</strong></div><div><span>缓存写入</span><strong>{{ attempt.tokens?.cache_write_tokens?.toLocaleString('zh-CN') ?? '未观测' }}</strong></div></div><div v-if="attempt.context?.usage" class="request-token-metrics" data-gemini-usage><div><span>源总 Token</span><strong>{{ attempt.context.usage.total_tokens ?? '未观测' }}</strong></div><div><span>思考 Token</span><strong>{{ attempt.context.usage.thoughts_tokens ?? '未观测' }}</strong></div><div><span>来源</span><strong>Gemini usageMetadata</strong></div></div><details v-if="attempt.context?.usage" class="request-code-block"><summary>平台原始用量 · {{ attempt.context.usage.complete ? '完整' : '有界观察存在缺口' }}</summary><pre>{{ JSON.stringify(attempt.context.usage.usage_metadata,null,2) }}</pre></details>
              </section>
              <div v-if="!attempts.length && !detailLoading" class="request-empty-capture">没有已记录的性能数据。</div>
            </template>
            <template v-else>
              <div v-if="selected.native_rejection" class="request-raw-controls"><button type="button" class="btn" :disabled="detailLoading" @click="inspect()"><RefreshCw :size="14" />{{ detailLoading ? '读取中…' : '读取拒绝请求的入站证据' }}</button><span>{{ rejectionLabel(selected.native_rejection.reason) }}</span></div>
              <div class="request-raw-controls"><ChoiceSelect :model-value="currentAttempt?.attempt_id" label="当前尝试" :options="attempts.map(attempt=>({value:attempt.attempt_id,label:`尝试 ${attempt.ordinal} · ${accountLabel(attempt)}`}))" @update:model-value="value=>{selectedAttempt=value;changeAttempt()}" /><button v-if="currentAttempt && canInspect(currentAttempt)" type="button" class="btn" :disabled="detailLoading" @click="inspect(currentAttempt)"><RefreshCw :size="14" />{{ detailLoading ? '读取中…' : capture ? '刷新阶段证据' : '读取阶段证据' }}</button></div>
              <div v-if="currentAttempt && !canInspect(currentAttempt)" class="request-empty-capture"><ShieldCheck :size="20" /><strong>{{ currentAttempt.log_mode === 'info' ? '本次仅保存摘要' : captureLabel(currentAttempt.capture_status) }}</strong><p>完整阶段原文需要账号内容采集开启及 debug 日志模式。设置对后续请求生效。</p><router-link :to="{name:'environments',query:{gateway_account:String(currentAttempt.account_id)}}" class="btn small">前往该账号环境配置<ArrowRight :size="13" /></router-link></div>
              <section v-else-if="capture"><p v-if="!['available', 'saved'].includes(capture.state) || capture.message" role="status" class="form-help">阶段证据 · {{ capture.state === 'missing' ? '文件缺失或已清理' : capture.state === 'expired' ? '已超过保留期' : ['available', 'saved'].includes(capture.state) ? '已读取' : capture.state }}{{ capture.message ? ' · '+capture.message : '' }}</p><NativeStageDetails v-if="capture.snapshot" :key="selectedAttempt" :snapshot="capture.snapshot" /></section>
              <div v-else-if="!detailLoading" class="request-empty-capture"><strong>按需读取阶段证据</strong><p>选择上方尝试后读取脱敏处理信息。</p></div>
              <details class="request-code-block"><summary>已脱敏诊断字段 · 原始时间</summary><pre>{{ JSON.stringify({request:selected,attempts},null,2) }}</pre></details>
            </template>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  </section>
</template>

<style scoped>
.diagnostic-badge { display: inline-flex; align-items: center; gap: .35rem; border: 1px solid var(--border); border-radius: 6px; padding: 3px 8px; font-size: var(--ui-font-small); font-weight: 500; white-space: nowrap; }
button.diagnostic-badge { cursor: pointer; }
.diagnostic-badge:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.diagnostic-success { background: #effaf3; border-color: #d5eedf; color: #237348; }
.diagnostic-pending { background: #eff6ff; border-color: #dbeafe; color: #2563eb; }
.diagnostic-error { background: #fff4f2; border-color: #fee0d8; color: #b4533e; }
.diagnostic-metric { min-width: 0; border: 1px solid var(--border); border-radius: 10px; padding: 12px; background: var(--card); }
.diagnostic-metric span { display: block; color: var(--muted-foreground); font-size: var(--ui-font-small); }
.diagnostic-metric strong { display: block; margin-top: 6px; font: 600 var(--ui-font-card) var(--font-mono); overflow-wrap: anywhere; }
.diagnostic-definition { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 12px 20px; font-size: var(--ui-font-small); }
.diagnostic-definition dt { color: var(--muted-foreground); }
.diagnostic-definition dd { min-width: 0; overflow-wrap: anywhere; }
@media (max-width: 480px) { .diagnostic-definition { grid-template-columns: 1fr; gap: 4px; } .diagnostic-definition dd { margin-bottom: 8px; } }
</style>
