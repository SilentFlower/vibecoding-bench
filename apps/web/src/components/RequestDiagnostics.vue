<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { Copy, RefreshCw, Search, FileText, ArrowRight, ShieldCheck, Activity, AlertCircle, Clock, Filter, SlidersHorizontal } from './ui/icon';
import { ChoiceSelect, SearchInput, DateTimeControl, InfoTooltip, Pagination } from './ui/controls';
import AccountFilterSelect from './AccountFilterSelect.vue';
import '../request-records.css';
import { formatLocalTime } from '../lib/time';
import { useToast } from '../composables/useToast';
import NativeStageDetails from './NativeStageDetails.vue';
import ExecutionNodeBadge from './runtime/ExecutionNodeBadge.vue';
import { agyToolContinuationLabels } from './runtime/runtimeApi';
import PlatformBadge from './PlatformBadge.vue';
import RequestSessionId from './RequestSessionId.vue';
import { api, type DiagnosticRequest, type DiagnosticAttempt, type NativeCapture } from '../api';
import { Button } from '@/components/ui/button';
import { Badge, type BadgeVariants } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import { ModalDialog } from '@/components/ui/modal';
import { OverviewCard, OverviewGrid } from '@/components/ui/overview';
import { TableCard } from '@/components/ui/table-card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Toolbar } from '@/components/ui/toolbar';
import { Segmented, type SegmentedOption } from '@/components/ui/segmented';
import { IconTile } from '@/components/ui/icon-tile';
import { NoticeStrip } from '@/components/ui/notice-strip';
import { Empty } from '@/components/ui/empty';

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
// 快捷分段与具体结果同一维度：选了具体结果时分段无选中项；计数来自接口，缺失显示「—」。
const quickOptions = computed<SegmentedOption[]>(() => [{value:'all',label:'全部',count:counts.value?.all ?? '—'},{value:'errors',label:'错误',count:counts.value?.errors ?? '—'},{value:'processing',label:'处理中',count:counts.value?.processing ?? '—'}]);
const outcomeOptions=['success','in_progress','incomplete','local_rejected','local_response','mock','cache_hit','upstream_rejected','upstream_error','transport_error','body_error','cancelled'].map(value=>({value,label:outcomeLabel(value)}));
/** 快捷结果和具体结果使用同一查询维度。@param value 快捷结果。@return 无。 */
function chooseQuick(value: string): void { quick.value=value;outcome.value='';void load(); }
/** 筛选区是否有生效条件，用于「筛选」按钮上的圆点。 */
const filtersActive = computed(() => !!(account.value || outcome.value || since.value || until.value || platform.value || protocol.value || kernelVersion.value || requestedModel.value || actualModel.value));
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
const rejectionEvidence = computed(() => {
  const request = selected.value;
  return request && !tuiSubmissionUnknown(request) ? request.native_rejection : undefined;
});
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
    account_selection: '账号选择阶段返回', tool_continuation: '原工具轮回填或收尾失败',
    credentials: '账号凭据检查失败', runtime_prepare: '运行环境准备失败',
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
  const request = selected.value;
  if (!request) return;
  const rejection = attempt ? undefined : rejectionEvidence.value;
  const captureId = attempt?.attempt_id ?? rejection?.capture_id;
  if (!captureId || (attempt && !canInspect(attempt))) return;
  activeTab.value = 'raw';
  const requestId = request.request_id;
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

/** 日志卡数值：当前后续请求模式；读取失败与读取中分开显示。 */
const modeValue = computed(() => mode.value === 'info' ? 'info · 摘要' : mode.value === 'debug' ? 'debug · 脱敏内容' : modeError.value ? '读取失败' : '读取中');
/** 日志卡无障碍名称写明当前值与点击后的目标值。 */
const modeLabelText = computed(() => mode.value === 'unknown' ? `后续请求日志：${modeValue.value}` : `后续请求日志：${modeValue.value}，点击切换为 ${mode.value === 'info' ? 'debug · 脱敏内容' : 'info · 摘要'}`);

/** 展示每次请求冻结的模式。@param value 实际模式。@return 中文标签。 */
function modeLabel(value?: string | null): string {
  return value === 'info' ? 'info（摘要）' : value === 'debug' ? 'debug（脱敏内容）' : '历史模式未知';
}

/** 显示持久化的采集状态。@param status 尝试采集状态。@return 中文标签。 */
function captureLabel(status?: string | null): string {
  return ({ not_submitted: '模型提交前已结束', queued: '后台采集已排队', saved: '已采集', disabled: '采集已关闭', dropped: '采集繁忙，已丢弃', failed: '采集失败', timeout: '采集超时，保存结果待核对' } as Record<string, string>)[status ?? ''] ?? '采集状态缺失';
}


