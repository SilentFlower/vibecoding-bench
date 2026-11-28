<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { useMediaQuery } from '@vueuse/core';
import { Pencil, RefreshCw, Activity, ArrowRight, Trash2, Globe, Box, Clock, ChevronRight, KeyRound, Plus, Check, AlertCircle, Search, Users } from '@/components/ui/icon';
import { NumberInput, ChoiceSelect, SearchInput, InfoTooltip, Pagination } from '@/components/ui/controls';
import { useRoute } from 'vue-router';
import ProxyPicker from './ProxyPicker.vue';
import ExecutionNodeBadge from './runtime/ExecutionNodeBadge.vue';
import PlatformBadge from './PlatformBadge.vue';
import { nodeApi, type AccountNodeAssignment, type AccountNodeSummary } from './runtime/nodeApi';
import { api, type ProxyRoute, type Account, type RequestBackend, type OAuthExchangeResult, type UsageWindow, type RuntimeEnvironmentSummary, type OverallWorkStatus } from '../api';
import AgyAccountUsage from './AgyAccountUsage.vue';
import UsageWindowStats from './UsageWindowStats.vue';
import SchedulingDetails from './SchedulingDetails.vue';
import { subscriptionLabel, fiveHourLabel, usageBarTone } from '../lib/subscription';
import { schedulingReasonLabel } from '../lib/scheduling';
import { accountUpdateDelta } from '../lib/accountUpdate';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge, type BadgeVariants } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Toolbar } from '@/components/ui/toolbar';
import { Segmented, type SegmentedOption } from '@/components/ui/segmented';
import { RadioCardGroup } from '@/components/ui/radio-card';
import { NoticeStrip } from '@/components/ui/notice-strip';
import { IconTile } from '@/components/ui/icon-tile';
import { EntityBlock } from '@/components/ui/entity-card';
import { Empty } from '@/components/ui/empty';
import { ModalDialog } from '@/components/ui/modal';
import { useToast } from '../composables/useToast';
import { OperationFeedback, ConfirmationDialog } from './ui/feedback';
import '../accounts.css';

const route = useRoute();
const props = defineProps<{ workspaceAccountId?: number }>();
let linkedGeneration = 0;
const proxyChoice = ref<ProxyRoute | null | undefined>();
/** 将代理草稿转为目录选择，保持原增量保存语义。@param payload 账号载荷。@return 无。 */
function applyProxyChoice(payload: Record<string, unknown>): void {
  if (proxyChoice.value === undefined) return;
  delete payload.proxy_url;
  payload.proxy_id = proxyChoice.value?.id ?? null;
  if (proxyChoice.value) payload.proxy_revision = proxyChoice.value.revision;
}
/** 通过代理使用者直达编辑，支持目标不在当前分页。@return 完成。 */
async function openLinkedAccount(): Promise<void> {
  const id = props.workspaceAccountId ?? Number(route.query.account);
  if (!Number.isSafeInteger(id) || id < 1) return;
  const generation = ++linkedGeneration;
  try {
    const account = accounts.value.find(value => value.id === id) ?? await api.accountById(id);
    if (generation !== linkedGeneration) return;
    if (!accounts.value.some(value => value.id === id)) accounts.value.push(account);
    void loadAccountNodes();
    openEdit(account);
  } catch (cause) {
    if (generation !== linkedGeneration) return;
    toast((cause as Error).message);
    if (props.workspaceAccountId) emit('close');
  }
}
watch(() => props.workspaceAccountId ?? route.query.account, () => { void openLinkedAccount(); });

const DEFAULT_ALLOW_1M_MODELS = 'opus,claude-sonnet-5';
const DEFAULT_UPSTREAM_SESSION_POOL_SIZE = 3;
const DEFAULT_UPSTREAM_SESSION_TTL_MINUTES = 60;
const DEFAULT_UPSTREAM_SESSION_REFRESH_POLICY = 'mapped_request';

const emit = defineEmits<{ refresh: []; close: [] }>();
const { show: toast } = useToast();

/** 账号列表 */
const accounts = ref<Account[]>([]);
const workPending = reactive(new Set<number>());
const overallStates = reactive(new Map<number, OverallWorkStatus>());
const accountNodes = ref(new Map<number, AccountNodeSummary>());
const agyNodes = ref(new Map<number, AccountNodeAssignment>());
const agyNodesLoaded = ref(false);
const agyNodesFailed = ref(false);
const nodeReadFailed = ref(false);
const nodeLoaded = ref(false);
let nodeController: AbortController | undefined;
let nodeGeneration = 0;

/** 批量读取已保存归属，旧页面及迟到回执不能覆盖当前节点。@return 读取结束。 */
async function loadAccountNodes(): Promise<void> {
  nodeController?.abort();
  const controller = new AbortController(), generation = ++nodeGeneration;
  nodeController = controller;
  try {
    await api.openRuntime();
    if (controller.signal.aborted) return;
    const [bindings, nodes] = await Promise.allSettled([
      api.runtimeAccountNodes(controller.signal),
      accounts.value.some(account => account.platform === 'antigravity') ? nodeApi.agyAssignments(controller.signal) : undefined,
    ]);
    if (controller.signal.aborted || generation !== nodeGeneration) return;
    if (nodes.status === 'fulfilled' && nodes.value) {
      agyNodes.value = new Map(nodes.value.items.map(node => [node.account_id, node]));
      agyNodesLoaded.value = true;
    }
    agyNodesFailed.value = nodes.status === 'rejected';
    if (bindings.status === 'rejected') throw bindings.reason;
    accountNodes.value = new Map(bindings.value.filter(row => row.cc2api_account_id != null).map(row => [row.cc2api_account_id!, row]));
    nodeReadFailed.value = false;
    nodeLoaded.value = true;
  } catch {
    if (!controller.signal.aborted && generation === nodeGeneration) {
      nodeReadFailed.value = true;
      if (!agyNodesLoaded.value) agyNodesFailed.value = true;
    }
  }
}

/** 从对应账号域读取持久分配。@param account 网关账号。@return 当前节点身份。 */
function accountNode(account: Account) {
  if (account.platform === 'antigravity') return agyNodes.value.get(account.id);
  return accountNodes.value.get(account.id)?.node;
}

/** 归属与缓存观察分别呈现，读取失败保留原身份。@param account 网关账号。@return 观察说明。 */
function nodeStatus(account: Account): string {
  if (account.platform === 'antigravity') {
    if (agyNodesFailed.value) return '归属待刷新';
    if (!agyNodesLoaded.value) return '归属读取中';
    const node = agyNodes.value.get(account.id);
    if (!node) return '运行环境尚未登记';
    if (node.phase !== 'ready') return '正在迁移或维护核对';
    return node.enabled ? '已保存执行归属' : '节点已暂停接单';
  }
  if (nodeReadFailed.value) return '归属待刷新';
  if (!nodeLoaded.value) return '归属读取中';
  const row = accountNodes.value.get(account.id);
  if (!row?.node) return '当前归属未观测';
  if (!row.node.enabled) return '节点已暂停接单';
  if (row.node.phase !== 'ready') return row.node.phase === 'maintenance' ? '节点迁移维护中' : '节点归属待核对';
  if (!row.node_observation) return '在线状态未观测';
  if (row.node_observation.stale) return '在线观察已过期';
  return row.node_observation.state === 'reachable' ? '最近观测可达' : '最近观测不可达';
}

/** 标记任务账号需要核对的观察，同时保留已知归属。@param account 网关账号。@return 是否提醒。 */
function nodeAttention(account: Account): boolean {
  if (account.platform === 'antigravity') return false;
  const row = accountNodes.value.get(account.id);
  return nodeReadFailed.value || !!row?.node && (!row.node.enabled || row.node.phase !== 'ready')
    || !!row?.node_observation && (row.node_observation.stale || row.node_observation.state === 'unreachable');
}

/** 读取整体收尾观察。@param rows 当前账号。@return 完成。 */
async function loadOverallStates(rows: Account[]): Promise<void> {
  const targets = rows.filter(account => account.work_control?.coordinated && (!account.work_control.work_enabled || overallStates.has(account.id)));
  if (!targets.length) return;
  const generation = accountLoadGeneration;
  try {
    await api.openRuntime();
    await Promise.all(targets.map(async account => {
      try { const state = await api.overallWork(account.id); if (generation === accountLoadGeneration) overallStates.set(account.id, state); }
      catch { if (generation === accountLoadGeneration) overallStates.set(account.id, {phase:'reconcile',message:'整体工作状态待核对'}); }
    }));
  } catch { if (generation === accountLoadGeneration) for (const account of targets) overallStates.set(account.id, {phase:'reconcile',message:'整体工作状态待核对'}); }
}

/** 提示需要关注的整体状态。@param account 账号。@return 状态提示，正常启用时为空。 */
function overallWorkNote(account: Account): string {
  const phase = overallStates.get(account.id)?.phase ?? account.work_control?.phase;
  if (phase === 'draining') {
    const remaining = account.work_control?.admitted_requests ?? 0;
    return remaining > 0 ? `正在收尾 · 剩余 ${remaining} 个请求` : '正在收尾';
  }
  if (phase === 'reconcile') return '状态待核对';
  if (phase === 'disabled') return '账号已停用';
  return '';
}

/** 优先采用关联任务账号的整体状态。@param account 账号。@return 是否整体启用。 */
function overallEnabled(account: Account): boolean {
  return overallStates.get(account.id)?.enabled ?? account.work_control?.work_enabled ?? false;
}

/** 控制账号全部工作。@param account 账号。@param enabled 目标。@return 完成。 */
async function changeOverall(account: Account, enabled: boolean): Promise<void> {
  if (!account.work_control || workPending.has(account.id)) return;
  workPending.add(account.id);
  try {
    if (account.work_control.coordinated) {
      await api.openRuntime();
      overallStates.set(account.id, await api.setOverallWork(account.id, enabled));
    } else {
      account.work_control = await api.updateAccountWork(account.id, {work_enabled:enabled,expected_revision:account.work_control.revision});
    }
    await load();
    emit('refresh');
  } catch (cause) {
    overallStates.set(account.id, {phase:'reconcile',message:(cause as Error).message});
    toast((cause as Error).message);
    await load();
  } finally { workPending.delete(account.id); }
}
/** 网关当前生效的画像配置；旧后端未提供时不推测默认值。 */
const profileSelectionMode = ref<'client_version' | 'account' | null>(null);
const defaultVersionProfile = ref<string | null>(null);
/** 分页状态 */
const currentPage = ref(1);
const totalPages = ref(1);
const totalCount = ref(0);
const pageSize = ref(12);
watch(pageSize, () => { currentPage.value=1;void load(); });
const accountQuery = ref('');
const accountFilter = ref('all');
const platformFilter = ref('all');
const platformOptions = [{value:'claude_code',label:'Claude Code'},{value:'antigravity',label:'Antigravity'}];
const isAgyForm = computed(() => form.value.platform === 'antigravity');
const accountCounts = ref<{total: number; active: number; error: number; disabled: number} | null>(null);
let searchTimer: ReturnType<typeof setTimeout> | undefined;
/** 筛选先重置分页，服务端负责全量匹配。@return 无。 */
function applyAccountFilter(): void { clearTimeout(searchTimer); currentPage.value = 1; void load(); }
watch(accountQuery, () => { clearTimeout(searchTimer); searchTimer = setTimeout(applyAccountFilter, 250); });
/** 选择状态后立即查询。@param value 状态。@return 无。 */
function chooseAccountFilter(value: string): void { accountFilter.value = value; applyAccountFilter(); }
/** 先更新平台，再使用当前状态与搜索条件查询。@param value 已选平台。@return 无。 */
function choosePlatformFilter(value: string): void { platformFilter.value = value; applyAccountFilter(); }
/** 移动端（≤760px）分段用短标签，搜索行默认收起。 */
const compactToolbar = useMediaQuery('(max-width: 760px)');
const statusFilterOptions = computed<SegmentedOption[]>(() => [
  { value: 'all', label: compactToolbar.value ? '全部' : '全部账号', count: accountCounts.value?.total ?? '—' },
  { value: 'active', label: '正常', count: accountCounts.value?.active ?? '—' },
  { value: 'error', label: compactToolbar.value ? '关注' : '需要关注', count: accountCounts.value?.error ?? '—' },
  { value: 'disabled', label: '已停用', count: accountCounts.value?.disabled ?? '—' },
]);
const toolbarRef = ref<InstanceType<typeof Toolbar> | null>(null);
const searchOpen = ref(false);
/** 有生效中的搜索词或平台筛选时保持搜索行展开，避免筛选条件被藏起来。 */
const filtersActive = computed(() => accountQuery.value !== '' || platformFilter.value !== 'all');
const searchRowOpen = computed(() => searchOpen.value || filtersActive.value);
/** 应用栏搜索按钮：收起空搜索行，否则展开并聚焦搜索框。@return 无。 */
function toggleSearch(): void {
  if (searchRowOpen.value && !filtersActive.value) { searchOpen.value = false; return; }
  searchOpen.value = true;
  void nextTick(() => (toolbarRef.value?.$el as HTMLElement | undefined)?.querySelector<HTMLInputElement>('input[type=search]')?.focus());
}

/** 只读调度详情，保留已有账号卡片布局。 */
const schedulingAccount = ref<Account | null>(null);
const showScheduling = ref(false);
const accountLoadFailed = ref(false);
let accountLoadGeneration = 0;
let accountLoading = false;

/** 表单弹窗是否可见 */
const showForm = ref(false);
/** 编辑开始时的标量快照，用于增量提交。 */
const editBaseline = ref<Record<string, unknown>>({});
/** 删除确认弹窗是否可见 */
const showDeleteConfirm = ref(false);
const deletingAccount = ref(false);
const deleteError = ref('');
/** 待删除账号 ID */
const deleteTargetId = ref<number | null>(null);

/** 当前编辑的账号（null 表示新建） */
const editing = ref<Account | null>(null);
let editorGeneration = 0;
const savingAccount = ref(false);
const backendSaveIssue = ref<{ otherSaved: boolean; detail: string } | null>(null);
/** 表单数据 */
const form = ref({
  platform: 'claude_code',
  agy_system_prompt_homoglyph_enabled: false,
  client_system_prompt_policy: 'independent',
  agy_gif_frames_enabled: false,
  agy_disable_safety_filtering: false,
  name: '',
  email: '',
  auth_type: 'setup_token',
  setup_token: '',
  access_token: '',
  refresh_token: '',
  expires_at: '',
  proxy_url: '',
  billing_mode: 'strip',
  request_backend: 'legacy' as RequestBackend,
  account_uuid: '',
  organization_uuid: '',
  subscription_type: '',
  rate_limit_tier: '',
  concurrency: 3,
  priority: 50,
  rpm_limit: 0,
  five_hour_usage_limit_percent: 0,
  seven_day_usage_limit_percent: 0,
  auto_telemetry: false,
  auto_poll_usage: false,
  allow_1m_models: DEFAULT_ALLOW_1M_MODELS,
  allow_fast_mode: false,
  upstream_session_pool_enabled: false,
  upstream_session_pool_size: DEFAULT_UPSTREAM_SESSION_POOL_SIZE,
  upstream_session_ttl_minutes: DEFAULT_UPSTREAM_SESSION_TTL_MINUTES,
  upstream_session_refresh_policy: DEFAULT_UPSTREAM_SESSION_REFRESH_POLICY,
});
/** 手动切换新建平台时清空原平台凭据。@param value 新平台。@return 无。 */
function selectAccountPlatform(value:string): void {
  if (editing.value || savingAccount.value || value === form.value.platform || !platformOptions.some(item=>item.value===value)) return;
  editorGeneration++;
  form.value.platform=value;
  form.value.auth_type=value==='antigravity'?'oauth':'setup_token';
  form.value.setup_token=''; form.value.access_token=''; form.value.refresh_token=''; form.value.expires_at='';
  form.value.agy_system_prompt_homoglyph_enabled=false;
  form.value.client_system_prompt_policy='independent';
  form.value.agy_gif_frames_enabled=false;
  form.value.agy_disable_safety_filtering=false;
}
/** 详情始终读取当前列表快照，列表刷新后不保留过期对象。 */
const detailAccountId = ref<number | null>(null);
const showAccountDetails = ref(false);
const workspaceTabs = [{value:'overview',label:'概览'},{value:'configuration',label:'配置'},{value:'scheduling',label:'调度'},{value:'diagnostics',label:'环境与诊断'}] as const;
const workspaceTab = ref<'overview' | 'configuration' | 'scheduling' | 'diagnostics'>('overview');
/** 有排队时调度页签显示排队数（设计稿「调度 4」）；反重力账号同样有调度页签（优先级口径）。 */
const workspaceTabOptions = computed<SegmentedOption[]>(() => {
  const account = detailAccount.value;
  return workspaceTabs.map(item => ({ ...item, count: item.value === 'scheduling' && (account?.queued_requests ?? 0) > 0 ? account?.queued_requests : undefined }));
});
const workspaceOpen = computed({
  get: () => showForm.value || showAccountDetails.value || showScheduling.value,
  set: (open: boolean) => { if (!open) { showForm.value = false; showAccountDetails.value = false; showScheduling.value = false; } },
});
watch(workspaceOpen, (open, previous) => { if (!open && previous && props.workspaceAccountId) emit('close'); });
const diagnosticEnvironment = ref<RuntimeEnvironmentSummary | null>(null);
const diagnosticEnvironmentStates: Record<string,string> = {ready:'就绪',stopped:'已停止',starting:'启动中'};
const diagnosticError = ref('');
const diagnosticLoading = ref(false);
watch(() => workspaceOpen.value && workspaceTab.value === 'diagnostics' ? detailAccountId.value : null, async (id, _previous, onCleanup) => {
  const controller = new AbortController();
  onCleanup(() => controller.abort());
  diagnosticEnvironment.value = null;
  diagnosticError.value = '';
  diagnosticLoading.value = !!id;
  if (!id) return;
  try {
    await api.openRuntime();
    if (controller.signal.aborted) return;
    const rows = await api.runtimeEnvironments(controller.signal);
    if (!controller.signal.aborted) diagnosticEnvironment.value = rows.find(row => row.gateway_account_id === id) ?? null;
  } catch (cause) {
    if (!controller.signal.aborted) diagnosticError.value = (cause as Error).message;
  } finally {
    if (!controller.signal.aborted) diagnosticLoading.value = false;
  }
});
/** 分段控件选中页签，只接受已知页签值。@param value 页签值。@return 无。 */
function selectWorkspaceTab(value: string): void {
  const tab = workspaceTabs.find(item => item.value === value);
  if (tab) changeWorkspaceTab(tab.value);
}
/** 在同一工作区切换，保留当前账号尚未提交的表单。@param tab 页签。@return 无。 */
function changeWorkspaceTab(tab: typeof workspaceTab.value): void {
  const account = detailAccount.value;
  if (!account) return;
  if (tab === 'configuration' && (!showForm.value || editing.value?.id !== account.id)) openEdit(account);
  if (tab === 'scheduling') schedulingAccount.value = account;
  workspaceTab.value = tab;
}

const detailAccount = computed(() => accounts.value.find(account => account.id === detailAccountId.value) ?? null);
const overviewCapabilities = computed(() => detailAccount.value?.usage_data?.capabilities);
const overviewQuota = computed(() => detailAccount.value?.usage_data?.platform_quota);
const overviewAgyTier = computed(() => detailAccount.value && agySubscriptionTier(detailAccount.value));
const overviewAgySource = computed(() => {
  const nativeVersion = detailAccount.value && agyVersion(detailAccount.value);
  return nativeVersion ? `Antigravity ${nativeVersion} 原生观测` : '未观测';
});

/** 从受信能力来源读取原生版本。@param account 当前账号。@return 已观测版本。 */
function agyVersion(account: Account): string | undefined {
  return account.usage_data?.capabilities?.source?.match(/^agy:([\d.]+):native$/)?.[1];
}

/**
 * 读取原生用户档位。额度快照仍可为历史账号提供档位名称。
 * @param account 当前反重力账号。
 * @return 观测到的用户订阅档位。
 */
function agySubscriptionTier(account: Account): string | null {
  const tier = account.usage_data?.capabilities?.provider?.userTier;
  const name = typeof tier === 'object' && tier !== null && 'name' in tier ? tier.name : tier;
  return (typeof name === 'string' && name.trim()) || account.usage_data?.platform_quota?.tier?.trim() || null;
}

/** 使用平台实际可读的套餐标签。@param account 当前账号。@return 精简标签。 */
function cardPlan(account: Account): string | null {
  if (account.platform !== 'antigravity') return subscriptionLabel(account.subscription_type, account.rate_limit_tier);
  const label = agySubscriptionTier(account) || account.usage_data?.platform_quota?.plan?.trim();
  return label?.replace(/^Google AI\s+/i, '') || null;
}

/** 格式化当前调度模式的评分。@param account 账号调度快照。@return 带模式的紧凑评分文字。 */
function activeSchedulingScore(account: Account): string {
  const summary = account.v3_scheduling;
  if (summary) {
    return `智能评分 ${(summary.factors.score * 100).toFixed(1)}`;
  }
  return '评分待更新';
}
/** 打开账号完整信息。@param account 账号。@return 无。 */
function openAccountDetails(account: Account): void {
  detailAccountId.value = account.id;
  showAccountDetails.value = true;
  workspaceTab.value = 'overview';
}
/** 公开代理摘要只显示协议与主机，认证信息仅在配置中编辑。@param value 原始地址。@return 脱敏摘要。 */
function publicProxy(value: string): string { if (!value) return '直连'; try { const url = new URL(value); return `${url.protocol}//${url.host}`; } catch { return '代理地址待核对'; } }
const editingProxyLabel = computed(() => {
  const account = accounts.value.find(item => item.id === editing.value?.id) ?? editing.value;
  return account?.proxy_name || publicProxy(account?.proxy_url ?? form.value.proxy_url);
});
/** 数字草稿保留清空状态，提交边界才转换成后端数字字段。 */
const numberDrafts = ref<Record<'concurrency' | 'priority' | 'rpm_limit' | 'five_hour_usage_limit_percent' | 'seven_day_usage_limit_percent' | 'upstream_session_pool_size' | 'upstream_session_ttl_minutes', number | string>>({ concurrency: 3, priority: 50, rpm_limit: 0, five_hour_usage_limit_percent: 0, seven_day_usage_limit_percent: 0, upstream_session_pool_size: 3, upstream_session_ttl_minutes: 60 });
/** 初始化数字编辑草稿。@return 无。 */
function resetNumberDrafts(): void { for (const key of Object.keys(numberDrafts.value) as (keyof typeof numberDrafts.value)[]) numberDrafts.value[key] = form.value[key]; }
/** 校验后一次写入数字字段，避免清空隐式变成零。@return 无。 */
function applyNumberDrafts(): void {
  const values = { ...numberDrafts.value };
  for (const key of Object.keys(values) as (keyof typeof values)[]) {
    const value = values[key];
    if (String(value).trim() === '' || !Number.isInteger(Number(value))) throw new Error('请完整填写整数配置');
  }
  for (const key of Object.keys(values) as (keyof typeof values)[]) form.value[key] = Number(values[key]);
}
/** 各账号测试状态独立；列表和详情读取同一结果。 */
const testStates = ref(new Map<number, { status: 'loading' | 'success' | 'error'; message: string }>());
const testRequests = new Map<number, AbortController>();
let accountAlive = true;
onUnmounted(() => { accountAlive = false; for (const controller of testRequests.values()) controller.abort(); testRequests.clear(); });
const refreshingUsage = reactive(new Set<number>());
const usageRefreshErrors = reactive(new Map<number, string>());
// 主题设置的预览画板以 ?theme-preview=1 嵌入首页，只读展示，不自动读取反重力上游额度；手动刷新不受影响。
let refreshUsageOnListEntry = route.query['theme-preview'] !== '1';
type UsageWindowKey = 'five_hour' | 'seven_day' | 'seven_day_sonnet' | 'seven_day_fable';
const usageWindows = [{ key: 'five_hour', label: '5 小时' }, { key: 'seven_day', label: '7 天' }, { key: 'seven_day_fable', label: '7 天 Fable' }] as const;

/** 修改原始类型时清除旧分级，防止把上个套餐的真实分级带入新类型。@param value 原始类型。@return 无。 */
function selectSubscription(value: string) {
  if (form.value.subscription_type !== value) form.value.rate_limit_tier = '';
  form.value.subscription_type = value;
}

/** 加载账号列表 */
async function load() {
  if (document.hidden) return;
  const generation = ++accountLoadGeneration;
  accountLoading = true;
  try {
    if (props.workspaceAccountId) {
      const account = await api.accountById(props.workspaceAccountId);
      if (generation === accountLoadGeneration) { accounts.value = [account]; accountLoadFailed.value = false; void loadOverallStates([account]); void loadAccountNodes(); }
      return;
    }
    const [res, overview] = await Promise.all([api.listAccounts(currentPage.value, pageSize.value, accountQuery.value.trim(), accountFilter.value === 'all' ? '' : accountFilter.value, undefined, platformFilter.value), api.getDashboard().catch(() => null)]);
    if (generation !== accountLoadGeneration) return;
    accountLoadFailed.value = false;
    accounts.value = res.data ?? [];
    void loadOverallStates(accounts.value);
    void loadAccountNodes();
    accountCounts.value = res.account_counts ?? overview?.accounts ?? null;
    profileSelectionMode.value = res.claude_code_profile_selection_mode ?? null;
    defaultVersionProfile.value = res.claude_code_version_profile ?? null;
    totalPages.value = res.total_pages;
    totalCount.value = res.total;
    if (refreshUsageOnListEntry) {
      refreshUsageOnListEntry = false;
      void refreshEntryUsage(accounts.value);
    }
  } catch {
    // 读取失败不把原有负载伪装成空列表；旧快照保留并明确标记。
    if (generation === accountLoadGeneration) accountLoadFailed.value = true;
  } finally {
    if (generation === accountLoadGeneration) accountLoading = false;
  }
}

/** 页面恢复可见时立即更新，隐藏时不继续拉取。@return 无。 */
function refreshVisibleAccounts() {
  if (document.hidden) { nodeGeneration++; nodeController?.abort(); }
  if (!document.hidden) void load();
}

/** 打开只读会话和发送视图。@param account 当前账号。@return 无。 */
function openScheduling(account: Account) {
  detailAccountId.value = account.id;
  workspaceTab.value = 'scheduling';
  schedulingAccount.value = account;
  showScheduling.value = true;
}

/** 进入账号支持的容量视图。@param account 当前账号。@return 无。 */
function openAccountCapacity(account: Account): void {
  openScheduling(account);
}

/** 读取卡片口径的速率。@param account 当前账号。@return 未计量时为空。 */
function cardRpm(account: Account): number | undefined {
  if (account.platform === 'antigravity') return account.rpm_limit > 0 ? account.rpm_current : undefined;
  return account.v3_scheduling?.submissions_last_60s ?? account.rpm_current ?? 0;
}

/** 翻页 */
function goToPage(page: number) {
  if (page < 1 || page > totalPages.value || page === currentPage.value) return;
  currentPage.value = page;
  load();
}

/** 自动重载定时器 */
let autoReloadTimer: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  void openLinkedAccount();
  if (!props.workspaceAccountId) void load();
  document.addEventListener('visibilitychange', refreshVisibleAccounts);
  // 每 5 秒静默重拉账户列表，保证秒级 soft backoff 状态能被看到。
  autoReloadTimer = setInterval(() => {
    if (!document.hidden && !accountLoading) void load();
  }, 5 * 1000);
});

onUnmounted(() => {
  nodeGeneration++;
  nodeController?.abort();
  linkedGeneration++;
  accountLoadGeneration++;
  clearTimeout(searchTimer);
  document.removeEventListener('visibilitychange', refreshVisibleAccounts);
  if (autoReloadTimer) {
    clearInterval(autoReloadTimer);
    autoReloadTimer = null;
  }
});

/** 打开新建账号弹窗 */
function openCreate() {
  editorGeneration++;
  backendSaveIssue.value = null;
  proxyChoice.value = undefined;
  editing.value = null;
  form.value = {
    platform: 'claude_code',
    agy_system_prompt_homoglyph_enabled: false,
    client_system_prompt_policy: 'independent',
    agy_gif_frames_enabled: false,
    agy_disable_safety_filtering: false,
    name: '',
    email: '',
    auth_type: 'setup_token',
    setup_token: '',
    access_token: '',
    refresh_token: '',
    expires_at: '',
    proxy_url: '',
    billing_mode: 'strip',
    request_backend: 'legacy' as RequestBackend,
    account_uuid: '',
    organization_uuid: '',
    subscription_type: '',
    rate_limit_tier: '',
    concurrency: 3,
    priority: 50,
    rpm_limit: 0,
    five_hour_usage_limit_percent: 0,
    seven_day_usage_limit_percent: 0,
    auto_telemetry: false,
    auto_poll_usage: false,
    allow_1m_models: DEFAULT_ALLOW_1M_MODELS,
    allow_fast_mode: false,
    upstream_session_pool_enabled: false,
    upstream_session_pool_size: DEFAULT_UPSTREAM_SESSION_POOL_SIZE,
    upstream_session_ttl_minutes: DEFAULT_UPSTREAM_SESSION_TTL_MINUTES,
    upstream_session_refresh_policy: DEFAULT_UPSTREAM_SESSION_REFRESH_POLICY,
  };
  detailAccountId.value = null;
  workspaceTab.value = 'configuration';
  resetNumberDrafts();
  showForm.value = true;
}