const currentAttempt = computed(() => attempts.value.find(item => item.attempt_id === selectedAttempt.value) ?? attempts.value[0]);

/** 按冻结状态判断是否提供私有文件读取。@param attempt 当前尝试。@return 是否可读取。 */
function canInspect(attempt: DiagnosticAttempt): boolean {
  if (attempt.context?.kernel === 'tui_v2') {
    return attempt.log_mode === 'debug' && ['saved', 'queued', 'timeout'].includes(attempt.capture_status ?? '');
  }
  return ['native280_cc_prepared', 'native293_cc_prepared', 'agy_native'].includes(attempt.profile_selection ?? '') && attempt.log_mode !== 'info'
    && [null, undefined, 'saved', 'queued', 'timeout'].includes(attempt.capture_status);
}

/** 显示响应结果，保留未知服务端状态。@param value 持久结果。@return 中文标签。 */
function outcomeLabel(value: string): string {
  return ({success: '成功', in_progress: '处理中', incomplete: '未完整结束', cancelled: '已取消',
    upstream_error: '上游错误', local_rejected: '本地拒绝', transport_error: '传输错误', body_error: '响应读取失败',
    timeout: '已超时', mock: '模拟响应', cache_hit: '命中缓存'} as Record<string, string>)[value] ?? value;
}

/** 按私有提交边界识别结果待核对的请求，兼容旧记录。@param request 请求摘要。@return 提交状态是否未知。 */
function tuiSubmissionUnknown(request: DiagnosticRequest): boolean {
  return request.status_code === 502 && request.error_stage === 'tui_send_http';
}

/** 显示请求级结果。@param request 请求摘要。@return 中文结果。 */
function requestOutcomeLabel(request: DiagnosticRequest): string {
  return tuiSubmissionUnknown(request) ? '提交状态未知' : outcomeLabel(request.outcome);
}