/**
 * 打开编辑账号弹窗
 * @param a 要编辑的账号对象
 */
function openEdit(a: Account) {
  editorGeneration++;
  backendSaveIssue.value = null;
  proxyChoice.value = undefined;
  editing.value = a;
  form.value = {
    platform: a.platform ?? 'claude_code',
    agy_system_prompt_homoglyph_enabled: a.agy_system_prompt_homoglyph_enabled ?? false,
    client_system_prompt_policy: a.client_system_prompt_policy
      ?? (a.platform === 'antigravity' ? (a.agy_system_prompt_as_user_reminder ? 'user_reminder' : 'independent') : 'append'),
    agy_gif_frames_enabled: a.agy_gif_frames_enabled ?? false,
    agy_disable_safety_filtering: a.agy_disable_safety_filtering ?? false,
    name: a.name,
    email: a.email,
    auth_type: a.auth_type || 'setup_token',
    setup_token: '',
    access_token: '',
    refresh_token: '',
    expires_at: a.expires_at ? String(a.expires_at) : '',
    proxy_url: a.proxy_url,
    billing_mode: a.billing_mode || 'strip',
    request_backend: a.request_backend_pending ?? a.request_backend ?? 'legacy',
    account_uuid: a.account_uuid || '',
    organization_uuid: a.organization_uuid || '',
    subscription_type: a.subscription_type || '',
    rate_limit_tier: a.rate_limit_tier || '',
    concurrency: a.concurrency,
    priority: a.priority,
    rpm_limit: a.rpm_limit ?? 0,
    five_hour_usage_limit_percent: a.five_hour_usage_limit_percent ?? 0,
    seven_day_usage_limit_percent: a.seven_day_usage_limit_percent ?? 0,
    auto_telemetry: a.auto_telemetry ?? false,
    auto_poll_usage: a.auto_poll_usage ?? false,
    allow_1m_models: a.allow_1m_models ?? DEFAULT_ALLOW_1M_MODELS,
    allow_fast_mode: a.allow_fast_mode ?? false,
    upstream_session_pool_enabled: a.upstream_session_pool_enabled ?? false,
    upstream_session_pool_size: a.upstream_session_pool_size ?? DEFAULT_UPSTREAM_SESSION_POOL_SIZE,
    upstream_session_ttl_minutes: a.upstream_session_ttl_minutes ?? DEFAULT_UPSTREAM_SESSION_TTL_MINUTES,
    upstream_session_refresh_policy: a.upstream_session_refresh_policy ?? DEFAULT_UPSTREAM_SESSION_REFRESH_POLICY,
  };
  editBaseline.value = { ...form.value };
  detailAccountId.value = a.id;
  workspaceTab.value = 'configuration';
  resetNumberDrafts();
  showForm.value = true;
}

const backendOptions = computed(() => {
  const options = [
    { value: 'native293', label: '原生运行时 V1', description: 'Claude Code 2.1.293', disabled: false },
    { value: 'legacy', label: '原有转发', description: '现有转发通道', disabled: false },
  ];
  const account = editing.value;
  if (account && (account.request_backend_revision !== undefined || account.tui_v2_available
    || account.request_backend === 'tui_v2' || account.request_backend_pending === 'tui_v2')) {
    const description = account.tui_v2_available ? 'Claude Code 2.1.293' : '保存时核对账号环境';
    options.unshift({ value: 'tui_v2', label: '交互运行时 V2', description, disabled: false });
  }
  return options;
});

/** 显示账号实际使用的转发方式。@param backend 持久值。@return 中文标签。 */
function backendName(backend?: RequestBackend): string {
  if (backend === 'tui_v2') return '交互运行时 V2';
  if (backend === 'native293') return '原生运行时 V1';
  return '原有转发';
}

/** 重新读取账号的生效值、等待目标和修订。@param keepDraft 保留待重试的选择。@return 是否已同步。 */
async function reloadBackend(keepDraft = backendSaveIssue.value !== null): Promise<boolean> {
  const current = editing.value;
  if (!current) return false;
  const generation = editorGeneration;
  try {
    const fresh = await api.accountById(current.id);
    if (generation !== editorGeneration) return false;
    editing.value = fresh;
    const selected = fresh.request_backend_pending ?? fresh.request_backend ?? 'legacy';
    if (!keepDraft) form.value.request_backend = selected;
    editBaseline.value.request_backend = selected;
    return true;
  } catch (error) {
    if (generation === editorGeneration) toast((error as Error).message || '刷新转发状态失败');
    return false;
  }
}

const credentialDrafts = ['setup_token', 'access_token', 'refresh_token'] as const;

/** 普通 PUT 确认成功后推进已提交字段的基线，并清理已确认的凭据草稿。
 * @param saved 后端保存结果。@param sent 本次提交字段。@param submitted 发出时的表单快照。
 * @param selectedProxy 发出时选择的代理。@return 无。
 */
function acceptSavedSettings(
  saved: Account,
  sent: Record<string, unknown>,
  submitted: typeof form.value,
  selectedProxy: ProxyRoute | null | undefined,
): void {
  for (const key of Object.keys(sent) as (keyof typeof submitted)[]) {
    if (Object.hasOwn(submitted, key) && !credentialDrafts.some(field => field === key)) {
      editBaseline.value[key] = submitted[key];
    }
  }
  for (const key of credentialDrafts) {
    if (!Object.hasOwn(sent, key)) continue;
    editBaseline.value[key] = '';
    if (form.value[key] === submitted[key]) form.value[key] = '';
  }

  const current = { ...editing.value, ...saved };
  if (Object.hasOwn(sent, 'proxy_id')) {
    editBaseline.value.proxy_url = saved.proxy_url;
    if (form.value.proxy_url === submitted.proxy_url) form.value.proxy_url = saved.proxy_url;
    if (proxyChoice.value === selectedProxy) proxyChoice.value = undefined;
    current.proxy_id = selectedProxy?.id;
    current.proxy_name = selectedProxy?.name;
  }
  editing.value = current;
  const index = accounts.value.findIndex(account => account.id === saved.id);
  if (index >= 0) accounts.value[index] = { ...accounts.value[index], ...current };
}

/**
 * 规整并校验额度输入，拒绝空值和越界数值，避免误将限制关闭。
 * @param value 输入框当前值。
 * @param label 用于错误提示的窗口名称。
 * @return 0～100 的整数百分比。
 */
function usageLimitInput(value: unknown, label: string): number {
  const number = typeof value === 'number' ? value
    : typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN;
  if (!Number.isInteger(number) || number < 0 || number > 100) {
    throw new Error(`${label}用量上限必须为 0～100 的整数，0 表示不限制`);
  }
  return number;
}

const agyFormKeys = ['platform','agy_system_prompt_homoglyph_enabled','client_system_prompt_policy','agy_gif_frames_enabled','agy_disable_safety_filtering','name','email','auth_type','access_token','refresh_token','expires_at','proxy_url','proxy_id','proxy_revision','concurrency','priority','rpm_limit'];

/** 保存账号（新建或更新）。@return 保存完成后的空结果。 */
async function save() {
  if (savingAccount.value) return;
  const generation = editorGeneration;
  savingAccount.value = true;
  try {
    applyNumberDrafts();
    const expiresAt = form.value.expires_at.trim();
    form.value.five_hour_usage_limit_percent = usageLimitInput(form.value.five_hour_usage_limit_percent, '5 小时');
    form.value.seven_day_usage_limit_percent = usageLimitInput(form.value.seven_day_usage_limit_percent, '7 天');
    if (form.value.upstream_session_pool_size < 0 || form.value.upstream_session_pool_size > 20) {
      throw new Error('上游 session 池容量必须为 0 或 1-20');
    }
    if (form.value.upstream_session_pool_size !== 0 && form.value.upstream_session_pool_size < 1) {
      throw new Error('上游 session 池容量必须为 0 或 1-20');
    }
    if (form.value.upstream_session_ttl_minutes < 5 || form.value.upstream_session_ttl_minutes > 1440) {
      throw new Error('上游 session TTL 必须为 5-1440 分钟');
    }
    const account = editing.value;
    if (account) {
      if (form.value.auth_type === 'setup_token'
        && !form.value.setup_token.trim()
        && account.auth_type !== 'setup_token') {
        throw new Error('切换到 Setup Token 模式时必须填写 Setup Token');
      }
      if (form.value.auth_type === 'oauth'
        && !form.value.refresh_token.trim()
        && account.auth_type !== 'oauth') {
        throw new Error('切换到 OAuth 模式时必须填写 Refresh Token');
      }
      const submitted = { ...form.value };
      const selectedProxy = proxyChoice.value;
      const updates = accountUpdateDelta(submitted, editBaseline.value);
      applyProxyChoice(updates);
      if (isAgyForm.value) for (const key of Object.keys(updates)) if (!agyFormKeys.includes(key)) delete updates[key];
      const backend = updates.request_backend as RequestBackend | undefined;
      const revision = account.request_backend_revision;
      const candidateChange = backend === 'tui_v2' || account.request_backend === 'tui_v2'
        || account.request_backend_pending != null || (revision ?? 0) > 0;
      if (backend && revision !== undefined && candidateChange) {
        delete updates.request_backend;
        let otherSaved = backendSaveIssue.value?.otherSaved ?? false;
        if (Object.keys(updates).length) {
          const saved = await api.updateAccount(account.id, updates);
          if (generation !== editorGeneration) return;
          acceptSavedSettings(saved, updates, submitted, selectedProxy);
          otherSaved = true;
        }
        try {
          await api.updateAccount(account.id, { request_backend: backend, request_backend_revision: revision });
        } catch (error) {
          if (generation !== editorGeneration) return;
          const reason = (error as Error).message;
          backendSaveIssue.value = { otherSaved, detail: ['转发方式保存未确认。', reason].filter(Boolean).join(' ') };
          const refreshed = await reloadBackend(true);
          if (refreshed && generation === editorGeneration && editBaseline.value.request_backend === backend) {
            backendSaveIssue.value = { otherSaved, detail: '已核对转发方式，当前状态符合所选目标。' };
          }
          return;
        }
      } else if (Object.keys(updates).length) {
        await api.updateAccount(account.id, updates);
      }
    } else {
      if (form.value.auth_type === 'setup_token' && !form.value.setup_token.trim()) {
        throw new Error('Setup Token 不能为空');
      }
      if (form.value.auth_type === 'oauth' && !form.value.refresh_token.trim()) {
        throw new Error('Refresh Token 不能为空');
      }
      const payload: Record<string, unknown> = {
        platform: form.value.platform,
        agy_system_prompt_homoglyph_enabled: form.value.agy_system_prompt_homoglyph_enabled,
        agy_gif_frames_enabled: form.value.agy_gif_frames_enabled,
        agy_disable_safety_filtering: form.value.agy_disable_safety_filtering,
        name: form.value.name,
        email: form.value.email,
        auth_type: form.value.auth_type,
        setup_token: form.value.setup_token,
        access_token: form.value.access_token,
        refresh_token: form.value.refresh_token,
        proxy_url: form.value.proxy_url,
        billing_mode: form.value.billing_mode,
        request_backend: form.value.request_backend,
        account_uuid: form.value.account_uuid || null,
        organization_uuid: form.value.organization_uuid || null,
        subscription_type: form.value.subscription_type || null,
        rate_limit_tier: form.value.rate_limit_tier || null,
        concurrency: form.value.concurrency,
        priority: form.value.priority,
        rpm_limit: form.value.rpm_limit,
        five_hour_usage_limit_percent: form.value.five_hour_usage_limit_percent,
        seven_day_usage_limit_percent: form.value.seven_day_usage_limit_percent,
        auto_telemetry: form.value.auto_telemetry,
        auto_poll_usage: form.value.auto_poll_usage,
        allow_1m_models: form.value.allow_1m_models,
        allow_fast_mode: form.value.allow_fast_mode,
        upstream_session_pool_enabled: form.value.upstream_session_pool_enabled,
        upstream_session_pool_size: form.value.upstream_session_pool_size,
        upstream_session_ttl_minutes: form.value.upstream_session_ttl_minutes,
        upstream_session_refresh_policy: form.value.upstream_session_refresh_policy,
      };
      if (isAgyForm.value) payload.client_system_prompt_policy = form.value.client_system_prompt_policy;
      if (expiresAt) payload.expires_at = Number(expiresAt);
      applyProxyChoice(payload);
      if (isAgyForm.value) for (const key of Object.keys(payload)) if (!agyFormKeys.includes(key)) delete payload[key];
      await api.createAccount(payload);
    }
    if (generation !== editorGeneration) return;
    if (props.workspaceAccountId) {
      emit('refresh');
      workspaceOpen.value = false;
    } else {
      workspaceOpen.value = false;
      await load();
      emit('refresh');
    }
  } catch (e: unknown) {
    if (generation === editorGeneration) toast((e as Error).message || '保存失败');
  } finally { savingAccount.value = false; }
}

/**
 * 确认删除账号
 * @param id 账号 ID
 */
function confirmDelete(id: number) {
  deleteTargetId.value = id;
  deleteError.value = '';
  showDeleteConfirm.value = true;
}

/** 执行删除账号 */
async function executeDelete() {
  if (deleteTargetId.value === null || deletingAccount.value) return;
  deletingAccount.value = true; deleteError.value = '';
  try {
    await api.deleteAccount(deleteTargetId.value);
    showDeleteConfirm.value = false;
    deleteTargetId.value = null;
    await load();
    emit('refresh');
  } catch (e: unknown) {
    deleteError.value = (e as Error).message || '删除失败';
  } finally { deletingAccount.value = false; }
}

/**
 * 测试账号连接
 * @param id 账号 ID
 */
async function test(id: number) {
  if (testRequests.has(id)) return;
  const controller = new AbortController();
  testRequests.set(id, controller);
  testStates.value.set(id, { status: 'loading', message: '' });
  try {
    const result = await api.testAccount(id, controller.signal);
    if (!accountAlive || testRequests.get(id) !== controller) return;
    testStates.value.set(id, { status: result.status === 'ok' ? 'success' : 'error', message: result.message || (result.status === 'ok' ? '账号连接正常。' : '测试失败，请重试。') });
  } catch (cause) {
    if (!accountAlive || controller.signal.aborted || testRequests.get(id) !== controller) return;
    testStates.value.set(id, { status: 'error', message: (cause as Error).message || '测试请求失败' });
  } finally {
    if (testRequests.get(id) === controller) testRequests.delete(id);
  }
}

/**
 * 刷新账号用量数据
 * @param id 账号 ID
 * @param automatic 是否属于进入列表时的一次性批次
 * @return 用量读取是否成功
 */
async function refreshUsage(id: number, automatic = false): Promise<boolean> {
  if (refreshingUsage.has(id)) return false;
  refreshingUsage.add(id);
  usageRefreshErrors.delete(id);
  try {
    const res = await api.refreshUsage(id);
    if (!accountAlive) return false;
    if (res.status === 'ok' && res.usage) {
      // 自动批次收尾时统一回读，手动刷新立即同步新的用量窗口。
      if (!automatic) await load();
      return true;
    } else {
      throw new Error(res.message || '刷新用量失败');
    }
  } catch (e: unknown) {
    if (accountAlive) {
      const message = (e as Error).message || '刷新用量失败';
      if (automatic) usageRefreshErrors.set(id, message);
      else toast(message);
    }
  } finally {
    refreshingUsage.delete(id);
  }
  return false;
}

/** 首次进入列表后逐个读取当前页的反重力额度。@param rows 首次加载的账号。@return 批次结束。 */
async function refreshEntryUsage(rows: Account[]): Promise<void> {
  const eligible = rows.filter(account => account.platform === 'antigravity' && account.status === 'active'
    && account.work_control?.work_enabled !== false && (account.credential_state?.phase ?? 'ready') === 'ready');
  let updated = false;
  for (const account of eligible) {
    if (!accountAlive) return;
    if (await refreshUsage(account.id, true)) updated = true;
  }
  if (updated && accountAlive) await load();
}

/**
 * 只切换 API 接单，保留账号资格与其它工作。
 * @param a 账号对象
 * @return 完成。
 */
async function toggleScheduling(a: Account) {
  if (!a.work_control || workPending.has(a.id)) return;
  workPending.add(a.id);
  try {
    a.work_control = await api.updateAccountWork(a.id, {api_accepting:!a.work_control.api_accepting,expected_revision:a.work_control.revision});
    emit('refresh');
  } catch (e: unknown) {
    toast((e as Error).message || '切换 API 接单失败');
  } finally { workPending.delete(a.id); }
}

/** 显式恢复旧账号资格，独立接单偏好保持原值。@param account 账号。@return 完成。 */
async function restoreAvailability(account: Account): Promise<void> {
  if (workPending.has(account.id)) return;
  workPending.add(account.id);
  try { await api.updateAccount(account.id, {status:'active'}); await load(); emit('refresh'); }
  catch (cause) { toast((cause as Error).message); }
  finally { workPending.delete(account.id); }
}

/**
 * 格式化剩余时间
 * @param resetsAt ISO 时间字符串
 */
function formatTimeLeft(resetsAt?: string | null): string {
  if (!resetsAt) return '—';
  const resetMs = new Date(resetsAt).getTime();
  if (Number.isNaN(resetMs)) return '未知';
  const diff = resetMs - Date.now();
  if (diff <= 0) return '已重置';
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  if (days > 0) return `${days}天 ${hours}小时 ${minutes}分`;
  if (hours > 0) return `${hours}小时 ${minutes}分`;
  if (minutes > 0) return `${minutes}分`;
  // 不足 1 分钟时显示秒,避免短冷却显示成 “0m” 让人误以为卡住
  return `${seconds}秒`;
}

/**
 * 从新版 limits scoped 结构中提取指定模型的周用量窗口。
 */
function scopedUsageWindow(data: Account['usage_data'], modelName: string) {
  const expected = modelName.toLowerCase();
  const limit = data?.limits?.find(item => {
    const model = item.scope?.model;
    const displayName = model?.display_name?.toLowerCase();
    const modelId = model?.id?.toLowerCase();
    const matchesModel = displayName === expected || !!modelId?.includes(expected);
    return matchesModel && (item.kind === 'weekly_scoped' || item.group === 'weekly');
  });
  if (typeof limit?.percent !== 'number') return undefined;
  return {
    utilization: limit.percent,
    resets_at: limit.resets_at ?? null,
  };
}

/**
 * 获取页面展示用 usage 窗口；Fable 兼容后端尚未写入稳定字段的旧缓存。
 */
function usageWindow(data: Account['usage_data'], key: UsageWindowKey) {
  const direct = data?.[key];
  if (direct) return direct;
  if (key === 'seven_day_fable') return scopedUsageWindow(data, 'Fable');
  return undefined;
}

/**
 * 获取进度条宽度；未知或过期状态由文字单独说明，不能显示成真实 0%。
 * @param window 官方额度观察。
 * @return 限制在合法数值范围内的进度条百分比。
 */
function effectiveUtil(window?: { utilization: number; resets_at?: string | null }): number {
  if (!window || !Number.isFinite(window.utilization) || window.utilization < 0) return 0;
  const resetMs = window.resets_at ? new Date(window.resets_at).getTime() : NaN;
  if (!Number.isNaN(resetMs) && resetMs <= Date.now()) return 0;
  return window.utilization;
}

/**
 * 区分真实零占用、缺少额度观察和等待新周期观察。
 * @param window 官方额度窗口。
 * @return 百分比或明确的未知／待更新状态。
 */
function usagePercentLabel(window?: UsageWindow): string {
  if (!window || !Number.isFinite(window.utilization) || window.utilization < 0) return '未知';
  if (window.resets_at) {
    const reset = Date.parse(window.resets_at);
    if (!Number.isFinite(reset)) return '未知';
    if (reset <= Date.now()) return '待更新';
  } else if (window.utilization > 0) {
    return '未知';
  }
  return `${Math.round(window.utilization)}%`;
}

/**
 * 只为仍有效的官方窗口展示倒计时，避免过期观察同时显示“已重置”。
 * @param window 官方额度窗口。
 * @return 重置时间是否合法且尚未到期。
 */
function hasFutureReset(window?: UsageWindow): boolean {
  if (!window?.resets_at) return false;
  const reset = Date.parse(window.resets_at);
  return Number.isFinite(reset) && reset > Date.now();
}

/**
 * 判断账号是否正在被限流
 */
function isRateLimited(a: Account): boolean {
  return !!(a.rate_limit_reset_at && new Date(a.rate_limit_reset_at) > new Date());
}

/**
 * 获取状态文案。
 * @param a 账号对象
 * @return 状态标签
 */
function statusStyle(a: Account): { label: string } {
  if (a.status === 'active' && isRateLimited(a)) {
    // 短冷却(瞬时速率限制,秒级)与真正撞墙(5h/7d 限额)区分显示,避免误以为账号被长时间限流
    if ((a.disable_reason || '').includes('短冷却')) return { label: '短冷却' };
    return { label: '限流中' };
  }
  if (a.status === 'active') return { label: '活跃' };
  if (a.status === 'error') return { label: '异常' };
  return { label: '停用' };
}

/**
 * 健康条语义色调：停用为中性；异常与认证错误为危险；限流、短冷却与调度观测错误为警示；其余为成功。
 * @param a 账号对象
 * @return NoticeStrip 色调
 */
function accountHealthTone(a: Account): 'success' | 'warning' | 'danger' | 'neutral' {
  if (a.status === 'disabled') return 'neutral';
  if (a.status === 'error' || a.auth_error) return 'danger';
  if (isRateLimited(a) || a.v3_scheduling_error) return 'warning';
  return 'success';
}

/**
 * 概览页状态徽标与健康条同色。
 * @param a 账号对象
 * @return 徽标变体
 */
function healthBadgeVariant(a: Account): BadgeVariants['variant'] {
  const tone = accountHealthTone(a);
  return tone === 'neutral' ? 'secondary' : tone === 'danger' ? 'destructive' : tone;
}

/**
 * 遮蔽 Token 显示
 * @param t Token 原始值
 */
function maskToken(t: string): string {
  if (t.length <= 20) return t;
  return t.slice(0, 20) + '...';
}

/**
 * 获取认证方式标签
 * @param authType 认证方式
 */
function authTypeLabel(authType: string): string {
  return authType === 'oauth' ? 'OAuth' : 'Setup Token';
}

/**
 * 格式化当前分钟 RPM 状态。
 * @param account 账号对象
 */
function rpmLabel(account: Account): string {
  if (account.v3_scheduling) return `${account.v3_scheduling.submissions_last_60s}/${account.rpm_limit > 0 ? account.rpm_limit : '不限'}`;
  if (!account.rpm_limit || account.rpm_limit <= 0) return '未限制';
  const current = account.rpm_current ?? 0;
  return account.rpm_saturated ? `已满 ${current}/${account.rpm_limit}` : `${current}/${account.rpm_limit}`;
}

/**
 * 获取 RPM 文本色调类（is-warning / is-danger / is-muted，见 accounts.css）。
 * @param account 账号对象
 */
function rpmClass(account: Account): string {
  if (account.v3_scheduling) return account.v3_scheduling.capacity.reason === 'pacing' ? 'is-warning' : '';
  if (!account.rpm_limit || account.rpm_limit <= 0) return 'is-muted';
  if (account.rpm_saturated) return 'is-danger';
  const current = account.rpm_current ?? 0;
  const ratio = current / account.rpm_limit;
  if (ratio >= 0.8) return 'is-warning';
  return '';
}

/**
 * 格式化上游 session 池状态。
 * @param account 账号对象
 */
function upstreamSessionPoolLabel(account: Account): string {
  if (!account.upstream_session_pool_enabled || account.upstream_session_pool_size <= 0) return '关闭';
  const active = account.upstream_session_pool_active_count ?? 0;
  const capacity = account.upstream_session_pool_capacity ?? account.upstream_session_pool_size;
  return `${active}/${capacity}`;
}

/**
 * 获取上游 session 池文本色调类。
 * @param account 账号对象
 */
function upstreamSessionPoolClass(account: Account): string {
  if (!account.upstream_session_pool_enabled || account.upstream_session_pool_size <= 0) return 'is-muted';
  const active = account.upstream_session_pool_active_count ?? 0;
  return active >= account.upstream_session_pool_size ? 'is-warning' : 'is-success';
}

/**
 * 获取上游 session 池刷新策略显示名。
 * @param policy 刷新策略值
 */
function upstreamSessionPolicyLabel(policy?: string): string {
  return policy === 'owner_only' ? '仅属主刷新' : '映射请求刷新';
}

/**
 * 格式化瞬时 429 软退避剩余时间。
 * @param account 账号对象
 */
function transientBackoffLabel(account: Account): string {
  const waiting = account.transient_backoff_waiting ?? 0;
  const remainingMs = account.transient_backoff_remaining_ms ?? 0;
  if (waiting <= 0 && remainingMs <= 0) return '0';
  const seconds = Math.max(1, Math.ceil(remainingMs / 1000));
  return `${waiting} · ${seconds}s`;
}

/**
 * 获取瞬时 429 软退避文本色调类。
 * @param account 账号对象
 */
function transientBackoffClass(account: Account): string {
  return ((account.transient_backoff_waiting ?? 0) > 0 || (account.transient_backoff_remaining_ms ?? 0) > 0)
    ? 'is-warning'
    : '';
}

/**
 * 格式化标准并发槽位。
 * @param value 标准槽位数
 */
function formatConcurrencySlots(value?: number | null): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return '0';
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/**
 * 格式化内部单位数。
 * @param value 内部单位数
 */
function formatConcurrencyUnits(value?: number | null): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return '0';
  return String(Math.round(n));
}

/**
 * 获取账号卡片并发显示文本。
 * @param account 账号对象
 */
function concurrencyLabel(account: Account): string {
  return `${formatConcurrencySlots(account.current_concurrency)}/${formatConcurrencySlots(account.concurrency)}`;
}

/**
 * 获取账号卡片并发文本色调类（满载为 is-danger）。
 * @param account 账号对象
 */
function concurrencyClass(account: Account): string {
  return (account.current_concurrency ?? 0) >= account.concurrency
    ? 'is-danger'
    : '';
}

/**
 * 获取当前账号显示的凭证摘要
 * @param account 账号对象
 */
function authSecretPreview(account: Account): string {
  if (account.auth_type === 'oauth') {
    return maskToken(account.refresh_token || account.access_token || '未配置');
  }
  return maskToken(account.setup_token || '未配置');
}

/**
 * 格式化 OAuth 过期时间
 * @param expiresAt 毫秒时间戳
 */
function formatExpiresAt(expiresAt?: number | null): string {
  if (!expiresAt) return '未提供';
  return new Date(expiresAt).toLocaleString('zh-CN');
}

/**
 * 格式化字节数为可读字符串。
 * @param bytes 字节数。
 * @param precision 小数位，实测指标保留精度以避免将 1.5G 显示为 2G。
 * @returns 可读的容量。
 */
function formatBytes(bytes?: number, precision = 0): string {
  if (!bytes) return '—';
  if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(precision) + 'G';
  if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(precision) + 'M';
  if (bytes >= 1024) return (bytes / 1024).toFixed(precision) + 'K';
  return bytes + 'B';
}

// --- OAuth 授权流程 ---
const showOAuthFlow = ref(false);
const oauthPlatform = ref('claude_code');
const oauthTarget = ref<Account | null>(null);
const oauthMode = ref<'oauth' | 'setup_token'>('oauth');
const oauthProxy = ref<ProxyRoute | null | undefined>();
const oauthSessionProxy = ref<ProxyRoute | null>(null);
const oauthSessionId = ref('');
const oauthAuthUrl = ref('');
const oauthCode = ref('');
const oauthLoading = ref(false);
const oauthResult = ref<OAuthExchangeResult | null>(null);
const oauthStep = ref<'generate' | 'exchange' | 'done'>('generate');
const oauthError = ref('');
let oauthGeneration = 0;
let oauthController: AbortController | undefined;
/** 使原回执失效；原生链接生成保留连接，收到会话后立即结束原进程。@return 无。 */
function invalidateOAuthRequest(): void {
  oauthGeneration++;
  // 生成阶段尚无会话ID，保留有界请求才能在迟到回执后精确取消原生进程。
  if (!(oauthPlatform.value === 'antigravity' && oauthStep.value === 'generate' && oauthLoading.value)) oauthController?.abort();
  oauthController = undefined;
}
watch(showOAuthFlow, value => {
  if (!value) { invalidateOAuthRequest(); oauthLoading.value = false; cancelOAuthSession(); }
}, { flush:'sync' });
onUnmounted(() => { invalidateOAuthRequest(); cancelOAuthSession(); });

/** 结束已知的原生授权会话。@return 无。 */
function cancelOAuthSession(): void {
  const id = oauthSessionId.value;
  const platform = oauthPlatform.value;
  oauthSessionId.value = '';
  if (id && platform === 'antigravity') void api.cancelOAuth(id, platform).catch(() => toast('原授权操作待核对，请读取账号状态'));
}

/** 返回授权选择并结束原会话。@return 无。 */
function restartOAuthFlow(): void {
  cancelOAuthSession(); invalidateOAuthRequest();
  oauthStep.value = 'generate'; oauthError.value = ''; oauthCode.value = '';
}