/** 结果色只依据持久终态。@param value 持久结果。@return 徽标变体：成功、处理中、其余为错误。 */
function outcomeVariant(value: string): BadgeVariants['variant'] {
  return ['success', 'cache_hit'].includes(value) ? 'success' : value === 'in_progress' ? 'info' : 'destructive';
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
    <PageHeader title="请求记录" description="从请求结果、用量到处理链路，快速找到需要关注的调用。">
      <template v-if="mode === 'debug'" #actions><div class="request-diagnostics-settings"><ChoiceSelect :model-value="rejectedBody" label="正文采集范围" :options="[{value:'preview',label:'限长预览'},{value:'full',label:'完整正文 · 脱敏'}]" :disabled="modeSaving" @update:model-value="saveDiagnostics" /></div></template>
    </PageHeader>
    <OverviewGrid class="request-overview">
      <OverviewCard label="全部记录" :value="counts?.all ?? '—'" caption="保留 7 天"><template #icon><Activity /></template></OverviewCard>
      <OverviewCard label="错误" :value="counts?.errors ?? '—'" caption="六类错误集合" tone="danger"><template #icon><AlertCircle /></template></OverviewCard>
      <OverviewCard label="处理中" :value="counts?.processing ?? '—'" caption="按当前筛选统计" tone="info"><template #icon><Clock /></template></OverviewCard>
      <OverviewCard interactive class="request-mode-card" label="后续请求日志" :value="modeValue" :caption="modeSaving ? '保存中…' : '仅影响后续请求 · 点击切换'" tone="warning" :disabled="modeSaving || mode === 'unknown'" :aria-label="modeLabelText" @click="saveDiagnostics(mode === 'info' ? 'debug' : 'info')"><template #icon><SlidersHorizontal /></template></OverviewCard>
    </OverviewGrid>
    <NoticeStrip v-if="modeError" tone="danger" role="alert"><AlertCircle />{{ modeError }}</NoticeStrip>
    <NoticeStrip v-if="Object.values(health).some(value=>value>0)" tone="warning" role="status" class="request-health"><AlertCircle />诊断采集健康：{{ health }}</NoticeStrip>
    <TableCard class="request-records" :aria-busy="loading">
      <template #toolbar>
        <form class="request-query" @submit.prevent="load()">
          <Toolbar>
            <Segmented :model-value="outcome ? '' : quick" :options="quickOptions" label="请求快捷筛选" @update:model-value="chooseQuick" />
            <template #end>
              <SearchInput v-model="correlation" label="请求关联 ID" placeholder="输入完整请求 ID / 响应关联 ID / 上游请求 ID" @search="load()" />
              <Button type="button" variant="outline" :aria-expanded="filtersOpen" aria-controls="request-filters" @click="filtersOpen=!filtersOpen"><Filter :size="14" />筛选<i v-if="filtersActive" class="request-filter-dot" /></Button>
              <Button type="submit" :disabled="loading"><Search :size="14" />查询</Button>
              <Button type="button" variant="outline" size="icon" aria-label="刷新" title="刷新" :disabled="loading" @click="load(page)"><RefreshCw :size="14" /></Button>
            </template>
          </Toolbar>
        </form>
      </template>
      <div v-show="filtersOpen" id="request-filters" class="request-filter-fields"><AccountFilterSelect v-model="account" platform="all" /><ChoiceSelect v-model="platform" label="账号平台" :options="platformOptions" /><ChoiceSelect v-model="protocol" label="入口协议" :options="protocolOptions" /><SearchInput v-model="kernelVersion" label="内核版本" placeholder="输入完整内核版本" @search="load()" /><SearchInput v-model="requestedModel" label="请求模型" placeholder="精确请求模型" @search="load()" /><SearchInput v-model="actualModel" label="实际模型" placeholder="实际提交模型标识" @search="load()" /><ChoiceSelect :model-value="outcome" label="具体结果" :options="[{value:'',label:'全部结果'},...outcomeOptions]" @update:model-value="value=>{outcome=value;quick='all'}" /><DateTimeControl v-model="since" label="开始时间" /><DateTimeControl v-model="until" label="结束时间" /><div class="request-filter-footer"><span>按浏览器本地时间查询 · 结束时间不包含边界时刻</span><Button type="button" variant="ghost" size="sm" @click="resetFilters">重置条件</Button></div></div>
      <NoticeStrip v-if="error" tone="danger" role="alert" class="request-error"><AlertCircle />{{ error }}</NoticeStrip>
      <Table class="request-table fui-table-fixed">
        <!-- 列宽在设计稿 colgroup 15/10/15/13/10/16/5/9/7（%）基础上给账号列让出徽标空间，见 request-records.css。 -->
        <TableHeader><TableRow><TableHead class="request-col-time">时间 / 请求</TableHead><TableHead class="request-col-account">账号</TableHead><TableHead class="request-col-model request-extra">模型 / 转发方式</TableHead><TableHead class="request-col-result">结果</TableHead><TableHead class="request-col-duration request-extra">总耗时 / 首输出</TableHead><TableHead class="request-col-token request-extra">Token（末次）</TableHead><TableHead class="request-col-attempts request-extra fui-table-end">尝试</TableHead><TableHead class="request-col-session request-extra">原始 Session ID</TableHead><TableHead class="request-col-actions fui-table-end">操作</TableHead></TableRow></TableHeader>
        <TableBody>
          <TableRow v-for="row in rows" :key="row.request_id">
            <TableCell><time class="fui-table-num" :datetime="row.started_at">{{ formatLocalTime(row.started_at, false) }}</time><span class="fui-table-sub request-id"><code class="fui-table-mono">{{ row.request_id.slice(0,8) }}…</code><button type="button" class="request-copy" :aria-label="`复制请求 ${row.request_id}`" @click="copy(row.request_id,$event)"><Copy :size="12" /></button><Badge as="span" variant="secondary">{{ row.log_mode || '模式未知' }}</Badge></span></TableCell>
            <TableCell class="request-account-cell"><div class="request-account-identity"><InfoTooltip :label="`查看账号资料 ${row.account_name?.trim() || row.account_email?.trim() || accountLabel(row)}`"><template #trigger><strong class="request-account-name">{{ row.account_name?.trim() || row.account_email?.trim() || accountLabel(row) }}</strong></template><p>{{ row.account_name?.trim() || row.account_email?.trim() || accountLabel(row) }}</p><p v-if="row.account_email?.trim() && row.account_email.trim() !== row.account_name?.trim()">{{ row.account_email }}</p></InfoTooltip></div><span class="fui-table-sub request-account-meta"><PlatformBadge :platform="row.context?.platform" /><ExecutionNodeBadge compact :node="row.last_attempt?.execution_location" :empty-label="row.attempt_count===0 && !tuiSubmissionUnknown(row) ? '无执行尝试' : '节点未观测'" /></span></TableCell>
            <TableCell class="request-extra">{{ row.last_attempt?.parameters?.model || row.last_attempt?.response_model || '未观测' }}<span class="fui-table-sub request-forwarding">{{ row.last_attempt?.context?.kernel === 'agy' ? 'AGY 原生运行时' : row.last_attempt?.profile_selection?.includes('native') ? '原生运行时' : row.last_attempt ? '原有转发' : '转发方式未观测' }} · {{ row.last_attempt?.profile_version || '未观测' }}</span></TableCell>
            <TableCell><button type="button" class="request-result-button" @click="open(row,$event)"><Badge as="span" :variant="outcomeVariant(row.outcome)" dot>{{ requestOutcomeLabel(row) }}</Badge><code class="fui-table-mono request-status-code">{{ row.status_code ?? '待终结' }}</code></button></TableCell>
            <TableCell class="request-extra"><strong class="fui-table-strong fui-table-num">{{ milliseconds(elapsed(row)) }}</strong><span class="fui-table-sub">首输出 {{ milliseconds(row.last_attempt?.first_output_ms) }}</span></TableCell>
            <TableCell class="request-extra"><span class="fui-table-num">{{ row.last_attempt?.tokens?.input_tokens?.toLocaleString() ?? '—' }} / {{ row.last_attempt?.tokens?.output_tokens?.toLocaleString() ?? '—' }}</span><span class="fui-table-sub fui-table-num">缓存读 {{ row.last_attempt?.tokens?.cache_read_tokens?.toLocaleString() ?? '—' }} · <span data-cache-write>缓存写 {{ row.last_attempt?.tokens?.cache_write_tokens?.toLocaleString() ?? '—' }}</span></span><span class="fui-table-sub fui-table-num" data-average-tps :title="tpsDescription">平均 TPS {{ averageTps(row.last_attempt) }}</span></TableCell>
            <TableCell class="request-extra fui-table-end fui-table-num">{{ row.attempt_count }}</TableCell>
            <TableCell class="request-extra"><RequestSessionId :request="row" @copy="copy" /></TableCell>
            <TableCell class="fui-table-end"><Button variant="ghost" size="sm" class="request-detail-button" aria-label="详情" @click="open(row,$event)">详情<ArrowRight :size="14" /></Button></TableCell>
          </TableRow>
          <TableRow v-if="!rows.length"><TableCell :colspan="9" class="request-empty"><Empty :title="loading ? '正在读取记录…' : '没有符合条件的请求'" description="可以调整结果、时间或关联 ID。"><template #icon><FileText /></template><template #actions><Button size="sm" variant="outline" @click="resetFilters">重置查询</Button></template></Empty></TableCell></TableRow>
        </TableBody>
      </Table>
      <template #footer><p class="request-footnote">模型、节点、Token、首输出取末次尝试；总耗时按请求起止时间计算。</p><Pagination v-model:page-size="pageSize" :page="page" :total="total" :disabled="loading" label="请求记录分页" @update:page="load" /></template>
    </TableCard>
    <ModalDialog :open="dialogOpen" placement="side" :width="1020" class="request-workspace" title="请求详情" @update:open="setDialogOpen" @close-auto-focus="restoreFocus">
      <template #media><IconTile size="lg"><FileText /></IconTile></template>
      <template #description><span class="request-detail-identity"><code>{{ selected?.request_id }}</code><button v-if="selected" type="button" class="request-copy" data-request-copy aria-label="复制完整请求 ID" @click="copy(selected.request_id, $event)"><Copy :size="13" /></button></span></template>
      <!-- 详情是真正的页签面板，保留 tablist / tab / tabpanel 语义与方向键切换，外观与分段控件一致。 -->
      <template #nav><div role="tablist" aria-label="请求详情分类" class="fui-segmented request-detail-tabs" @keydown="tabKeys"><button v-for="tab in tabs" :id="`request-tab-${tab.id}`" :key="tab.id" type="button" role="tab" class="fui-segmented-item" :data-state="activeTab === tab.id ? 'checked' : 'unchecked'" :aria-selected="activeTab === tab.id" :aria-controls="`request-panel-${tab.id}`" :tabindex="activeTab === tab.id ? 0 : -1" @click="activeTab = tab.id">{{ tab.label }}</button></div></template>
      <p v-if="detailLoading" role="status" class="form-help">读取中…</p>
      <NoticeStrip v-if="detailError" tone="danger" role="alert"><AlertCircle />{{ detailError }}</NoticeStrip>
      <section v-if="selected" :id="`request-panel-${activeTab}`" role="tabpanel" :aria-labelledby="`request-tab-${activeTab}`" tabindex="0" class="request-panel">
        <template v-if="activeTab === 'overview'">
          <div class="request-detail-hero"><div class="request-detail-hero-main"><span class="request-detail-outcome"><Badge as="span" :variant="outcomeVariant(selected.outcome)" dot>{{ requestOutcomeLabel(selected) }}</Badge><code class="fui-table-mono">{{ selected.status_code ?? '待终结' }}</code></span><h3>{{ selected.account_name || selected.account_email || accountLabel(selected) }}</h3><p>{{ selected.account_email || '暂无账号邮箱' }}</p></div><div class="request-detail-hero-metric"><span>请求总耗时</span><strong>{{ milliseconds(elapsed(selected)) }}</strong></div></div>
          <NoticeStrip v-if="selected.error_stage" tone="danger" class="request-error-explanation"><AlertCircle /><span><strong>{{ requestOutcomeLabel(selected) }}</strong><template v-if="tuiSubmissionUnknown(selected)"> · 模型可能已收到请求。请先核对原轮状态，再决定是否重投。</template><template v-if="attempts.at(-1)?.error_type === 'RESOURCE_EXHAUSTED'"> · 上游额度不足或触发限流（RESOURCE_EXHAUSTED）</template> · 错误阶段：{{ selected.error_stage === 'system_update' ? '系统更新中断' : selected.error_stage === 'upstream_model' ? '上游模型' : selected.error_stage }}{{ selected.status_code===200 ? (attempts.at(-1)?.partial === false ? ' · HTTP 200，模型响应已结束' : ' · HTTP 200，响应未完整结束') : '' }}</span></NoticeStrip>
          <NoticeStrip v-if="rejectionEvidence" tone="danger" class="request-error-explanation"><AlertCircle /><span><strong>{{ rejectionLabel(rejectionEvidence.reason) }}</strong> · 本次在上游发送前拒绝。入口采集状态：{{ captureLabel(rejectionEvidence.capture_status) }}<template v-if="selected.context?.input_rejection_field"> · <code>{{ selected.context.input_rejection_field }}</code></template></span><template #end><Button type="button" variant="outline" size="sm" :disabled="detailLoading" @click="inspect()">查看入站请求</Button></template></NoticeStrip>
          <NoticeStrip v-else-if="selected.context?.input_rejection_reason && !tuiSubmissionUnknown(selected)" tone="danger" class="request-error-explanation"><AlertCircle /><span><strong>请求在上游发送前被拒绝</strong> · <code>{{ selected.context.input_rejection_reason }}</code><template v-if="selected.context.input_rejection_field"> · <code>{{ selected.context.input_rejection_field }}</code></template></span><template v-if="currentAttempt && canInspect(currentAttempt)" #end><Button type="button" variant="outline" size="sm" :disabled="detailLoading" @click="inspect(currentAttempt)">查看入站请求</Button></template></NoticeStrip>
          <dl class="request-definitions"><dt>开始时间</dt><dd :title="selected.started_at">{{ formatLocalTime(selected.started_at) }}</dd><dt>结束时间</dt><dd :title="selected.finished_at ?? undefined">{{ formatLocalTime(selected.finished_at) }}</dd><dt>原始 Session ID</dt><dd><RequestSessionId :request="selected" full @copy="copy" /></dd><dt>账号平台</dt><dd>{{ platformLabel(selected.context?.platform) }}</dd><dt>入口协议</dt><dd>{{ selected.context?.entry_protocol ?? '历史未记录' }}</dd><dt>请求模型</dt><dd>{{ selected.context?.requested_model ?? '历史未记录' }}</dd><dt>响应关联 ID</dt><dd><code>{{ selected.response_request_id ?? '未观测' }}</code></dd><dt>发生时日志</dt><dd>{{ selected.log_mode || '历史模式未知' }}</dd><dt>已记录尝试次数</dt><dd>{{ selected.attempt_count }}</dd><template v-if="selected.context?.tui_reservation_id"><dt>发送器预留 ID</dt><dd><code>{{ selected.context.tui_reservation_id }}</code></dd></template><dt>末次执行节点</dt><dd><ExecutionNodeBadge compact :node="latestExecution" :empty-label="selected.attempt_count===0 && !tuiSubmissionUnknown(selected) ? '无执行尝试' : '节点未观测'" /></dd><dt>显示时区</dt><dd>{{ Intl.DateTimeFormat().resolvedOptions().timeZone }}</dd></dl>
          <section class="request-section"><div class="request-section-head"><h3>上游尝试</h3><span>{{ attempts.length }} 次</span></div>
            <article v-for="attempt in attempts" :key="attempt.attempt_id" class="request-attempt-summary"><span class="request-attempt-icon">{{ attempt.ordinal }}</span><div class="request-attempt-text"><strong>{{ attempt.account_name || attempt.account_email || accountLabel(attempt) }}</strong><small>{{ attempt.account_email || '暂无账号邮箱' }} · {{ attempt.parameters?.model || attempt.response_model || '模型未观测' }}</small><span>{{ captureLabel(attempt.capture_status) }} · {{ modeLabel(attempt.log_mode) }}</span><ExecutionNodeBadge compact :node="attempt.execution_location" /></div><div class="request-attempt-actions"><Button type="button" variant="outline" size="sm" @click="activeTab='chain'">查看链路<ArrowRight :size="13" /></Button><Button v-if="canInspect(attempt)" type="button" variant="outline" size="sm" :disabled="detailLoading" @click="inspect(attempt)">阶段证据</Button><router-link :to="{name:'environments',query:{gateway_account:String(attempt.account_id)}}" class="request-text-button">内容采集设置</router-link></div></article>
            <div v-if="!attempts.length && !detailLoading" class="request-empty-capture">此请求没有已记录的上游尝试。</div>
          </section>
        </template>
        <template v-else-if="activeTab === 'chain'">
          <div class="request-chain-heading"><h3>请求处理链路</h3><p>按实际提交顺序展示，每次尝试保留自己的账号与结果。</p></div>
          <article v-for="attempt in attempts" :key="attempt.attempt_id" class="request-chain-card"><header><span class="request-attempt-icon">{{ attempt.ordinal }}</span><div><h3>{{ attempt.account_name || attempt.account_email || accountLabel(attempt) }}</h3><p>{{ attempt.account_email || '暂无账号邮箱' }}</p></div><span class="request-detail-outcome"><Badge as="span" :variant="outcomeVariant(attempt.outcome)" dot>{{ outcomeLabel(attempt.outcome) }}</Badge><code class="fui-table-mono">{{ attempt.status_code ?? '未观测' }}</code></span></header><dl class="request-definitions"><dt>执行节点</dt><dd><ExecutionNodeBadge compact :node="attempt.execution_location" /></dd><dt v-if="attempt.execution_location">环境代次</dt><dd v-if="attempt.execution_location">{{ attempt.execution_location.environment_id }} · {{ attempt.execution_location.generation }}</dd><dt>转发方式</dt><dd>{{ attempt.profile_selection }}</dd><dt>画像版本</dt><dd>{{ attempt.profile_version ?? '未观测' }}</dd><dt>上游模型</dt><dd>{{ attempt.response_model ?? '未观测' }}</dd><dt>上游请求 ID</dt><dd>{{ attempt.upstream_request_id ?? '未观测' }}</dd><dt>重试原因</dt><dd>{{ attempt.retry_reason ?? '未记录重试' }}</dd><dt>错误阶段</dt><dd>{{ attempt.error_stage ?? '未记录错误阶段' }}</dd><dt>账号平台 / 内核</dt><dd>{{ platformLabel(attempt.context?.platform) }} · {{ attempt.context?.kernel ?? '历史未记录' }} {{ attempt.context?.kernel_version ?? '' }}</dd><dt>实际提交模型</dt><dd>{{ attempt.context?.submitted_model ?? '历史未记录' }}</dd><dt>凭据代次</dt><dd>{{ attempt.context?.credential_generation ?? '未观测' }}</dd><dt>工作进程</dt><dd>{{ attempt.context?.worker_id ?? '未观测' }}</dd><dt>原生会话</dt><dd>{{ attempt.context?.conversation_id ?? '未观测' }}</dd><dt>原生控制收口</dt><dd>{{ ({completed:'已收口',cancelled:'已取消',error:'收口异常'} as Record<string,string>)[attempt.context?.control_state ?? ''] ?? '未观测' }} · {{ formatLocalTime(attempt.context?.control_observed_at) }}<span v-if="attempt.context?.control_error_code"> · <code>{{ attempt.context.control_error_code }}</code></span><span v-if="attempt.context?.control_recovery"> · 恢复判定 <code>{{ attempt.context.control_recovery }}</code></span><span v-if="attempt.context?.observed_control_http_status != null"> · 控制 HTTP {{ attempt.context.observed_control_http_status }}</span><span v-if="attempt.context?.control_error_detail === 'unexpected_eof'"> · 响应读取中断</span></dd><template v-if="attempt.context?.native_receive_ended != null"><dt>原生流状态</dt><dd>{{ attempt.context.native_receive_ended ? '接收已结束' : '接收未结束' }} · {{ attempt.context.native_source_terminal ? '已收到模型终态' : '未收到模型终态' }}</dd></template><template v-if="attempt.context?.tool_continuation_path"><dt>工具续轮</dt><dd>{{ agyToolContinuationLabels[attempt.context.tool_continuation_mode ?? ''] ?? '未观测' }} → {{ agyToolContinuationLabels[attempt.context.tool_continuation_path] ?? '未观测' }}<span v-if="attempt.context.tool_continuation_reason === 'original_closed'"> · 原工具轮已确认关闭</span><span v-else-if="attempt.context.tool_continuation_reason === 'web_search'"> · 沿用 WebSearch 回调</span></dd></template><dt>系统提示词转换</dt><dd>{{ policyLabel(attempt) }}</dd><dt v-if="attempt.context?.system_prompt_policy">规则 / 来源</dt><dd v-if="attempt.context?.system_prompt_policy">{{ attempt.context.system_prompt_policy.rule_version }} · {{ attempt.context.system_prompt_policy.source ?? '未观测' }}</dd><template v-if="attempt.context?.tool_turn"><dt>工具最近观测</dt><dd>{{ ({waiting:'等待结果',completed:'已收口',cancelled:'已取消',error:'收口异常',continuation:'后续HTTP'} as Record<string,string>)[attempt.context.tool_turn.state] ?? '未观测' }} · {{ formatLocalTime(attempt.context.tool_turn.observed_at) }}</dd><dt>前驱HTTP请求</dt><dd>{{ attempt.context.tool_turn.continuation_of_request_id ?? '首轮' }}</dd></template><dt>真实会话摘要</dt><dd>{{ attempt.sessions?.real_session_hash ?? '未观测' }}</dd><dt>上游会话摘要</dt><dd>{{ attempt.sessions?.upstream_session_hash ?? '未观测' }}</dd></dl></article>
          <div v-if="!attempts.length && !detailLoading" class="request-empty-capture">没有已记录的上游尝试。</div>
        </template>
        <template v-else-if="activeTab === 'performance'">
          <section v-for="attempt in attempts" :key="attempt.attempt_id" class="request-performance-card"><header><h3><InfoTooltip :label="'账号 ' + accountLabel(attempt)" title="尝试账号" portal-target=".request-workspace"><template #trigger>尝试 {{ attempt.ordinal }} · {{ attempt.account_name || attempt.account_email || accountLabel(attempt) }}</template><p>{{ attempt.account_name || '名称未提供' }}</p><p>{{ attempt.account_email || '邮箱未提供' }}</p><p>账号 ID：{{ attempt.account_id ?? '未知' }}</p></InfoTooltip></h3><span>{{ attempt.response_model || '模型未观测' }}</span></header><div class="request-performance-metrics"><div><span>{{ attempt.context?.kernel === 'agy' ? '发送器响应头耗时' : '响应头耗时' }}</span><strong>{{ milliseconds(attempt.ttft_ms) }}</strong></div><div><span>首次有效输出</span><strong>{{ milliseconds(attempt.first_output_ms) }}</strong></div><div><span>本次尝试耗时</span><strong>{{ milliseconds(attempt.duration_ms) }}</strong></div><div :title="tpsDescription"><span>平均 TPS</span><strong data-average-tps>{{ averageTps(attempt) }}</strong></div></div>
            <div v-if="attempt.runtime" class="request-runtime" data-native-runtime><div class="request-runtime-head"><strong v-if="attempt.runtime.warm_hit">命中热进程</strong><strong v-else-if="attempt.runtime.start_source === 'criu_restore'">本次 CRIU 恢复</strong><strong v-else-if="attempt.runtime.start_source === 'exec'">本次普通启动</strong><strong v-else>本次等待初始化</strong><span>PID {{ attempt.runtime.worker_pid }}<template v-if="attempt.runtime.warm_hit && attempt.runtime.start_source"> · {{ attempt.runtime.start_source === 'criu_restore' ? 'CRIU 恢复启动' : '普通启动' }}</template></span></div><div class="request-runtime-metrics"><span>准备等待<b>{{ milliseconds(attempt.runtime.preparation_wait_ms) }}</b></span><span>获取进程<b>{{ milliseconds(attempt.runtime.checkout_ms) }}</b></span><span>{{ !attempt.runtime.warm_hit && attempt.runtime.start_source === 'criu_restore' ? '进程恢复' : '进程启动' }}<b>{{ attempt.runtime.worker_start_ms == null ? '沿用现有进程' : milliseconds(attempt.runtime.worker_start_ms) }}</b></span><span>本地准备合计<b>{{ milliseconds(attempt.runtime.prepared_ms) }}</b></span></div><p>本地准备包含等待与获取进程，各项存在包含关系。</p></div><p v-else class="form-help">原生进程与本地阶段：未观测</p>
            <div class="request-token-metrics"><div><span>输入 Token</span><strong>{{ attempt.tokens?.input_tokens?.toLocaleString('zh-CN') ?? '未观测' }}</strong></div><div><span>输出 Token</span><strong>{{ attempt.tokens?.output_tokens?.toLocaleString('zh-CN') ?? '未观测' }}</strong></div><div><span>缓存读取</span><strong>{{ attempt.tokens?.cache_read_tokens?.toLocaleString('zh-CN') ?? '未观测' }}</strong></div><div><span>缓存写入</span><strong>{{ attempt.tokens?.cache_write_tokens?.toLocaleString('zh-CN') ?? '未观测' }}</strong></div></div><div v-if="attempt.context?.usage" class="request-token-metrics" data-gemini-usage><div><span>源总 Token</span><strong>{{ attempt.context.usage.total_tokens ?? '未观测' }}</strong></div><div><span>思考 Token</span><strong>{{ attempt.context.usage.thoughts_tokens ?? '未观测' }}</strong></div><div><span>来源</span><strong>Gemini usageMetadata</strong></div></div><details v-if="attempt.context?.usage" class="request-code-block"><summary>平台原始用量 · {{ attempt.context.usage.complete ? '完整' : '有界观察存在缺口' }}</summary><pre>{{ JSON.stringify(attempt.context.usage.usage_metadata,null,2) }}</pre></details>
          </section>
          <div v-if="!attempts.length && !detailLoading" class="request-empty-capture">没有已记录的性能数据。</div>
        </template>
        <template v-else>
          <div v-if="rejectionEvidence" class="request-raw-controls"><Button type="button" variant="outline" :disabled="detailLoading" @click="inspect()"><RefreshCw :size="14" />{{ detailLoading ? '读取中…' : '读取拒绝请求的入站证据' }}</Button><span>{{ rejectionLabel(rejectionEvidence.reason) }}</span></div>
          <div v-if="attempts.length" class="request-raw-controls"><ChoiceSelect :model-value="currentAttempt?.attempt_id" label="当前尝试" :options="attempts.map(attempt=>({value:attempt.attempt_id,label:`尝试 ${attempt.ordinal} · ${accountLabel(attempt)}`}))" @update:model-value="value=>{selectedAttempt=value;changeAttempt()}" /><Button v-if="currentAttempt && canInspect(currentAttempt)" type="button" variant="outline" :disabled="detailLoading" @click="inspect(currentAttempt)"><RefreshCw :size="14" />{{ detailLoading ? '读取中…' : capture ? '刷新阶段证据' : '读取阶段证据' }}</Button></div>
          <div v-if="currentAttempt && !canInspect(currentAttempt)" class="request-empty-capture"><ShieldCheck :size="20" /><strong>{{ currentAttempt.log_mode === 'info' ? '本次仅保存摘要' : captureLabel(currentAttempt.capture_status) }}</strong><p>完整阶段原文需要账号内容采集开启及 debug 日志模式。设置对后续请求生效。</p><Button as-child variant="outline" size="sm"><router-link :to="{name:'environments',query:{gateway_account:String(currentAttempt.account_id)}}">前往该账号环境配置<ArrowRight :size="13" /></router-link></Button></div>
          <section v-else-if="capture"><p v-if="!['available', 'saved'].includes(capture.state) || capture.message" role="status" class="form-help">阶段证据 · {{ capture.state === 'missing' ? '文件缺失或已清理' : capture.state === 'expired' ? '已超过保留期' : ['available', 'saved'].includes(capture.state) ? '已读取' : capture.state }}{{ capture.message ? ' · '+capture.message : '' }}</p><NativeStageDetails v-if="capture.snapshot" :key="selectedAttempt" :snapshot="capture.snapshot" /></section>
          <div v-else-if="!detailLoading && (currentAttempt || !rejectionEvidence)" class="request-empty-capture">
            <strong>{{ currentAttempt ? '按需读取阶段证据' : '没有已记录的上游尝试' }}</strong>
            <p v-if="currentAttempt">选择上方尝试后读取脱敏处理信息。</p>
            <p v-else-if="tuiSubmissionUnknown(selected)">提交状态未知。请先核对原轮状态，再决定是否重投。</p>
          </div>
          <details class="request-code-block"><summary>已脱敏诊断字段 · 原始时间</summary><pre>{{ JSON.stringify({request:selected,attempts},null,2) }}</pre></details>
        </template>
      </section>
    </ModalDialog>
  </section>
</template>