/** 打开授权窗口并冻结原账号。@param target 重新授权的目标。@return 无。 */
function openOAuthFlow(target?: Account) {
  invalidateOAuthRequest(); oauthError.value = "";
  cancelOAuthSession();
  oauthTarget.value = target?.platform === 'antigravity'
    ? accounts.value.find(account => account.id === target.id) ?? target
    : null;
  oauthPlatform.value = oauthTarget.value ? 'antigravity' : 'claude_code';
  oauthMode.value = 'oauth';
  oauthProxy.value = oauthTarget.value ? undefined : null; oauthSessionProxy.value = null;
  oauthSessionId.value = '';
  oauthAuthUrl.value = '';
  oauthCode.value = '';
  oauthResult.value = null;
  oauthStep.value = 'generate';
  oauthLoading.value = false;
  showOAuthFlow.value = true;
}

/** 生成当前授权步骤的链接，关闭后丢弃迟到回执。@return 完成。 */
async function generateOAuthUrl(): Promise<void> {
  if (oauthLoading.value) return;
  oauthController?.abort(); oauthController = new AbortController();
  const current = ++oauthGeneration; const signal = oauthController.signal;
  oauthLoading.value = true; oauthError.value = '';
  try {
    const selection = oauthProxy.value;
    const proxy = selection ? {proxy_id:selection.id, proxy_revision:selection.revision}
      : oauthTarget.value && selection === null ? {proxy_url:''} : {};
    const replaceProxy = !!oauthTarget.value && selection !== undefined;
    const platform = oauthPlatform.value;
    const result = oauthMode.value === 'oauth' ? await api.generateAuthUrl({...proxy, platform, account_id:oauthTarget.value?.id,
      ...(replaceProxy ? {replace_proxy:true} : {})}, signal) : await api.generateSetupTokenUrl(proxy, signal);
    if (current !== oauthGeneration || !showOAuthFlow.value) { if (platform === 'antigravity') void api.cancelOAuth(result.session_id, platform).catch(() => {}); return; }
    oauthSessionProxy.value = selection ?? null;
    oauthSessionId.value = result.session_id; oauthAuthUrl.value = result.auth_url; oauthCode.value = ''; oauthStep.value = 'exchange';
  } catch (cause) { if (current === oauthGeneration && !signal.aborted) oauthError.value = (cause as Error).message || '生成授权链接失败'; }
  finally { if (current === oauthGeneration) oauthLoading.value = false; }
}

/** 交换原授权会话的code，失败保留输入供修正。@return 完成。 */
async function exchangeOAuthCode(): Promise<void> {
  if (oauthLoading.value || !oauthCode.value.trim()) return;
  oauthController?.abort(); oauthController = new AbortController();
  const current = ++oauthGeneration; const signal = oauthController.signal;
  oauthLoading.value = true; oauthError.value = '';
  try {
    const result = oauthMode.value === 'oauth' ? await api.exchangeCode(oauthSessionId.value, oauthCode.value.trim(), signal) : await api.exchangeSetupTokenCode(oauthSessionId.value, oauthCode.value.trim(), signal);
    if (current !== oauthGeneration || !showOAuthFlow.value) return;
    oauthResult.value = result; oauthCode.value = ''; oauthStep.value = 'done';
    if (oauthTarget.value) await load();
  } catch (cause) { if (current === oauthGeneration && !signal.aborted) oauthError.value = (cause as Error).message || '授权失败，请检查授权码'; }
  finally { if (current === oauthGeneration) oauthLoading.value = false; }
}

/** 结束当前账号尚待提交的授权。@param account 原账号。@return 无。 */
async function cancelAgyReauth(account:Account): Promise<void> {
  const operation = account.credential_state?.operation_id;
  if (!operation) return;
  try { await api.cancelOAuth(operation,'antigravity'); await load(); toast('原授权已结束','success'); }
  catch (cause) { toast((cause as Error).message); }
}

/** 展示账号凭据的业务状态。@param account 当前账号。@return 中文状态。 */
function agyPhaseLabel(account:Account): string {
  const recovery = account.credential_state?.recovery_status;
  if (recovery === 'retrying') return '正在恢复凭据';
  if (recovery === 'needs_check') return '凭据需核对';
  if (recovery === 'reauthorization_required') return '需要重新授权';
  const labels:Record<string,string>={ready:'凭据就绪',refresh_pending:'刷新待确认',reauth:'重新授权中',reconcile:'凭据待核对'};
  return labels[account.credential_state?.phase ?? ''] ?? '状态待更新';
}

/** 将已保存的首个失败阶段转换为脱敏文案。@param account 当前账号。@return 已知阶段文案。 */
function agyFirstFailure(account: Account): string | undefined {
  const stages: Record<string, string> = {
    start_refresh: '启动凭据刷新', refresh: '原生凭据刷新', stop_refresh: '结束原刷新进程',
    credential_file: '读取落盘凭据', credential_expiry: '核对凭据有效期', identity_check: '核对账号身份',
    receipt: '保存恢复回执', receipt_validation: '核对凭据回执',
    receive_receipt: '接收原生回执', gateway_commit: '提交网关凭据',
  };
  return stages[account.credential_state?.first_failure ?? ''];
}

/** 对账当前账号的原凭据操作。@param id 冻结账号。@return 无。 */
async function recoverAgy(id:number): Promise<void> {
  try { await api.recoverAgyCredentials(id); await load(); toast('原凭据操作已核对', 'success'); }
  catch (cause) { toast((cause as Error).message); }
}

/** 将授权结果填入新建账号表单 */
function applyOAuthResult() {
  editorGeneration++;
  if (oauthTarget.value) { showOAuthFlow.value = false; return; }
  backendSaveIssue.value = null;
  proxyChoice.value = oauthSessionProxy.value;
  const r = oauthResult.value;
  if (!r) return;
  showOAuthFlow.value = false;
  editing.value = null;
  const isSetupToken = oauthMode.value === 'setup_token';
  form.value = {
    platform: oauthPlatform.value,
    agy_system_prompt_homoglyph_enabled: false,
    client_system_prompt_policy: 'independent',
    agy_gif_frames_enabled: false,
    agy_disable_safety_filtering: false,
    name: '',
    email: r.email_address || '',
    auth_type: isSetupToken ? 'setup_token' : 'oauth',
    setup_token: isSetupToken ? r.access_token : '',
    access_token: isSetupToken ? '' : (r.access_token || ''),
    refresh_token: isSetupToken ? '' : (r.refresh_token || ''),
    expires_at: (!isSetupToken && r.expires_at) ? String(r.expires_at * 1000) : '',
    proxy_url: '',
    billing_mode: 'strip',
    request_backend: 'legacy' as RequestBackend,
    account_uuid: r.account_uuid || '',
    organization_uuid: r.organization_uuid || '',
    subscription_type: '',
    rate_limit_tier: '',
    concurrency: 3,
    priority: 50,
    rpm_limit: 0,
    five_hour_usage_limit_percent: 0,
    seven_day_usage_limit_percent: 0,
    auto_telemetry: false,
    auto_poll_usage: false,
    allow_1m_models: DEFAULT_ALLOW_1M_MODELS,
    allow_fast_mode: false,
    upstream_session_pool_enabled: false,
    upstream_session_pool_size: DEFAULT_UPSTREAM_SESSION_POOL_SIZE,
    upstream_session_ttl_minutes: DEFAULT_UPSTREAM_SESSION_TTL_MINUTES,
    upstream_session_refresh_policy: DEFAULT_UPSTREAM_SESSION_REFRESH_POLICY,
  };
  detailAccountId.value = null;
  workspaceTab.value = 'configuration';
  resetNumberDrafts();
  showForm.value = true;
}

/** 复制文本到剪贴板（兼容非安全上下文） */
async function copyText(text: string) {
  if (!text) {
    toast('没有可复制的内容');
    return;
  }

  // 1. 优先使用 Clipboard API（仅在安全上下文 HTTPS / localhost 可用）
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制', 'success');
      return;
    } catch {
      // 失败则继续走降级方案
    }
  }

  // 2. 降级方案：临时 textarea + execCommand('copy')
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '0';
    ta.style.left = '0';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, text.length);
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    toast(ok ? '已复制' : '复制失败', ok ? 'success' : 'error');
  } catch {
    toast('复制失败');
  }
}
</script>

<template>
  <div class="accounts-page">
    <template v-if="!workspaceAccountId">
    <!-- 标题栏 -->
    <PageHeader title="账号管理" description="状态、用量和调度集中展示，常用操作直接可达。">
      <template #actions>
        <Button
          @click="openOAuthFlow()"
          variant="outline"
          class="account-authorize-button"
        >
          <KeyRound :size="15" />授权登录
        </Button>
        <Button @click="openCreate">
          <Plus :size="15" />添加账号
        </Button>
      </template>
    </PageHeader>

    <!-- 移动端应用栏的搜索按钮：桌面上应用栏隐藏，按钮随之不可见。 -->
    <Teleport defer to="#console-toolbar-page-actions">
      <button type="button" class="console-toolbar-action account-search-toggle" aria-label="搜索账号" aria-controls="account-toolbar" :aria-expanded="searchRowOpen" @click="toggleSearch"><Search /></button>
    </Teleport>
    <Toolbar id="account-toolbar" ref="toolbarRef" class="account-toolbar" :class="{ 'is-search-open': searchRowOpen }">
      <ChoiceSelect class="account-platform-filter" :model-value="platformFilter" label="平台筛选" :options="[{value:'all',label:'全部平台'},...platformOptions]" @update:model-value="choosePlatformFilter" />
      <Segmented class="account-filter-tabs" :model-value="accountFilter" :options="statusFilterOptions" label="账号状态筛选" @update:model-value="chooseAccountFilter" />
      <template #end><SearchInput v-model="accountQuery" label="搜索账号" placeholder="搜索名称或邮箱" :maxlength="256" @search="applyAccountFilter" /></template>
    </Toolbar>

    <NoticeStrip v-if="accountLoadFailed" tone="warning" role="alert"><AlertCircle />账号刷新失败，当前展示上次快照；负载与调度状态可能已陈旧。</NoticeStrip>
    <!-- 账号卡片列表 -->
    <div class="account-card-grid">
      <Card
        v-for="a in accounts"
        :key="a.id"
        class="account-card"
      >
        <div class="account-card-body">
          <div class="account-card-topline">
            <div class="account-identity">
              <IconTile size="lg" :tone="a.platform === 'antigravity' ? 'agy' : 'primary'" class="account-avatar">{{ (a.name || a.email || '?')[0]?.toUpperCase() }}<i class="account-avatar-state" :class="a.status" /></IconTile>
              <button type="button" class="account-identity-text" @click="openAccountDetails(a)">
                <div class="account-card-title">
                  <h3>{{ a.name || a.email }}</h3>
                  <span class="account-card-badges">
                    <PlatformBadge :platform="a.platform || 'claude_code'" />
                    <Badge v-if="cardPlan(a)" class="account-plan">{{ cardPlan(a) }}</Badge>
                  </span>
                </div>
                <p>{{ a.email }}</p>
              </button>
            </div>
            <div class="account-work-controls">
              <label class="account-admission"><span>接收请求</span><Switch class="account-status-switch" :model-value="a.work_control?.api_accepting === true" :disabled="!a.work_control || workPending.has(a.id)" :label="`${a.work_control?.api_accepting ? '关闭' : '开启'}接收请求 ${a.name || a.email}`" @update:model-value="toggleScheduling(a)" /></label>
              <Button size="sm" :variant="overallEnabled(a) ? 'destructive' : 'secondary'" class="account-work-toggle" :class="{ 'account-stop-action': overallEnabled(a) }" :disabled="!a.work_control || workPending.has(a.id)" @click="changeOverall(a, !overallEnabled(a))">{{ overallEnabled(a) ? '停用账号' : '启用账号' }}</Button>
            </div>
          </div>
          <div class="account-network">
            <button type="button" @click="openEdit(a)"><Globe :size="14" /><span>{{ a.proxy_name || publicProxy(a.proxy_url) }}</span></button>
            <ExecutionNodeBadge :node="accountNode(a)" :status="nodeStatus(a)" :attention="nodeAttention(a)" />
            <router-link :to="{ name: 'environments', query: { gateway_account: String(a.id) } }"><Box :size="14" />运行环境</router-link>
          </div>
          <div v-if="overallWorkNote(a)" class="account-work-status">
            <span>{{ overallWorkNote(a) }}</span>
            <Button v-if="overallStates.get(a.id)?.phase==='reconcile'" size="sm" variant="secondary" :disabled="workPending.has(a.id)" @click="changeOverall(a, false)">继续停用</Button>
          </div>
          <p v-if="overallStates.get(a.id)?.message" class="account-note" role="status">{{ overallStates.get(a.id)?.message }}</p>
          <NoticeStrip class="account-health" :tone="accountHealthTone(a)">
            <Check v-if="accountHealthTone(a) === 'success'" /><AlertCircle v-else-if="accountHealthTone(a) !== 'neutral'" /><i v-else class="account-health-dot" />
            <span class="account-health-message">{{ a.status === 'disabled' ? '已停用' : a.v3_scheduling ? schedulingReasonLabel(a.v3_scheduling.capacity.reason) : statusStyle(a).label }}<template v-if="a.v3_scheduling"> · {{ a.v3_scheduling.phases.running > 0 ? `正在处理 ${a.v3_scheduling.phases.running} 个请求` : '当前空闲' }}</template><template v-else-if="a.platform === 'antigravity' && a.status === 'active' && a.active_requests != null"> · {{ a.active_requests > 0 ? `在途 ${a.active_requests} 个请求` : '当前空闲' }}</template></span>
            <template v-if="(a.queued_requests ?? 0)>0" #end><button type="button" class="account-queue-alert" @click="openAccountCapacity(a)">排队 {{ a.queued_requests }}</button></template>
          </NoticeStrip>
          <NoticeStrip v-if="a.auth_error" tone="danger" role="alert" class="account-strip-text">{{ a.auth_error }}</NoticeStrip>
          <p v-if="a.platform === 'antigravity' && a.credential_state && a.credential_state.phase !== 'ready'" class="account-note" role="status">{{ agyPhaseLabel(a) }}<template v-if="agyFirstFailure(a)"> · 首次失败阶段 {{ agyFirstFailure(a) }}</template></p>
          <NoticeStrip v-if="a.v3_scheduling_error" tone="warning" class="account-strip-text">{{ a.v3_scheduling_error }}，调度观测待更新。</NoticeStrip>
          <p v-if="a.credential_ownership" class="account-note" role="status">{{ a.credential_ownership.phase === 'ready' ? (a.credential_ownership.owner === 'local' ? '本地管理凭据 · 网关已暂停' : '网关管理凭据') : (a.credential_ownership.phase === 'reauth' ? '重新授权中 · 上游活动暂停' : '凭据交接待确认 · 请在账号环境页对账') }}</p>
          <EntityBlock v-if="!a.platform || a.platform === 'claude_code' || a.platform === 'antigravity'" class="account-routing">
            <div><span>转发方式</span><strong><template v-if="a.platform === 'antigravity'">原生运行时 <small v-if="agyVersion(a)">Antigravity {{ agyVersion(a) }}</small></template><template v-else-if="a.request_backend === 'native293'">原生运行时 <small>Claude Code 2.1.293</small></template><template v-else>{{ backendName(a.request_backend) }}</template></strong></div>
            <button type="button" @click="openScheduling(a)">
              <span>调度优先级</span><strong>{{ a.priority }}<ArrowRight :size="14" /></strong>
              <Badge :variant="a.v3_scheduling ? 'default' : 'secondary'" class="account-score">{{ activeSchedulingScore(a) }}</Badge>
            </button>
          </EntityBlock>

          <AgyAccountUsage v-if="a.platform === 'antigravity'" :account="a" :refreshing="refreshingUsage.has(a.id)"
            :refresh-error="usageRefreshErrors.get(a.id)" />
          <section v-if="a.platform !== 'antigravity'" class="account-usage-windows">
            <header><span>用量</span><small>{{ a.usage_fetched_at ? new Date(a.usage_fetched_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) + ' 更新' : '未刷新' }}</small><button type="button" @click="refreshUsage(a.id)" :disabled="refreshingUsage.has(a.id)" aria-label="刷新用量"><RefreshCw :size="14" />刷新</button></header>
            <p v-if="a.request_usage" class="usage-record-start">网关记录始于 {{ new Date(a.request_usage.recorded_since).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) }}</p>
            <div v-for="window in usageWindows" :key="window.key" class="account-usage-window">
              <UsageWindowStats v-if="window.key !== 'seven_day_fable'" :stats="a.request_usage?.[window.key]" :label="window.key === 'five_hour' ? '5h' : '7d'" />
              <div class="usage-window-label"><span>{{ window.label }}<template v-if="window.key !== 'seven_day_fable'"> · {{ a[window.key === 'five_hour' ? 'five_hour_usage_limit_percent' : 'seven_day_usage_limit_percent'] > 0 ? '上限 ' + a[window.key === 'five_hour' ? 'five_hour_usage_limit_percent' : 'seven_day_usage_limit_percent'] + '%' : '未限制' }}</template></span><strong>{{ window.key === 'five_hour' ? fiveHourLabel(a.usage_data, usagePercentLabel(usageWindow(a.usage_data, window.key))) : usagePercentLabel(usageWindow(a.usage_data, window.key)) }}</strong></div>
              <div class="usage-window-bar"><i :data-tone="usageBarTone(effectiveUtil(usageWindow(a.usage_data, window.key)))" :style="{ width: Math.min(effectiveUtil(usageWindow(a.usage_data, window.key)), 100) + '%' }" /></div>
              <div v-if="hasFutureReset(usageWindow(a.usage_data, window.key))" class="usage-window-reset"><span>{{ formatTimeLeft(usageWindow(a.usage_data, window.key)?.resets_at) }} 后重置</span><span>{{ new Date(usageWindow(a.usage_data, window.key)!.resets_at!).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }}</span></div>
            </div>
          </section>
          <div v-if="!a.platform || a.platform === 'claude_code' || a.platform === 'antigravity'" class="account-live-metrics">
            <button type="button" @click="openAccountCapacity(a)"><span>并发</span><strong :class="concurrencyClass(a)">{{ a.platform === 'antigravity' && a.current_concurrency == null ? '—' : formatConcurrencySlots(a.current_concurrency) }}<small>/{{ formatConcurrencySlots(a.concurrency) }}</small></strong><i class="metric-track" :class="concurrencyClass(a)"><i :style="{width:Math.min(100,(a.current_concurrency??0)/Math.max(1,a.concurrency)*100)+'%'}" /></i></button>
            <button type="button" @click="openAccountCapacity(a)"><span>RPM</span><strong :class="rpmClass(a)">{{ cardRpm(a) ?? '—' }}<small>/{{ a.rpm_limit>0?a.rpm_limit:'∞' }}</small></strong><i class="metric-track" :class="rpmClass(a)"><i :style="{width:a.rpm_limit>0?Math.min(100,(cardRpm(a)??0)/a.rpm_limit*100)+'%':'0%'}" /></i></button>
            <button type="button" @click="openAccountCapacity(a)"><span>排队<ChevronRight :size="14" /></span><strong :class="(a.queued_requests ?? 0) > 0 ? 'is-warning' : ''">{{ a.queued_requests ?? (a.platform === 'antigravity' ? '—' : 0) }}</strong></button>
            <button type="button" @click="openAccountCapacity(a)"><span>{{ a.platform === 'antigravity' ? '在途请求' : '活跃会话' }}</span><strong>{{ (a.platform === 'antigravity' ? a.active_requests : a.v3_scheduling?.active_sessions) ?? '—' }}</strong></button>
          </div>

          <!-- 停用 / 限流原因 -->
          <NoticeStrip
            v-if="a.disable_reason && (a.status === 'disabled' || (a.rate_limit_reset_at && new Date(a.rate_limit_reset_at) > new Date()))"
            :tone="a.status === 'disabled' ? 'danger' : 'warning'"
            class="account-strip-text account-disable-reason"
          >
            {{ a.disable_reason }}
            <template v-if="a.rate_limit_reset_at && new Date(a.rate_limit_reset_at) > new Date()" #end>剩余 {{ formatTimeLeft(a.rate_limit_reset_at) }}</template>
          </NoticeStrip>
        </div>
        <footer class="account-card-actions">
          <button type="button" @click="openEdit(a)"><Pencil :size="14" />编辑</button>
          <button type="button" @click="refreshUsage(a.id)" :disabled="refreshingUsage.has(a.id)"><RefreshCw :size="14" />{{ refreshingUsage.has(a.id) ? '刷新中' : '用量' }}</button>
          <OperationFeedback :status="testStates.get(a.id)?.status" :message="testStates.get(a.id)?.message" :identity="a.name" @action="test(a.id)" />
          <button type="button" @click="openAccountDetails(a)"><ArrowRight :size="14" />详情</button>
          <button type="button" @click="confirmDelete(a.id)" class="danger"><Trash2 :size="14" />删除</button>
        </footer>
      </Card>

      <!-- 空状态 -->
      <Empty v-if="accounts.length === 0" class="account-empty" title="暂无账号" description="点击“添加账号”开始"><template #icon><Users /></template></Empty>
    </div>

    <!-- 分页 -->
    <Pagination v-if="totalCount > 0" v-model:page-size="pageSize" class="account-pagination" :page="currentPage" :total="totalCount" :page-sizes="[12,24,48,96]" label="账号列表分页" unit="个账号" @update:page="goToPage" />
    </template>

    <!-- 账号工作区：概览、配置、调度、环境与诊断共用同一居中弹窗，只有内容区滚动。 -->
    <ModalDialog v-model:open="workspaceOpen" class="account-workspace" :title="detailAccount?.name || detailAccount?.email || '添加账号'" :description="detailAccount?.email || '填写账号配置与认证信息'" :width="820">
      <template v-if="detailAccount" #media><IconTile size="lg" :tone="detailAccount.platform === 'antigravity' ? 'agy' : 'primary'" class="account-avatar">{{ (detailAccount.name || detailAccount.email || '?')[0]?.toUpperCase() }}<i class="account-avatar-state" :class="detailAccount.status" /></IconTile></template>
      <template v-if="detailAccount" #title-extra><span class="account-card-badges"><PlatformBadge :platform="detailAccount.platform || 'claude_code'" /><Badge v-if="cardPlan(detailAccount)" class="account-plan">{{ cardPlan(detailAccount) }}</Badge></span></template>
      <template v-if="detailAccount" #nav><Segmented class="account-workspace-tabs" :model-value="workspaceTab" :options="workspaceTabOptions" label="账号工作区" @update:model-value="selectWorkspaceTab" /></template>
      <div v-if="detailAccount" v-show="workspaceTab === 'overview'" class="account-workspace-scroll account-overview">
        <div class="account-overview-context"><div class="account-overview-status">
          <Badge :variant="healthBadgeVariant(detailAccount)" dot>{{ statusStyle(detailAccount).label }}</Badge>
          <Badge v-if="detailAccount.platform !== 'antigravity'" :variant="detailAccount.v3_scheduling ? 'default' : 'secondary'" class="account-score">{{ activeSchedulingScore(detailAccount) }}</Badge>
        </div>
        <ExecutionNodeBadge :node="accountNode(detailAccount)" :status="nodeStatus(detailAccount)" :attention="nodeAttention(detailAccount)" /></div>
        <section v-if="detailAccount.platform !== 'antigravity'" class="account-usage-windows"><header><span>用量</span><small>{{ detailAccount.usage_fetched_at ? new Date(detailAccount.usage_fetched_at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}) + ' 更新' : '未刷新' }}</small></header>
          <div v-for="window in usageWindows" :key="window.key" class="account-usage-window"><UsageWindowStats v-if="window.key!=='seven_day_fable'" :stats="detailAccount.request_usage?.[window.key]" :label="window.key==='five_hour'?'5h':'7d'" /><div class="usage-window-label"><span>{{ window.label }}</span><strong>{{ usagePercentLabel(usageWindow(detailAccount.usage_data,window.key)) }}</strong></div><div class="usage-window-bar"><i :data-tone="usageBarTone(effectiveUtil(usageWindow(detailAccount.usage_data,window.key)))" :style="{width:Math.min(100,effectiveUtil(usageWindow(detailAccount.usage_data,window.key)))+'%'}" /></div><p v-if="hasFutureReset(usageWindow(detailAccount.usage_data,window.key))" class="usage-window-reset">{{ formatTimeLeft(usageWindow(detailAccount.usage_data,window.key)?.resets_at) }} 后重置</p></div>
        </section>
        <template v-if="detailAccount.platform === 'antigravity'">
          <AgyAccountUsage :account="detailAccount" expanded />
          <EntityBlock class="account-capabilities">
            <header><h3>平台能力</h3><Badge :variant="detailAccount.credential_state?.phase !== 'ready' ? 'warning' : 'success'" :class="{'is-warning':detailAccount.credential_state?.phase !== 'ready'}">{{ agyPhaseLabel(detailAccount) }}</Badge></header>
            <p v-if="agyFirstFailure(detailAccount)" class="account-note">首次失败阶段 {{ agyFirstFailure(detailAccount) }}</p>
            <dl><div><dt>模型目录</dt><dd>{{ overviewCapabilities?.models ? `${overviewCapabilities.models.length} 个模型` : '未观测' }}</dd></div><div><dt>能力快照</dt><dd>{{ !overviewCapabilities ? '未观测' : Date.now() - overviewCapabilities.observed_at_ms > 300000 ? '待刷新' : '已更新' }}</dd></div><div class="capability-observed"><dt>观测时间</dt><dd>{{ overviewCapabilities?.observed_at_ms ? new Date(overviewCapabilities.observed_at_ms).toLocaleString('zh-CN') : '未提供' }}</dd></div></dl>
            <details class="account-capability-details"><summary>可用模型<ChevronRight :size="14" /></summary><div class="account-model-list"><code v-for="model in overviewCapabilities?.models" :key="model">{{ model }}</code><p v-if="!overviewCapabilities?.models?.length">{{ overviewCapabilities?.models ? '目录为空' : '模型目录未观测' }}</p></div></details>
            <details class="account-capability-details">
              <summary>套餐与来源<ChevronRight :size="14" /></summary>
              <dl class="account-provider-details">
                <div><dt>平台计划</dt><dd>{{ overviewQuota?.plan || '未提供' }}</dd></div>
                <div><dt>订阅档位</dt><dd>{{ overviewAgyTier || '未提供' }}</dd></div>
                <div><dt>来源</dt><dd>{{ overviewAgySource }}</dd></div>
              </dl>
            </details>
            <div v-if="detailAccount.credential_state?.phase !== 'ready'" class="account-credential-actions"><Button v-if="detailAccount.credential_state?.phase === 'reauth'" size="sm" variant="outline" @click="cancelAgyReauth(detailAccount)">结束原授权</Button><Button size="sm" variant="outline" @click="recoverAgy(detailAccount.id)">核对凭据</Button></div>
          </EntityBlock>
        </template>
        <div class="account-overview-section-head"><h3>请求配置</h3><button type="button" @click="changeWorkspaceTab('scheduling')">调度详情<ArrowRight :size="14" /></button></div>
        <EntityBlock class="account-overview-block">
          <dl v-if="detailAccount.platform === 'antigravity'" class="account-overview-settings"><div><dt>并发</dt><dd>{{ detailAccount.current_concurrency ?? '—' }} / {{ detailAccount.concurrency }}</dd></div><div><dt>RPM</dt><dd>{{ cardRpm(detailAccount) ?? '—' }} / {{ detailAccount.rpm_limit || '不限' }}</dd></div><div><dt>调度优先级</dt><dd>{{ detailAccount.priority }}</dd></div></dl>
          <dl v-else class="account-overview-settings"><div><dt>并发上限</dt><dd>{{ detailAccount.concurrency }}</dd></div><div><dt>RPM 上限</dt><dd>{{ detailAccount.rpm_limit || '不限' }}</dd></div><div><dt>调度优先级</dt><dd>{{ detailAccount.priority }}</dd></div></dl>
        </EntityBlock>
        <div class="account-overview-actions">
          <OperationFeedback label="测试连接" button-variant="outline" :status="testStates.get(detailAccount.id)?.status" :message="testStates.get(detailAccount.id)?.message" :identity="detailAccount.name || detailAccount.email" @action="test(detailAccount.id)" />
          <Button type="button" variant="outline" @click="refreshUsage(detailAccount.id)" :disabled="refreshingUsage.has(detailAccount.id)"><RefreshCw :size="14" />{{ refreshingUsage.has(detailAccount.id) ? '刷新中' : '刷新用量' }}</Button>
        </div>
        <section class="account-overview-control"><header><h3>账号控制</h3><InfoTooltip label="账号控制说明"><template #trigger><span>控制说明</span></template><p>关闭接收请求后，已接纳的请求正常收尾。</p><p>停用账号会停止全部新工作，并等待已接纳的请求收尾。</p></InfoTooltip></header><div class="account-overview-control-row"><label class="account-admission"><span>接收请求</span><Switch class="account-status-switch" :model-value="detailAccount.work_control?.api_accepting === true" :disabled="!detailAccount.work_control || workPending.has(detailAccount.id)" :label="`${detailAccount.work_control?.api_accepting ? '关闭' : '开启'}接收请求 ${detailAccount.name || detailAccount.email}`" @update:model-value="toggleScheduling(detailAccount)" /></label><Button v-if="detailAccount.status !== 'active' || isRateLimited(detailAccount)" type="button" size="sm" variant="outline" :disabled="workPending.has(detailAccount.id)" @click="restoreAvailability(detailAccount)">恢复资格</Button><Button type="button" size="sm" :variant="overallEnabled(detailAccount) ? 'destructive' : 'secondary'" :class="{'account-stop-action':overallEnabled(detailAccount)}" :disabled="!detailAccount.work_control || workPending.has(detailAccount.id)" @click="changeOverall(detailAccount, !overallEnabled(detailAccount))">{{ overallEnabled(detailAccount) ? '停用账号' : '启用账号' }}</Button></div><p v-if="overallWorkNote(detailAccount)" class="account-overview-note" role="status">{{ overallWorkNote(detailAccount) }}</p></section>
        <p v-if="overallStates.get(detailAccount.id)?.message" class="account-overview-note" role="status">{{ overallStates.get(detailAccount.id)?.message }}</p>
      </div>
      <form id="account-editor-form" v-show="workspaceTab === 'configuration'" @submit.prevent="save" class="account-editor-form">
        <div class="account-editor-scroll complete-account-form">
          <section class="account-form-section"><h3>基础配置</h3><div class="account-edit-grid three"><ChoiceSelect :model-value="form.platform" @update:model-value="selectAccountPlatform" label="账号平台" :disabled="!!editing || savingAccount" :options="platformOptions" /><label class="approved-field"><span>备注名（选填）</span><Input v-model="form.name"  /></label><label class="approved-field"><span>邮箱</span><Input v-model="form.email" type="email" :readonly="!!editing && isAgyForm" required /></label></div>
            <div v-if="!isAgyForm" class="forwarding-field">
              <span class="fui-label">转发方式</span>
              <RadioCardGroup :model-value="form.request_backend" class="forwarding-options" name="request_backend" label="转发方式"
                :options="backendOptions" @update:model-value="value => form.request_backend = value as RequestBackend" />
              <template v-if="editing?.request_backend_revision !== undefined">
                <p class="form-help">当前生效 {{ backendName(editing.request_backend) }}</p>
                <p v-if="editing.request_backend_pending" class="form-help">
                  等待切换到 {{ backendName(editing.request_backend_pending) }}。
                  {{ editing.request_backend_wait_reason === 'runtime_unconfirmed' ? '运行环境状态待确认。' : '原轮排空并经后台核对后生效。' }}
                  选择当前生效方式并保存即可撤销等待。
                </p>
                <Button type="button" variant="outline" :disabled="savingAccount" @click="reloadBackend()">刷新转发状态</Button>
              </template>
              <p v-else class="form-help">请在账号空闲时切换转发方式。</p>
              <NoticeStrip v-if="backendSaveIssue" tone="warning" role="alert">
                <AlertCircle /><span><strong v-if="backendSaveIssue.otherSaved">其他设置已保存。 </strong>{{ backendSaveIssue.detail }}</span>
              </NoticeStrip>
            </div>
            <ProxyPicker v-model="proxyChoice" :current-label="editingProxyLabel" /></section>
          <section v-if="!isAgyForm && form.request_backend === 'native293'" class="account-form-section">
            <h3>客户端系统提示词</h3>
            <p>用客户端指令替换默认工作正文（默认）</p>
            <p class="form-help">普通 Messages 请求省略指令时保留默认工作正文。显式空值清空工作正文，保留 Claude Code 身份和计费。</p>
          </section>
          <section v-else-if="!isAgyForm && editing?.tui_system_prompt_policy_available && form.request_backend === 'tui_v2'" class="account-form-section">
            <ChoiceSelect v-model="form.client_system_prompt_policy" label="客户端系统提示词" :options="[
              {value:'append',label:'追加到原生系统提示词（默认）'},
              {value:'replace',label:'用客户端指令替换默认工作正文'},
              {value:'user_reminder',label:'放入用户提醒'},
            ]" />
            <p v-if="form.client_system_prompt_policy === 'replace'" class="form-help">普通 Messages 请求省略指令时保留默认工作正文。显式空值清空工作正文，保留身份和计费。</p>
            <p v-else-if="form.client_system_prompt_policy === 'user_reminder'" class="form-help">普通 Messages 请求的非空指令进入首条适合的用户消息。省略或传空时仅使用默认工作正文。</p>
            <p v-else class="form-help">普通 Messages 请求的非空指令按顺序追加。省略或传空时保留默认工作正文。</p>
          </section>
          <section v-if="!isAgyForm" class="account-form-section"><h3>用量与调度</h3><div class="account-edit-grid three"><NumberInput v-model="numberDrafts.concurrency" label="并发上限" :min="1" required /><NumberInput v-model="numberDrafts.rpm_limit" label="RPM 上限" :min="0" required /><NumberInput v-model="numberDrafts.priority" label="调度优先级" :min="1" required /></div><div class="account-edit-grid"><NumberInput v-model="numberDrafts.five_hour_usage_limit_percent" label="5 小时用量上限（%）" :min="0" :max="100" required /><NumberInput v-model="numberDrafts.seven_day_usage_limit_percent" label="7 天用量上限（%）" :min="0" :max="100" required /></div><p class="form-help">RPM 和用量上限填 0 表示不限。达到任一用量上限后停止分配新消息，窗口重置后恢复。未知用量保持可用，单次或并发请求可能越线。</p></section>
          <section v-if="!isAgyForm" class="account-form-section"><h3>请求与模型</h3><div class="account-edit-grid"><ChoiceSelect v-model="form.billing_mode" label="Billing 模式" :options="[{value:'strip',label:'清除（Strip）'},{value:'rewrite',label:'重写（Rewrite）'}]" /><label class="approved-field"><span>允许 1M 上下文的模型</span><Input v-model="form.allow_1m_models"  /></label></div><div class="model-presets"><span>模型预设</span><Button type="button" size="sm" variant="secondary" @click="form.allow_1m_models = 'opus'">仅 Opus</Button><Button type="button" size="sm" variant="secondary" @click="form.allow_1m_models = DEFAULT_ALLOW_1M_MODELS">Opus + Sonnet 5</Button><Button type="button" size="sm" variant="secondary" @click="form.allow_1m_models = ''">全部关闭</Button></div><p class="form-help">模型以逗号分隔，按子串匹配。留空关闭 1M 上下文。Sonnet 5 使用完整名称以区分 Sonnet 4.6。</p>
            <Checkbox v-model="form.allow_fast_mode" class="account-check"><strong>允许客户端 Fast Mode</strong><small>允许后保留客户端申请，可能增加计费和限流风险。</small></Checkbox><Checkbox v-model="form.auto_telemetry" class="account-check"><strong>自动遥测</strong><small>由网关代替客户端发送遥测请求。</small></Checkbox><Checkbox v-if="form.auth_type==='oauth'" v-model="form.auto_poll_usage" class="account-check"><strong>自动轮询用量</strong><small>后台定时拉取 OAuth 账号的用量数据。</small></Checkbox></section>
          <section v-if="!isAgyForm" class="account-form-section"><h3>上游 Session 池</h3><Checkbox v-model="form.upstream_session_pool_enabled" class="account-check"><strong>启用 Session 池</strong><small>仅改写发往上游的会话；内部绑定、RPM 与本地缓存仍按真实会话隔离。</small></Checkbox><div class="account-edit-grid three"><NumberInput v-model="numberDrafts.upstream_session_pool_size" label="池容量（0 表示关闭）" :min="0" :max="20" required /><NumberInput v-model="numberDrafts.upstream_session_ttl_minutes" label="活跃 TTL（分钟）" :min="5" :max="1440" required /><ChoiceSelect v-model="form.upstream_session_refresh_policy" label="TTL 刷新策略" :options="[{value:'mapped_request',label:'映射请求刷新'},{value:'owner_only',label:'仅属主刷新'}]" /></div></section>
          <details v-if="!isAgyForm" class="account-auth-fields account-advanced account-form-section" :open="!editing"><summary>认证与高级配置<ChevronRight :size="14" /></summary><p class="form-help">认证通常由任务或工程创建流程提供。凭证留空保持原值；切换认证方式需要填写对应凭证。</p><div class="account-edit-grid"><ChoiceSelect v-model="form.auth_type" label="认证方式" :options="[{value:'oauth',label:'OAuth'},{value:'setup_token',label:'Setup Token'}]" /><label v-if="form.auth_type==='setup_token'" class="approved-field"><span>Setup Token</span><Input v-model="form.setup_token" type="password" autocomplete="new-password" :required="!editing" :placeholder="editing ? '留空保持不变' : 'sk-ant-oat01-...'" /></label></div><template v-if="form.auth_type!=='setup_token'"><div class="account-edit-grid"><label class="approved-field"><span>Access Token（选填）</span><Input v-model="form.access_token" type="password" autocomplete="new-password" placeholder="留空保持不变" /></label><label class="approved-field"><span>Refresh Token</span><Input v-model="form.refresh_token" type="password" autocomplete="new-password" :required="!editing" placeholder="留空保持不变" /></label></div><label class="approved-field"><span>过期时间（毫秒时间戳）</span><Input v-model="form.expires_at" inputmode="numeric" placeholder="留空清除到期时间" /></label><p v-if="editing?.expires_at" class="form-help">当前过期时间：{{ formatExpiresAt(editing.expires_at) }}</p><p v-if="editing?.auth_error" class="form-help is-danger">最近认证错误：{{ editing.auth_error }}</p></template><div class="account-edit-grid"><ChoiceSelect :model-value="form.subscription_type" @update:model-value="selectSubscription" label="订阅类型" :options="[{value:'',label:'未设置'},{value:'max',label:'Max'},{value:'ultra',label:'Ultra'},{value:'pro',label:'Pro'},{value:'team',label:'Team'},{value:'enterprise',label:'Enterprise'}]" /><label class="approved-field"><span>官方分级</span><Input v-model="form.rate_limit_tier"  /></label></div><div class="account-edit-grid"><label class="approved-field"><span>Account UUID</span><Input v-model="form.account_uuid"  /></label><label class="approved-field"><span>Organization UUID</span><Input v-model="form.organization_uuid"  /></label></div><p class="form-help">修改订阅类型时清除旧分级，可填写新类型的官方分级。</p><div class="account-form-actions"><Button type="button" size="sm" variant="outline" @click="openOAuthFlow()">重新授权</Button></div></details>
          <section v-if="isAgyForm" class="account-form-section">
            <h3>Antigravity 配置</h3><p class="form-help">账号能力来自最近的原生观测。模型服务等待运行环境接入。</p>
            <Checkbox v-model="form.agy_system_prompt_homoglyph_enabled" class="account-check"><strong>系统提示词同形体转换</strong><small>按当前账号保存，开启后转换系统提示词文本。</small></Checkbox>
            <ChoiceSelect v-model="form.client_system_prompt_policy" label="客户端系统提示词" :options="[
              {value:'independent',label:'作为独立系统指令发送（默认）'},
              {value:'user_reminder',label:'放入用户提醒'},
            ]" />
            <p class="form-help">Messages 的非空指令可移入首条适合的用户消息。省略或传空时使用独立系统段。Gemini 原生请求沿用独立系统段。</p>
            <Checkbox v-model="form.agy_gif_frames_enabled" class="account-check"><strong>GIF 抽帧兼容</strong><small>开启后每张 GIF 最多抽取 8 帧 PNG。</small></Checkbox>
            <Checkbox v-model="form.agy_disable_safety_filtering" class="account-check"><strong>使用 AGY 原生安全开关</strong><small>启用 disableSafetyFiltering，由 AGY 生成安全字段。客户端逐类阈值在关闭时应用。</small></Checkbox>
            <div class="account-edit-grid three"><NumberInput v-model="numberDrafts.concurrency" label="并发上限" :min="1" required /><NumberInput v-model="numberDrafts.rpm_limit" label="RPM 上限" :min="0" required /><NumberInput v-model="numberDrafts.priority" label="调度优先级" :min="1" required /></div>
            <div v-if="editing" class="account-form-actions">
              <Button type="button" size="sm" variant="outline" @click="openOAuthFlow(editing)">重新授权</Button>
              <Button v-if="editing.credential_state && editing.credential_state.phase !== 'ready'" type="button" size="sm" variant="outline" @click="recoverAgy(editing.id)">核对原凭据操作</Button>
            </div>
            <details class="account-advanced" :open="!editing"><summary>OAuth 凭据<ChevronRight :size="14" /></summary><p class="form-help">新账号需要有效的原生 OAuth 凭据。编辑时留空保持当前值。</p><div class="account-edit-grid"><label class="approved-field"><span>Access Token</span><Input v-model="form.access_token" type="password" autocomplete="new-password" :required="!editing" /></label><label class="approved-field"><span>Refresh Token</span><Input v-model="form.refresh_token" type="password" autocomplete="new-password" :required="!editing" /></label></div><label class="approved-field"><span>过期时间（毫秒时间戳）</span><Input v-model="form.expires_at" inputmode="numeric" :required="!editing" /></label></details>
          </section>
        </div>
      </form>
      <SchedulingDetails v-show="workspaceTab === 'scheduling'" embedded :open="workspaceOpen && workspaceTab === 'scheduling'" :account-id="detailAccount?.id ?? 0" :account-name="detailAccount?.name || detailAccount?.email || ''" :antigravity="detailAccount?.platform === 'antigravity'" />
      <div v-show="workspaceTab === 'diagnostics'" class="account-workspace-scroll account-diagnostics">
        <template v-if="detailAccount">
          <EntityBlock class="account-diagnostic-block">
            <dl class="account-diagnostic-summary">
              <div><dt>账号运行环境</dt><dd>{{ diagnosticLoading ? '正在读取…' : diagnosticEnvironment ? (diagnosticEnvironmentStates[diagnosticEnvironment.state] || diagnosticEnvironment.state) : '未观测到关联环境' }}</dd></div>
              <div><dt>CLI 版本</dt><dd>{{ diagnosticEnvironment?.cli_versions?.join(' / ') || '未采集' }}</dd></div>
              <div><dt>请求内核</dt><dd>{{ diagnosticEnvironment?.native_kernel?.current?.release || '未采集' }}</dd></div>
              <div><dt>运行时段</dt><dd>{{ diagnosticEnvironment?.run_window?.message || '未提供' }}</dd></div>
            </dl>
          </EntityBlock>
          <NoticeStrip v-if="diagnosticError" tone="danger" class="account-diagnostic-error account-strip-text" role="alert">环境摘要读取失败：{{ diagnosticError }}</NoticeStrip>
          <div class="account-diagnostic-actions"><Button as-child variant="outline"><router-link :to="{name:'environments',query:{gateway_account:String(detailAccount.id)}}"><Box :size="15" />管理环境</router-link></Button><Button as-child variant="outline"><router-link :to="{name:'requests',query:{account:String(detailAccount.id)}}"><Activity :size="15" />请求诊断</router-link></Button><Button as-child variant="outline"><router-link :to="{name:'environments',query:{gateway_account:String(detailAccount.id),section:'schedule'}}"><Clock :size="15" />运行时段</router-link></Button></div>
        </template>
        <details class="account-diagnostic-technical"><summary>技术与调度详情<ChevronRight :size="14" /></summary>
          <div v-if="detailAccount" class="account-detail-scroll">
            <dl class="account-detail-metrics five">
              <div><dt>智能评分</dt><dd>{{ detailAccount.v3_scheduling ? (detailAccount.v3_scheduling.factors.score * 100).toFixed(1) : '待更新' }}</dd></div>
              <InfoTooltip label="查看并发详情" title="并发与排队"><template #trigger><span class="account-detail-metric"><span>并发</span><strong :class="concurrencyClass(detailAccount)">{{ concurrencyLabel(detailAccount) }}</strong></span></template><div class="account-score-explanation"><p>标准槽位 {{ formatConcurrencySlots(detailAccount.current_concurrency) }} / {{ formatConcurrencySlots(detailAccount.concurrency) }}</p><p>内部单位 {{ formatConcurrencyUnits(detailAccount.current_concurrency_units) }} / {{ formatConcurrencyUnits(detailAccount.max_concurrency_units) }}</p><p>活跃请求 {{ detailAccount.active_requests ?? 0 }} · 排队请求 {{ detailAccount.queued_requests ?? 0 }}</p><p>排队单位 {{ formatConcurrencyUnits(detailAccount.queued_request_units) }}</p><small>普通请求占用 1 并发，Haiku 占用 0.5 并发。</small></div></InfoTooltip>
              <div><dt>排队</dt><dd :class="(detailAccount.queued_requests ?? 0) > 0 ? 'is-warning' : ''">{{ detailAccount.queued_requests ?? 0 }}</dd></div>
              <div><dt>429 等待</dt><dd :class="transientBackoffClass(detailAccount)">{{ transientBackoffLabel(detailAccount) }}</dd></div>
              <div><dt>{{ detailAccount.v3_scheduling ? '60秒提交 / RPM' : 'RPM' }}</dt><dd :class="rpmClass(detailAccount)">{{ rpmLabel(detailAccount) }}</dd></div>
            </dl>
            <EntityBlock v-if="detailAccount.v3_scheduling" class="account-detail-scheduling">
              <div class="account-detail-row"><strong>智能调度</strong><span :class="detailAccount.v3_scheduling.capacity.immediate ? 'is-success' : 'is-warning'">{{ schedulingReasonLabel(detailAccount.v3_scheduling.capacity.reason) }}</span></div>
              <p><span>绑定 {{ detailAccount.v3_scheduling.bound_sessions }} 个会话</span><span>活跃 {{ detailAccount.v3_scheduling.active_sessions }} 个</span><span>执行 {{ detailAccount.v3_scheduling.phases.running }} 个请求</span></p>
              <p>等槽 {{ detailAccount.v3_scheduling.phases.waiting_concurrency }} · 准备 {{ detailAccount.v3_scheduling.phases.preparing }} · 等发 {{ detailAccount.v3_scheduling.phases.waiting_send }} · 退避 {{ detailAccount.v3_scheduling.phases.backoff }}</p>
              <div class="account-detail-row"><span>{{ '智能偏好 ' + (detailAccount.v3_scheduling.factors.score * 100).toFixed(1) + '（高优）' }}</span><Button variant="outline" size="sm" @click="changeWorkspaceTab('scheduling')">调度详情</Button></div>
            </EntityBlock>
            <NoticeStrip v-else-if="detailAccount.v3_scheduling_error" tone="warning" class="account-strip-text">{{ detailAccount.v3_scheduling_error }}，不代表零负载。<template #end><button type="button" class="account-strip-link" @click="changeWorkspaceTab('scheduling')">查看详情</button></template></NoticeStrip>
            <p class="account-note">转发方式：{{ detailAccount.request_backend === 'native293' ? '原生运行时（Claude Code 2.1.293）' : backendName(detailAccount.request_backend) }}</p>
            <dl class="account-detail-metrics three">
              <div><dt>优先级</dt><dd>{{ detailAccount.priority }}</dd></div>
              <div><dt>Billing</dt><dd :class="detailAccount.billing_mode === 'rewrite' ? 'is-warning' : ''">{{ detailAccount.billing_mode === 'rewrite' ? '重写' : '清除' }}</dd></div>
              <div><dt>上游池槽位</dt><dd :class="upstreamSessionPoolClass(detailAccount)">{{ upstreamSessionPoolLabel(detailAccount) }}</dd></div>
            </dl>
            <dl class="account-detail-fields">
              <div><dt>代理</dt><dd>{{ publicProxy(detailAccount.proxy_url) }}</dd></div>
              <div><dt>认证方式</dt><dd>{{ authTypeLabel(detailAccount.auth_type) }}</dd></div>
              <div>
                <dt>自动遥测</dt>
                <dd :class="detailAccount.auto_telemetry ? 'is-success' : ''">{{ detailAccount.auto_telemetry ? '已开启' : '关闭' }}<small v-if="detailAccount.telemetry_count > 0"> · 已发送 {{ detailAccount.telemetry_count }} 次</small></dd>
                <dd v-if="detailAccount.telemetry_expires_at" class="is-warning">遥测中 · 停止于 {{ new Date(detailAccount.telemetry_expires_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }}</dd>
              </div>
              <div v-if="detailAccount.upstream_session_pool_enabled && detailAccount.upstream_session_pool_size > 0"><dt>上游 Session 池</dt><dd>TTL {{ detailAccount.upstream_session_ttl_minutes }} 分钟 · {{ upstreamSessionPolicyLabel(detailAccount.upstream_session_refresh_policy) }}</dd></div>
              <div v-if="detailAccount.auth_type === 'oauth'"><dt>自动轮询用量</dt><dd :class="detailAccount.auto_poll_usage ? 'is-success' : ''">{{ detailAccount.auto_poll_usage ? '已开启' : '关闭' }}</dd></div>
              <div><dt>{{ detailAccount.auth_type === 'oauth' ? 'Refresh Token' : 'Setup Token' }}</dt><dd class="is-mono">{{ authSecretPreview(detailAccount) }}</dd></div>
              <div v-if="detailAccount.auth_type === 'oauth'"><dt>过期时间</dt><dd>{{ formatExpiresAt(detailAccount.expires_at) }}</dd></div>
              <div v-if="detailAccount.auth_type === 'oauth' && detailAccount.auth_error"><dt>认证错误</dt><dd class="is-danger is-clamped">{{ detailAccount.auth_error }}</dd></div>
              <div>
                <dt>环境指纹</dt>
                <dd>{{ detailAccount.canonical_env?.platform || '—' }} / {{ detailAccount.canonical_env?.arch || '—' }}</dd>
                <dd>账号基础版本：v{{ detailAccount.canonical_env?.version || '—' }}</dd>
              </div>
              <div>
                <dt>画像选择方式</dt>
                <dd>{{ profileSelectionMode === 'client_version' ? '按客户端 UA 适配' : profileSelectionMode === 'account' ? '使用账号画像' : '未提供画像配置' }}</dd>
                <dd v-if="profileSelectionMode === 'client_version' && defaultVersionProfile">默认回退：v{{ defaultVersionProfile }}（准入通过后）</dd>
              </div>
              <div><dt>提示词环境</dt><dd>{{ detailAccount.canonical_prompt_env?.platform || '—' }} · {{ detailAccount.canonical_prompt_env?.shell || '—' }} · {{ detailAccount.canonical_prompt_env?.working_dir || '—' }}</dd></div>
              <div>
                <dt>进程指纹</dt>
                <template v-if="detailAccount.canonical_process?.observation?.source === 'v3:procfs:cli'">
                  <dd>容器内存上限 {{ detailAccount.canonical_process.constrained_memory === 0 ? '不限' : formatBytes(detailAccount.canonical_process.constrained_memory, 2) }}</dd>
                  <dd>CLI RSS {{ detailAccount.canonical_process.observation.sample_count ? formatBytes(detailAccount.canonical_process.observation.rss_bytes ?? undefined, 2) : '未采集' }}</dd>
                  <dd v-if="detailAccount.canonical_process.observation.sampled_at">官方 CLI 进程采样 · {{ new Date(detailAccount.canonical_process.observation.sampled_at * 1000).toLocaleString('zh-CN') }}</dd>
                </template>
                <dd v-else>内存 {{ formatBytes(detailAccount.canonical_process?.constrained_memory) }} · RSS {{ formatBytes(detailAccount.canonical_process?.rss_range?.[0]) }}–{{ formatBytes(detailAccount.canonical_process?.rss_range?.[1]) }}</dd>
              </div>
            </dl>
          </div>
        </details>
      </div>
      <template v-if="workspaceTab === 'configuration'" #footer>
        <span class="account-save-hint">修改后统一保存</span>
        <Button type="button" variant="outline" class="account-save-cancel" @click="workspaceOpen = false">取消</Button>
        <Button type="submit" form="account-editor-form" :disabled="savingAccount">{{ savingAccount ? '保存中…' : '保存修改' }}</Button>
      </template>
    </ModalDialog>

    <ConfirmationDialog :open="showDeleteConfirm" title="确认删除账号" message="此操作不可撤销，确认要删除此账号吗？" confirm-label="删除" danger :busy="deletingAccount" :error="deleteError" @confirm="executeDelete" @cancel="showDeleteConfirm=false" />

    <!-- 授权登录：三步表单，真实会话与凭据交接保持原接口；底栏按钮经 form 属性提交当前步骤。 -->
    <ModalDialog v-model:open="showOAuthFlow" class="account-oauth-dialog approved-oauth-dialog" title="授权登录" :description="oauthStep === 'generate' ? '将账号接入工作空间' : oauthStep === 'exchange' ? '完成浏览器授权后，填写返回的授权码' : '授权成功'" :width="440">
      <form v-if="oauthStep === 'generate'" id="account-oauth-step" class="approved-oauth-body" @submit.prevent="generateOAuthUrl">
        <ChoiceSelect v-model="oauthPlatform" label="授权平台" :options="platformOptions" :disabled="oauthLoading || !!oauthTarget" @update:model-value="oauthMode = 'oauth'" /><ChoiceSelect v-if="oauthPlatform === 'claude_code'" :model-value="oauthMode" @update:model-value="value => { if (value === 'oauth' || value === 'setup_token') oauthMode = value; }" label="授权方式" :disabled="oauthLoading" :options="[{value:'oauth',label:'OAuth'},{value:'setup_token',label:'Setup Token'}]" />
        <ProxyPicker v-model="oauthProxy" :current-label="oauthTarget?.proxy_name || publicProxy(oauthTarget?.proxy_url ?? '')"
          :disabled="oauthLoading" :help="oauthTarget ? '默认使用账号当前线路。重新选线后，授权成功时应用到该账号。' : '选择本次授权使用的代理，后续账号配置沿用此线路。'" />
        <p class="oauth-help">{{ oauthMode === 'oauth' ? '授权后支持账号信息与用量查询。' : 'Setup Token 仅用于推理，有效期 1 年。' }}</p>
        <NoticeStrip v-if="oauthError" tone="danger" class="oauth-error account-strip-text" role="alert">{{ oauthError }}</NoticeStrip>
      </form>
      <form v-else-if="oauthStep === 'exchange'" id="account-oauth-step" class="approved-oauth-body" @submit.prevent="exchangeOAuthCode">
        <EntityBlock class="oauth-link-panel"><a :href="oauthAuthUrl" target="_blank" rel="noopener noreferrer">点击打开授权页面 ↗</a><Button type="button" variant="outline" size="sm" @click="copyText(oauthAuthUrl)">复制链接</Button></EntityBlock>
        <details class="oauth-link-details"><summary>查看完整授权链接<ChevronRight :size="14" /></summary><Textarea :model-value="oauthAuthUrl" readonly :rows="3" aria-label="完整授权链接" /></details>
        <label class="approved-field"><span>授权码</span><Textarea v-model="oauthCode" :rows="3" autocomplete="off" spellcheck="false" :disabled="oauthLoading" placeholder="粘贴回调页面提供的授权码" /></label>
        <p class="oauth-help">在新页面完成 {{ oauthPlatform === 'antigravity' ? 'Google' : 'Claude' }} 登录授权，再将回调页面的授权码粘贴到这里。</p>
        <NoticeStrip v-if="oauthError" tone="danger" class="oauth-error account-strip-text" role="alert">{{ oauthError }}</NoticeStrip>
      </form>
      <section v-else-if="oauthResult" class="approved-oauth-body oauth-result">
        <NoticeStrip tone="success" class="oauth-success"><Check />授权成功 · {{ oauthResult.email_address || '账号信息已获取' }} · {{ oauthTarget ? '已保存到原账号' : '继续填写账号配置' }}</NoticeStrip>
        <EntityBlock><dl class="oauth-result-fields"><dt>授权方式</dt><dd>{{ oauthMode === 'oauth' ? 'OAuth' : 'Setup Token' }}</dd><dt>过期时间</dt><dd>{{ oauthResult.expires_at ? new Date(oauthResult.expires_at * 1000).toLocaleString('zh-CN') : '未提供' }}</dd></dl></EntityBlock>
        <details v-if="oauthPlatform === 'claude_code'" class="oauth-result-details"><summary>查看授权详情<ChevronRight :size="14" /></summary><dl class="oauth-result-fields"><dt>Account UUID</dt><dd>{{ oauthResult.account_uuid || '未提供' }}</dd><dt>Organization UUID</dt><dd>{{ oauthResult.organization_uuid || '未提供' }}</dd><dt>Scope</dt><dd>{{ oauthResult.scope || '未提供' }}</dd><dt>Access Token</dt><dd>已获取 <Button type="button" variant="outline" size="sm" aria-label="复制 Access Token" @click="copyText(oauthResult.access_token)">复制</Button></dd><template v-if="oauthResult.refresh_token"><dt>Refresh Token</dt><dd>已获取 <Button type="button" variant="outline" size="sm" aria-label="复制 Refresh Token" @click="copyText(oauthResult.refresh_token)">复制</Button></dd></template></dl></details>
      </section>
      <template #footer>
        <template v-if="oauthStep === 'generate'"><Button type="submit" form="account-oauth-step" class="oauth-primary" :disabled="oauthLoading">{{ oauthLoading ? '生成中…' : '生成授权链接' }}</Button></template>
        <template v-else-if="oauthStep === 'exchange'"><Button type="button" variant="outline" class="oauth-secondary" :disabled="oauthLoading" @click="restartOAuthFlow">返回</Button><Button type="submit" form="account-oauth-step" :disabled="oauthLoading || !oauthCode.trim()">{{ oauthLoading ? '授权中…' : '完成授权' }}</Button></template>
        <template v-else-if="oauthResult"><Button type="button" variant="outline" class="oauth-secondary" @click="showOAuthFlow = false">关闭</Button><Button type="button" @click="applyOAuthResult">{{ oauthTarget ? '完成' : '填入账号配置' }}</Button></template>
      </template>
    </ModalDialog>
  </div>

</template>
