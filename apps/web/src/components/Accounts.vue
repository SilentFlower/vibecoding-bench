<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { Pencil, RefreshCw, Activity, ArrowRight, Trash2, Globe, Box, Clock, ChevronRight, KeyRound, Plus, Check } from '@/components/ui/icon';
import { NumberInput, ChoiceSelect, SearchInput, InfoTooltip, Pagination } from '@/components/ui/controls';
import { useRoute } from 'vue-router';
import ProxyPicker from './ProxyPicker.vue';
import { api, type ProxyRoute, type Account, type OAuthExchangeResult, type UsageWindow, type RuntimeEnvironmentSummary } from '../api';
import UsageWindowStats from './UsageWindowStats.vue';
import SchedulingDetails from './SchedulingDetails.vue';
import { subscriptionLabel, fiveHourLabel } from '../lib/subscription';
import { schedulingReasonLabel } from '../lib/scheduling';
import { accountUpdateDelta } from '../lib/accountUpdate';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '../composables/useToast';
import { OperationFeedback, ConfirmationDialog } from './ui/feedback';

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
const accountCounts = ref<{total: number; active: number; error: number; disabled: number} | null>(null);
let searchTimer: ReturnType<typeof setTimeout> | undefined;
/** 筛选先重置分页，服务端负责全量匹配。@return 无。 */
function applyAccountFilter(): void { clearTimeout(searchTimer); currentPage.value = 1; void load(); }
watch(accountQuery, () => { clearTimeout(searchTimer); searchTimer = setTimeout(applyAccountFilter, 250); });
/** 选择状态后立即查询。@param value 状态。@return 无。 */
function chooseAccountFilter(value: string): void { accountFilter.value = value; applyAccountFilter(); }

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
/** 表单数据 */
const form = ref({
  name: '',
  email: '',
  auth_type: 'setup_token',
  setup_token: '',
  access_token: '',
  refresh_token: '',
  expires_at: '',
  proxy_url: '',
  billing_mode: 'strip',
  request_backend: 'legacy' as 'legacy' | 'native293',
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
/** 详情始终读取当前列表快照，列表刷新后不保留过期对象。 */
const detailAccountId = ref<number | null>(null);
const showAccountDetails = ref(false);
const workspaceTabs = [{value:'overview',label:'概览'},{value:'configuration',label:'配置'},{value:'scheduling',label:'调度'},{value:'diagnostics',label:'环境与诊断'}] as const;
const workspaceTab = ref<'overview' | 'configuration' | 'scheduling' | 'diagnostics'>('overview');
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
/** 在同一工作区切换，保留当前账号尚未提交的表单。@param tab 页签。@return 无。 */
function changeWorkspaceTab(tab: typeof workspaceTab.value): void {
  const account = detailAccount.value;
  if (!account) return;
  if (tab === 'configuration' && (!showForm.value || editing.value?.id !== account.id)) openEdit(account);
  if (tab === 'scheduling') schedulingAccount.value = account;
  workspaceTab.value = tab;
}

const detailAccount = computed(() => accounts.value.find(account => account.id === detailAccountId.value) ?? null);

/** 格式化当前调度模式的评分。@param account 账号调度快照。@return 带模式的紧凑评分文字。 */
function activeSchedulingScore(account: Account): string {
  const summary = account.v3_scheduling;
  if (summary) {
    return `智能评分 ${(summary.factors.score * 100).toFixed(1)}`;
  }
  return '评分待更新';
}
/** 打开账号完整信息。@param account 账号。@return 无。 */
function openAccountDetails(account: Account): void { detailAccountId.value = account.id; showAccountDetails.value = true; workspaceTab.value = 'overview'; }
/** 公开代理摘要只显示协议与主机，认证信息仅在配置中编辑。@param value 原始地址。@return 脱敏摘要。 */
function publicProxy(value: string): string { if (!value) return '直连'; try { const url = new URL(value); return `${url.protocol}//${url.host}`; } catch { return '代理地址待核对'; } }
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
let testAlive = true;
onUnmounted(() => { testAlive = false; for (const controller of testRequests.values()) controller.abort(); testRequests.clear(); });
/** 正在刷新用量的账号 ID */
const refreshingUsage = ref<number | null>(null);
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
      if (generation === accountLoadGeneration) { accounts.value = [account]; accountLoadFailed.value = false; }
      return;
    }
    const [res, overview] = await Promise.all([api.listAccounts(currentPage.value, pageSize.value, accountQuery.value.trim(), accountFilter.value === 'all' ? '' : accountFilter.value), api.getDashboard().catch(() => null)]);
    if (generation !== accountLoadGeneration) return;
    accountLoadFailed.value = false;
    accounts.value = res.data ?? [];
    if (overview) accountCounts.value = overview.accounts;
    profileSelectionMode.value = res.claude_code_profile_selection_mode ?? null;
    defaultVersionProfile.value = res.claude_code_version_profile ?? null;
    totalPages.value = res.total_pages;
    totalCount.value = res.total;
  } catch {
    // 读取失败不把原有负载伪装成空列表；旧快照保留并明确标记。
    if (generation === accountLoadGeneration) accountLoadFailed.value = true;
  } finally {
    if (generation === accountLoadGeneration) accountLoading = false;
  }
}

/** 页面恢复可见时立即更新，隐藏时不继续拉取。@return 无。 */
function refreshVisibleAccounts() {
  if (!document.hidden) void load();
}

/** 打开只读会话和发送视图。@param account 当前账号。@return 无。 */
function openScheduling(account: Account) {
  detailAccountId.value = account.id;
  workspaceTab.value = 'scheduling';
  schedulingAccount.value = account;
  showScheduling.value = true;
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
  proxyChoice.value = undefined;
  editing.value = null;
  form.value = {
    name: '',
    email: '',
    auth_type: 'setup_token',
    setup_token: '',
    access_token: '',
    refresh_token: '',
    expires_at: '',
    proxy_url: '',
    billing_mode: 'strip',
    request_backend: 'legacy' as 'legacy' | 'native293',
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
  proxyChoice.value = undefined;
  editing.value = a;
  form.value = {
    name: a.name,
    email: a.email,
    auth_type: a.auth_type || 'setup_token',
    setup_token: '',
    access_token: '',
    refresh_token: '',
    expires_at: a.expires_at ? String(a.expires_at) : '',
    proxy_url: a.proxy_url,
    billing_mode: a.billing_mode || 'strip',
    request_backend: a.request_backend ?? 'legacy',
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

/** 保存账号（新建或更新）。@return 保存完成后的空结果。 */
async function save() {
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
    if (editing.value) {
      if (form.value.auth_type === 'setup_token'
        && !form.value.setup_token.trim()
        && editing.value.auth_type !== 'setup_token') {
        throw new Error('切换到 Setup Token 模式时必须填写 Setup Token');
      }
      if (form.value.auth_type === 'oauth'
        && !form.value.refresh_token.trim()
        && editing.value.auth_type !== 'oauth') {
        throw new Error('切换到 OAuth 模式时必须填写 Refresh Token');
      }
      const updates = accountUpdateDelta(form.value, editBaseline.value);
      applyProxyChoice(updates);
      await api.updateAccount(editing.value.id, updates);
    } else {
      if (form.value.auth_type === 'setup_token' && !form.value.setup_token.trim()) {
        throw new Error('Setup Token 不能为空');
      }
      if (form.value.auth_type === 'oauth' && !form.value.refresh_token.trim()) {
        throw new Error('Refresh Token 不能为空');
      }
      const payload: Record<string, unknown> = {
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
      if (expiresAt) payload.expires_at = Number(expiresAt);
      applyProxyChoice(payload);
      await api.createAccount(payload);
    }
    if (props.workspaceAccountId) {
      emit('refresh');
      workspaceOpen.value = false;
    } else {
      workspaceOpen.value = false;
      await load();
      emit('refresh');
    }
  } catch (e: unknown) {
    toast((e as Error).message || '保存失败');
  }
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
    if (!testAlive || testRequests.get(id) !== controller) return;
    testStates.value.set(id, { status: result.status === 'ok' ? 'success' : 'error', message: result.message || (result.status === 'ok' ? '账号连接正常。' : '测试失败，请重试。') });
  } catch (cause) {
    if (!testAlive || controller.signal.aborted || testRequests.get(id) !== controller) return;
    testStates.value.set(id, { status: 'error', message: (cause as Error).message || '测试请求失败' });
  } finally {
    if (testRequests.get(id) === controller) testRequests.delete(id);
  }
}

/**
 * 刷新账号用量数据
 * @param id 账号 ID
 */
async function refreshUsage(id: number) {
  refreshingUsage.value = id;
  try {
    const res = await api.refreshUsage(id);
    if (res.status === 'ok' && res.usage) {
      // 官方 reset 可能已推进，立即重读后端汇总以同步切换费用窗口。
      await load();
    } else if (res.status === 'error') {
      toast(res.message || '刷新用量失败');
    }
  } catch (e: unknown) {
    toast((e as Error).message || '刷新用量失败');
  }
  refreshingUsage.value = null;
}

/**
 * 切换账号调度状态（启用/停用）
 * @param a 账号对象
 */
async function toggleScheduling(a: Account) {
  try {
    const isStopped = a.status === 'disabled' || isRateLimited(a);
    const newStatus = isStopped ? 'active' : 'disabled';
    const res = await api.updateAccount(a.id, { status: newStatus });
    a.status = res.status;
    a.disable_reason = res.disable_reason ?? '';
    a.rate_limited_at = res.rate_limited_at;
    a.rate_limit_reset_at = res.rate_limit_reset_at;
    emit('refresh');
  } catch (e: unknown) {
    toast((e as Error).message || '切换调度失败');
  }
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
 * 获取用量进度条颜色
 * @param pct 使用百分比 (0-100)
 */
function usageBarColor(pct: number): string {
  if (pct >= 80) return 'bg-red-400';
  if (pct >= 50) return 'bg-amber-400';
  return 'bg-emerald-400';
}

/**
 * 判断账号是否正在被限流
 */
function isRateLimited(a: Account): boolean {
  return !!(a.rate_limit_reset_at && new Date(a.rate_limit_reset_at) > new Date());
}

/**
 * 获取状态徽章样式
 */
function statusStyle(a: Account): { class: string; label: string } {
  if (a.status === 'active' && isRateLimited(a)) {
    // 短冷却(瞬时速率限制,秒级)与真正撞墙(5h/7d 限额)区分显示,避免误以为账号被长时间限流
    if ((a.disable_reason || '').includes('短冷却')) {
      return { class: 'bg-sky-50 text-sky-600 border-sky-200', label: '短冷却' };
    }
    return { class: 'bg-amber-50 text-amber-700 border-amber-200', label: '限流中' };
  }
  if (a.status === 'active') return { class: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: '活跃' };
  if (a.status === 'error') return { class: 'bg-red-50 text-red-600 border-red-200', label: '异常' };
  return { class: 'bg-gray-100 text-gray-500 border-gray-200', label: '停用' };
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
 * 获取 RPM 文本颜色。
 * @param account 账号对象
 */
function rpmClass(account: Account): string {
  if (account.v3_scheduling) return account.v3_scheduling.capacity.reason === 'pacing' ? 'text-amber-600' : 'text-foreground';
  if (!account.rpm_limit || account.rpm_limit <= 0) return 'text-muted-foreground';
  if (account.rpm_saturated) return 'text-red-500';
  const current = account.rpm_current ?? 0;
  const ratio = current / account.rpm_limit;
  if (ratio >= 0.8) return 'text-amber-600';
  return 'text-foreground';
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
 * 获取上游 session 池文本颜色。
 * @param account 账号对象
 */
function upstreamSessionPoolClass(account: Account): string {
  if (!account.upstream_session_pool_enabled || account.upstream_session_pool_size <= 0) return 'text-muted-foreground';
  const active = account.upstream_session_pool_active_count ?? 0;
  return active >= account.upstream_session_pool_size ? 'text-amber-600' : 'text-emerald-600';
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
 * 获取瞬时 429 软退避文本颜色。
 * @param account 账号对象
 */
function transientBackoffClass(account: Account): string {
  return ((account.transient_backoff_waiting ?? 0) > 0 || (account.transient_backoff_remaining_ms ?? 0) > 0)
    ? 'text-amber-600'
    : 'text-foreground';
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
 * 获取账号卡片并发文本颜色。
 * @param account 账号对象
 */
function concurrencyClass(account: Account): string {
  return (account.current_concurrency ?? 0) >= account.concurrency
    ? 'text-red-500'
    : 'text-foreground';
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
const oauthMode = ref<'oauth' | 'setup_token'>('oauth');
const oauthProxy = ref<ProxyRoute | null>(null);
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
watch(showOAuthFlow, value => {
  if (!value) { oauthGeneration++; oauthController?.abort(); oauthLoading.value = false; }
}, { flush:'sync' });
onUnmounted(() => { oauthGeneration++; oauthController?.abort(); });

/** 打开 OAuth 授权流程弹窗 */
function openOAuthFlow() {
  oauthGeneration++; oauthController?.abort(); oauthError.value = "";
  oauthMode.value = 'oauth';
  oauthProxy.value = null; oauthSessionProxy.value = null;
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
    const proxy = oauthProxy.value ? { proxy_id:oauthProxy.value.id, proxy_revision:oauthProxy.value.revision } : {};
    const result = oauthMode.value === 'oauth' ? await api.generateAuthUrl(proxy, signal) : await api.generateSetupTokenUrl(proxy, signal);
    if (current !== oauthGeneration || !showOAuthFlow.value) return;
    oauthSessionProxy.value = oauthProxy.value;
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
    oauthResult.value = result; oauthStep.value = 'done';
  } catch (cause) { if (current === oauthGeneration && !signal.aborted) oauthError.value = (cause as Error).message || '授权失败，请检查授权码'; }
  finally { if (current === oauthGeneration) oauthLoading.value = false; }
}

/** 将授权结果填入新建账号表单 */
function applyOAuthResult() {
  proxyChoice.value = oauthSessionProxy.value;
  const r = oauthResult.value;
  if (!r) return;
  showOAuthFlow.value = false;
  editing.value = null;
  const isSetupToken = oauthMode.value === 'setup_token';
  form.value = {
    name: '',
    email: r.email_address || '',
    auth_type: isSetupToken ? 'setup_token' : 'oauth',
    setup_token: isSetupToken ? r.access_token : '',
    access_token: isSetupToken ? '' : (r.access_token || ''),
    refresh_token: isSetupToken ? '' : (r.refresh_token || ''),
    expires_at: (!isSetupToken && r.expires_at) ? String(r.expires_at * 1000) : '',
    proxy_url: '',
    billing_mode: 'strip',
    request_backend: 'legacy' as 'legacy' | 'native293',
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
  <div class="space-y-4">
    <template v-if="!workspaceAccountId">
    <!-- 标题栏 -->
    <div class="page-heading">
      <div><p class="page-eyebrow">连接与调度</p><h2>账号管理</h2><p class="page-description">状态、用量和调度集中展示，常用操作直接可达。</p></div>
      <div class="flex gap-2">
        <Button
          @click="openOAuthFlow"
          variant="outline"
          class="account-authorize-button"
        >
          <KeyRound :size="15" />授权登录
        </Button>
        <Button
          @click="openCreate"
          class="bg-primary hover:bg-primary text-white font-medium rounded-xl transition-all duration-200 hover:shadow-md"
        >
          <Plus :size="15" />添加账号
        </Button>
      </div>
    </div>

    <div class="account-toolbar">
      <div class="account-filter-tabs" aria-label="账号筛选"><button v-for="item in [{value:'all', label:'全部账号', count:accountCounts?.total},{value:'active',label:'正常',count:accountCounts?.active},{value:'error',label:'需要关注',count:accountCounts?.error},{value:'disabled',label:'已停用',count:accountCounts?.disabled}]" :key="item.value" type="button" :class="{active:accountFilter===item.value}" :aria-pressed="accountFilter===item.value" @click="chooseAccountFilter(item.value)">{{ item.label }}<span>{{ item.count ?? '—' }}</span></button></div>
      <SearchInput v-model="accountQuery" label="搜索账号" placeholder="搜索名称或邮箱" :maxlength="256" @search="applyAccountFilter" />
    </div>

    <p v-if="accountLoadFailed" role="alert" class="text-xs text-amber-700">账号刷新失败，当前展示上次快照；负载与调度状态可能已陈旧。</p>
    <!-- 账号卡片列表 -->
    <div class="resource-grid account-card-grid">
      <Card
        v-for="a in accounts"
        :key="a.id"
        class="account-card"
      >
        <div class="account-card-body">
          <div class="account-identity">
            <span class="account-avatar">{{ (a.name || a.email || '?')[0]?.toUpperCase() }}<i class="account-avatar-state" :class="a.status" /></span>
            <button type="button" class="account-identity-text" @click="openAccountDetails(a)">
              <div><h3>{{ a.name || a.email }}<span class="account-plan">{{ subscriptionLabel(a.subscription_type, a.rate_limit_tier) }}</span></h3></div>
              <p>{{ a.email }}</p>
            </button>
            <button type="button" role="switch" class="account-status-switch" :aria-checked="!(a.status === 'disabled' || isRateLimited(a))" :aria-label="`${(a.status === 'disabled' || isRateLimited(a)) ? '启用' : '停用'} ${a.name || a.email}`" @click="toggleScheduling(a)"><span /></button>
          </div>
          <div class="account-network">
            <button type="button" @click="openEdit(a)"><Globe :size="13" /><span>{{ a.proxy_name || publicProxy(a.proxy_url) }}</span></button>
            <router-link :to="{ name: 'environments', query: { gateway_account: String(a.id) } }"><Box :size="13" />运行环境</router-link>
          </div>
          <div class="account-health" :class="a.status === 'disabled' ? 'is-disabled' : (isRateLimited(a) || a.auth_error || a.v3_scheduling_error) ? 'is-warning' : ''">
            <Check v-if="a.status !== 'disabled' && !isRateLimited(a) && !a.auth_error && !a.v3_scheduling_error" :size="13" /><i v-else />{{ a.status === 'disabled' ? '已停用' : a.v3_scheduling ? schedulingReasonLabel(a.v3_scheduling.capacity.reason) : statusStyle(a).label }}
            <span v-if="a.v3_scheduling">· {{ a.v3_scheduling.phases.running > 0 ? `正在处理 ${a.v3_scheduling.phases.running} 个请求` : '当前空闲' }}</span><button v-if="(a.queued_requests ?? 0)>0" class="account-queue-alert" @click="openScheduling(a)">排队 {{ a.queued_requests }}</button>
          </div>
          <p v-if="a.auth_error" role="alert" class="rounded-lg bg-red-50 p-3 text-xs text-red-700 break-words">{{ a.auth_error }}</p>
          <p v-if="a.v3_scheduling_error" class="text-xs text-amber-700">{{ a.v3_scheduling_error }}，调度观测待更新。</p>
          <p v-if="a.credential_ownership" class="text-xs text-muted-foreground" role="status">{{ a.credential_ownership.phase === 'ready' ? (a.credential_ownership.owner === 'local' ? '本地管理凭据 · 网关已暂停' : '网关管理凭据') : (a.credential_ownership.phase === 'reauth' ? '重新授权中 · 上游活动暂停' : '凭据交接待确认 · 请在账号环境页对账') }}</p>
          <div class="account-routing">
            <div><span>转发方式</span><strong><template v-if="a.request_backend === 'native293'">原生运行时 <small>280 / 293 自动匹配</small></template><template v-else>原有转发</template></strong></div>
            <button type="button" @click="openScheduling(a)">
              <span>调度优先级</span><strong>{{ a.priority }}<ArrowRight :size="13" /></strong>
              <small class="account-score">{{ activeSchedulingScore(a) }}</small>
            </button>
          </div>

          <section class="account-usage-windows">
            <header><span>用量</span><small>{{ a.usage_fetched_at ? new Date(a.usage_fetched_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) + ' 更新' : '未刷新' }}</small><button type="button" @click="refreshUsage(a.id)" :disabled="refreshingUsage === a.id" aria-label="刷新用量"><RefreshCw :size="12" />刷新</button></header>
            <p v-if="a.request_usage" class="usage-record-start">网关记录始于 {{ new Date(a.request_usage.recorded_since).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) }}</p>
            <div v-for="window in usageWindows" :key="window.key" class="account-usage-window">
              <UsageWindowStats v-if="window.key !== 'seven_day_fable'" :stats="a.request_usage?.[window.key]" :label="window.key === 'five_hour' ? '5h' : '7d'" />
              <div class="usage-window-label"><span>{{ window.label }}<template v-if="window.key !== 'seven_day_fable'"> · {{ a[window.key === 'five_hour' ? 'five_hour_usage_limit_percent' : 'seven_day_usage_limit_percent'] > 0 ? '上限 ' + a[window.key === 'five_hour' ? 'five_hour_usage_limit_percent' : 'seven_day_usage_limit_percent'] + '%' : '未限制' }}</template></span><strong>{{ window.key === 'five_hour' ? fiveHourLabel(a.usage_data, usagePercentLabel(usageWindow(a.usage_data, window.key))) : usagePercentLabel(usageWindow(a.usage_data, window.key)) }}</strong></div>
              <div class="usage-window-bar"><i :class="usageBarColor(effectiveUtil(usageWindow(a.usage_data, window.key)))" :style="{ width: Math.min(effectiveUtil(usageWindow(a.usage_data, window.key)), 100) + '%' }" /></div>
              <div v-if="hasFutureReset(usageWindow(a.usage_data, window.key))" class="usage-window-reset"><span>{{ formatTimeLeft(usageWindow(a.usage_data, window.key)?.resets_at) }} 后重置</span><span>{{ new Date(usageWindow(a.usage_data, window.key)!.resets_at!).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }}</span></div>
            </div>
          </section>
          <div class="account-live-metrics">
            <button type="button" @click="openScheduling(a)"><span>并发</span><strong :class="concurrencyClass(a)">{{ formatConcurrencySlots(a.current_concurrency) }}<small>/ {{ formatConcurrencySlots(a.concurrency) }}</small></strong><i class="metric-track"><i :style="{width:Math.min(100,(a.current_concurrency??0)/Math.max(1,a.concurrency)*100)+'%'}" /></i></button>
            <button type="button" @click="openScheduling(a)"><span>RPM</span><strong :class="rpmClass(a)">{{ a.v3_scheduling?.submissions_last_60s ?? a.rpm_current ?? 0 }}<small>/ {{ a.rpm_limit>0?a.rpm_limit:'∞' }}</small></strong><i class="metric-track"><i :style="{width:a.rpm_limit>0?Math.min(100,(a.v3_scheduling?.submissions_last_60s??a.rpm_current??0)/a.rpm_limit*100)+'%':'0%'}" /></i></button>
            <button type="button" @click="openScheduling(a)"><span>排队 <ChevronRight :size="12" /></span><strong :class="(a.queued_requests ?? 0) > 0 ? 'text-amber-600' : ''">{{ a.queued_requests ?? 0 }}</strong></button>
            <button type="button" @click="openScheduling(a)"><span>活跃会话</span><strong>{{ a.v3_scheduling?.active_sessions ?? '—' }}</strong></button>
          </div>

          <!-- 停用原因 -->
          <div
            v-if="a.disable_reason && (a.status === 'disabled' || (a.rate_limit_reset_at && new Date(a.rate_limit_reset_at) > new Date()))"
            class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border"
            :class="a.status === 'disabled' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'"
          >
            <span class="text-xs font-medium" :class="a.status === 'disabled' ? 'text-red-600' : 'text-amber-700'">
              {{ a.disable_reason }}
            </span>
            <span v-if="a.rate_limit_reset_at && new Date(a.rate_limit_reset_at) > new Date()" class="text-xs text-amber-500">
              · 剩余 {{ formatTimeLeft(a.rate_limit_reset_at) }}
            </span>
          </div>


        </div>
        <footer class="account-card-actions">
          <button type="button" @click="openEdit(a)"><Pencil :size="13" />编辑</button>
          <button type="button" @click="refreshUsage(a.id)" :disabled="refreshingUsage === a.id"><RefreshCw :size="13" />{{ refreshingUsage === a.id ? '刷新中' : '用量' }}</button>
          <OperationFeedback :status="testStates.get(a.id)?.status" :message="testStates.get(a.id)?.message" :identity="a.name" @action="test(a.id)" />
          <button type="button" @click="openAccountDetails(a)"><ArrowRight :size="13" />详情</button>
          <button type="button" @click="confirmDelete(a.id)" class="danger"><Trash2 :size="13" />删除</button>
        </footer>
      </Card>

      <!-- 空状态 -->
      <div
        v-if="accounts.length === 0"
        class="col-span-full flex flex-col items-center justify-center py-16 text-muted-foreground"
      >
        <div class="w-12 h-12 rounded-xl bg-muted flex items-center justify-center mb-3">
          <svg class="w-6 h-6 text-primary/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M18 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0ZM3 19.235v-.11a6.375 6.375 0 0 1 12.75 0v.109A12.318 12.318 0 0 1 9.374 21c-2.331 0-4.512-.645-6.374-1.766Z" />
          </svg>
        </div>
        <p class="text-sm">暂无账号，点击"添加账号"开始</p>
      </div>
    </div>

    <!-- 分页 -->
    <Pagination v-if="totalCount > 0" v-model:page-size="pageSize" class="account-pagination" :page="currentPage" :total="totalCount" :page-sizes="[12,24,48,96]" label="账号列表分页" unit="个账号" @update:page="goToPage" />



    </template>
    <!-- 新建/编辑账号弹窗 -->



    <Dialog v-model:open="workspaceOpen">
      <DialogContent class="account-workspace translate-x-0 translate-y-0" :class="{'account-workspace-wide': workspaceTab === 'configuration' || workspaceTab === 'scheduling'}">
        <DialogHeader><DialogTitle>{{ detailAccount?.name || detailAccount?.email || '添加账号' }}</DialogTitle><DialogDescription>{{ detailAccount?.email || '填写账号配置与认证信息' }}</DialogDescription></DialogHeader>
        <nav v-if="detailAccount" class="account-workspace-tabs" aria-label="账号工作区"><button v-for="tab in workspaceTabs" :key="tab.value" type="button" :class="{active:workspaceTab===tab.value}" :aria-pressed="workspaceTab===tab.value" @click="changeWorkspaceTab(tab.value)">{{ tab.label }}</button></nav>
        <div v-if="detailAccount" v-show="workspaceTab === 'overview'" class="account-workspace-scroll">
          <div class="account-overview-identity"><span class="account-avatar">{{ (detailAccount.name || detailAccount.email)[0] }}</span><div><strong>{{ detailAccount.name || detailAccount.email }}</strong><p>{{ detailAccount.email }}</p></div></div>
          <div class="account-overview-status">
            <span>{{ statusStyle(detailAccount).label }}</span>
            <small class="account-score">{{ activeSchedulingScore(detailAccount) }}</small>
          </div>
          <section class="account-usage-windows"><header><span>用量</span><small>{{ detailAccount.usage_fetched_at ? new Date(detailAccount.usage_fetched_at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}) + ' 更新' : '未刷新' }}</small></header>
            <div v-for="window in usageWindows" :key="window.key" class="account-usage-window"><UsageWindowStats v-if="window.key!=='seven_day_fable'" :stats="detailAccount.request_usage?.[window.key]" :label="window.key==='five_hour'?'5h':'7d'" /><div class="usage-window-label"><span>{{ window.label }}</span><strong>{{ usagePercentLabel(usageWindow(detailAccount.usage_data,window.key)) }}</strong></div><div class="usage-window-bar"><i :class="usageBarColor(effectiveUtil(usageWindow(detailAccount.usage_data,window.key)))" :style="{width:Math.min(100,effectiveUtil(usageWindow(detailAccount.usage_data,window.key)))+'%'}" /></div><p v-if="hasFutureReset(usageWindow(detailAccount.usage_data,window.key))" class="usage-window-reset">{{ formatTimeLeft(usageWindow(detailAccount.usage_data,window.key)?.resets_at) }} 后重置</p></div>
          </section>
          <dl class="account-overview-settings"><div><dt>订阅方案</dt><dd>{{ subscriptionLabel(detailAccount.subscription_type,detailAccount.rate_limit_tier) }}</dd></div><div><dt>并发上限</dt><dd>{{ detailAccount.concurrency }}</dd></div><div><dt>RPM 上限</dt><dd>{{ detailAccount.rpm_limit || '不限' }}</dd></div><div><dt>调度优先级</dt><dd>{{ detailAccount.priority }}</dd></div></dl>
          <div class="account-overview-actions">
            <OperationFeedback label="测试连接" button-variant="default" :status="testStates.get(detailAccount.id)?.status" :message="testStates.get(detailAccount.id)?.message" :identity="detailAccount.name || detailAccount.email" @action="test(detailAccount.id)" />
            <Button type="button" variant="outline" @click="refreshUsage(detailAccount.id)" :disabled="refreshingUsage === detailAccount.id"><RefreshCw :size="14" />{{ refreshingUsage === detailAccount.id ? '刷新中' : '刷新用量' }}</Button>
            <Button type="button" variant="ghost" @click="changeWorkspaceTab('scheduling')"><ArrowRight :size="14" />调度详情</Button>
            <Button v-if="detailAccount.status === 'disabled' || isRateLimited(detailAccount)" type="button" variant="outline" @click="toggleScheduling(detailAccount)">启用账号</Button>
            <Button v-else type="button" variant="destructive" class="account-stop-action" @click="toggleScheduling(detailAccount)">停用账号</Button>
          </div>
        </div>
        <form v-show="workspaceTab === 'configuration'" @submit.prevent="save" class="account-editor-form">
          <div class="account-editor-scroll complete-account-form">
            <section class="account-form-section"><h3>基础配置</h3><div class="account-edit-grid"><label class="approved-field"><span>备注名（选填）</span><Input v-model="form.name"  /></label><label class="approved-field"><span>邮箱</span><Input v-model="form.email" type="email" required /></label></div>
              <fieldset class="forwarding-field"><legend>转发方式</legend><div class="forwarding-options"><label><input type="radio" v-model="form.request_backend" value="native293"><span><strong>原生运行时</strong><small>280 / 293 自动匹配</small></span></label><label><input type="radio" v-model="form.request_backend" value="legacy"><span><strong>原有转发</strong><small>现有转发通道</small></span></label></div><p class="form-help">请在账号空闲时切换转发方式。</p></fieldset>
              <ProxyPicker v-model="proxyChoice" :current-label="editing?.proxy_name || publicProxy(form.proxy_url)" /></section>
            <section class="account-form-section"><h3>用量与调度</h3><div class="account-edit-grid three"><NumberInput v-model="numberDrafts.concurrency" label="并发上限" :min="1" required /><NumberInput v-model="numberDrafts.rpm_limit" label="RPM 上限" :min="0" required /><NumberInput v-model="numberDrafts.priority" label="调度优先级" :min="1" required /></div><div class="account-edit-grid"><NumberInput v-model="numberDrafts.five_hour_usage_limit_percent" label="5 小时用量上限（%）" :min="0" :max="100" required /><NumberInput v-model="numberDrafts.seven_day_usage_limit_percent" label="7 天用量上限（%）" :min="0" :max="100" required /></div><p class="form-help">RPM 和用量上限填 0 表示不限。达到任一用量上限后停止分配新消息，窗口重置后恢复。未知用量保持可用，单次或并发请求可能越线。</p></section>
            <section class="account-form-section"><h3>请求与模型</h3><div class="account-edit-grid"><ChoiceSelect v-model="form.billing_mode" label="Billing 模式" :options="[{value:'strip',label:'清除（Strip）'},{value:'rewrite',label:'重写（Rewrite）'}]" /><label class="approved-field"><span>允许 1M 上下文的模型</span><Input v-model="form.allow_1m_models"  /></label></div><div class="model-presets"><span>模型预设</span><button type="button" @click="form.allow_1m_models = 'opus'">仅 Opus</button><button type="button" @click="form.allow_1m_models = DEFAULT_ALLOW_1M_MODELS">Opus + Sonnet 5</button><button type="button" @click="form.allow_1m_models = ''">全部关闭</button></div><p class="form-help">模型以逗号分隔，按子串匹配。留空关闭 1M 上下文。Sonnet 5 使用完整名称以区分 Sonnet 4.6。</p>
              <label class="account-check"><span><strong>允许客户端 Fast Mode</strong><small>允许后保留客户端申请，可能增加计费和限流风险。</small></span><input type="checkbox" v-model="form.allow_fast_mode"></label><label class="account-check"><span><strong>自动遥测</strong><small>由网关代替客户端发送遥测请求。</small></span><input type="checkbox" v-model="form.auto_telemetry"></label><div v-if="form.auth_type==='oauth'"><label class="account-check"><span><strong>自动轮询用量</strong><small>后台定时拉取 OAuth 账号的用量数据。</small></span><input type="checkbox" v-model="form.auto_poll_usage"></label></div></section>
            <section class="account-form-section"><h3>上游 Session 池</h3><label class="account-check"><span><strong>启用 Session 池</strong><small>仅改写发往上游的会话；内部绑定、RPM 与本地缓存仍按真实会话隔离。</small></span><input type="checkbox" v-model="form.upstream_session_pool_enabled"></label><div class="account-edit-grid"><NumberInput v-model="numberDrafts.upstream_session_pool_size" label="池容量（0 表示关闭）" :min="0" :max="20" required /><NumberInput v-model="numberDrafts.upstream_session_ttl_minutes" label="活跃 TTL（分钟）" :min="5" :max="1440" required /></div><ChoiceSelect v-model="form.upstream_session_refresh_policy" label="TTL 刷新策略" :options="[{value:'mapped_request',label:'映射请求刷新'},{value:'owner_only',label:'仅属主刷新'}]" /></section>
            <details class="account-auth-fields account-advanced account-form-section" :open="!editing"><summary>认证与高级配置</summary><p class="form-help">认证通常由任务或工程创建流程提供。凭证留空保持原值；切换认证方式需要填写对应凭证。</p><ChoiceSelect v-model="form.auth_type" label="认证方式" :options="[{value:'oauth',label:'OAuth'},{value:'setup_token',label:'Setup Token'}]" /><div v-if="form.auth_type==='setup_token'"><label class="approved-field"><span>Setup Token</span><Input v-model="form.setup_token" type="password" autocomplete="new-password" :required="!editing" :placeholder="editing ? '留空保持不变' : 'sk-ant-oat01-...'" /></label></div><div v-else><div class="account-edit-grid"><label class="approved-field"><span>Access Token（选填）</span><Input v-model="form.access_token" type="password" autocomplete="new-password" placeholder="留空保持不变" /></label><label class="approved-field"><span>Refresh Token</span><Input v-model="form.refresh_token" type="password" autocomplete="new-password" :required="!editing" placeholder="留空保持不变" /></label></div><label class="approved-field"><span>过期时间（毫秒时间戳）</span><Input v-model="form.expires_at" inputmode="numeric" placeholder="留空清除到期时间" /></label><p v-if="editing?.expires_at" class="form-help">当前过期时间：{{ formatExpiresAt(editing.expires_at) }}</p><p v-if="editing?.auth_error" class="form-help text-red-600">最近认证错误：{{ editing.auth_error }}</p></div><div class="account-edit-grid"><ChoiceSelect :model-value="form.subscription_type" @update:model-value="selectSubscription" label="订阅类型" :options="[{value:'',label:'未设置'},{value:'max',label:'Max'},{value:'ultra',label:'Ultra'},{value:'pro',label:'Pro'},{value:'team',label:'Team'},{value:'enterprise',label:'Enterprise'}]" /><label class="approved-field"><span>官方分级</span><Input v-model="form.rate_limit_tier"  /></label></div><div class="account-edit-grid"><label class="approved-field"><span>Account UUID</span><Input v-model="form.account_uuid"  /></label><label class="approved-field"><span>Organization UUID</span><Input v-model="form.organization_uuid"  /></label></div><p class="form-help">修改订阅类型时清除旧分级，可填写新类型的官方分级。</p><Button type="button" variant="outline" @click="openOAuthFlow">重新授权</Button></details>
          </div>
          <DialogFooter class="account-save-footer"><span>修改后统一保存</span><Button type="button" variant="outline" @click="workspaceOpen = false">取消</Button><Button type="submit">保存修改</Button></DialogFooter>
        </form>
        <SchedulingDetails v-show="workspaceTab === 'scheduling'" embedded :open="workspaceOpen && workspaceTab === 'scheduling'" :account-id="detailAccount?.id ?? 0" :account-name="detailAccount?.name || detailAccount?.email || ''" />
        <div v-show="workspaceTab === 'diagnostics'" class="account-workspace-scroll account-diagnostics">
          <template v-if="detailAccount">
            <dl class="account-diagnostic-summary">
              <div><dt>账号运行环境</dt><dd>{{ diagnosticLoading ? '正在读取…' : diagnosticEnvironment ? (diagnosticEnvironmentStates[diagnosticEnvironment.state] || diagnosticEnvironment.state) : '未观测到关联环境' }}</dd></div>
              <div><dt>CLI 版本</dt><dd>{{ diagnosticEnvironment?.cli_versions?.join(' / ') || '未采集' }}</dd></div>
              <div><dt>请求内核</dt><dd>{{ diagnosticEnvironment?.native_kernel?.current?.release || '未采集' }}</dd></div>
              <div><dt>运行时段</dt><dd>{{ diagnosticEnvironment?.run_window?.message || '未提供' }}</dd></div>
            </dl>
            <p v-if="diagnosticError" class="account-diagnostic-error" role="alert">环境摘要读取失败：{{ diagnosticError }}</p>
            <div class="account-diagnostic-actions"><Button as-child variant="outline"><router-link :to="{name:'environments',query:{gateway_account:String(detailAccount.id)}}"><Box :size="15" />管理环境</router-link></Button><Button as-child variant="outline"><router-link :to="{name:'requests',query:{account:String(detailAccount.id)}}"><Activity :size="15" />请求诊断</router-link></Button><Button as-child variant="outline"><router-link :to="{name:'environments',query:{gateway_account:String(detailAccount.id),section:'schedule'}}"><Clock :size="15" />运行时段</router-link></Button></div>
          </template>
          <details class="account-diagnostic-technical"><summary>技术与调度详情</summary>
        <div v-if="detailAccount" class="account-detail-scroll space-y-5">
            <div class="grid grid-cols-5 gap-2">
              <div class="text-center"><span class="block text-[length:var(--ui-font-small)] text-muted-foreground">智能评分</span><strong class="text-sm font-medium">{{ detailAccount.v3_scheduling ? (detailAccount.v3_scheduling.factors.score * 100).toFixed(1) : '待更新' }}</strong></div>
              <InfoTooltip label="查看并发详情" title="并发与排队"><template #trigger><span class="block text-center"><span class="block text-[length:var(--ui-font-small)] text-muted-foreground">并发</span><strong class="text-sm font-medium" :class="concurrencyClass(detailAccount)">{{ concurrencyLabel(detailAccount) }}</strong></span></template><div class="account-score-explanation"><p>标准槽位 {{ formatConcurrencySlots(detailAccount.current_concurrency) }} / {{ formatConcurrencySlots(detailAccount.concurrency) }}</p><p>内部单位 {{ formatConcurrencyUnits(detailAccount.current_concurrency_units) }} / {{ formatConcurrencyUnits(detailAccount.max_concurrency_units) }}</p><p>活跃请求 {{ detailAccount.active_requests ?? 0 }} · 排队请求 {{ detailAccount.queued_requests ?? 0 }}</p><p>排队单位 {{ formatConcurrencyUnits(detailAccount.queued_request_units) }}</p><small>普通请求占用 1 并发，Haiku 占用 0.5 并发。</small></div></InfoTooltip>
              <div class="text-center">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider">排队</p>
                <p class="text-sm font-medium" :class="(detailAccount.queued_requests ?? 0) > 0 ? 'text-amber-600' : 'text-foreground'">
                  {{ detailAccount.queued_requests ?? 0 }}
                </p>
              </div>
              <div class="text-center">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider">429 等待</p>
                <p class="text-sm font-medium" :class="transientBackoffClass(detailAccount)">
                  {{ transientBackoffLabel(detailAccount) }}
                </p>
              </div>
              <div class="text-center">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider">{{ detailAccount.v3_scheduling ? '60秒提交 / RPM' : 'RPM' }}</p>
                <p class="text-sm font-medium" :class="rpmClass(detailAccount)">
                  {{ rpmLabel(detailAccount) }}
                </p>
              </div>
            </div>
            <div v-if="detailAccount.v3_scheduling" class="rounded-lg border border-border bg-muted p-3 space-y-2">
              <div class="flex justify-between items-center gap-2 text-xs"><span class="font-medium text-foreground">智能调度</span><span :class="detailAccount.v3_scheduling.capacity.immediate ? 'text-emerald-700' : 'text-amber-700'">{{ schedulingReasonLabel(detailAccount.v3_scheduling.capacity.reason) }}</span></div>
              <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground"><span>绑定 {{ detailAccount.v3_scheduling.bound_sessions }} 个会话</span><span>活跃 {{ detailAccount.v3_scheduling.active_sessions }} 个</span><span>执行 {{ detailAccount.v3_scheduling.phases.running }} 个请求</span></div>
              <p class="text-[length:var(--ui-font-small)] text-muted-foreground">等槽 {{ detailAccount.v3_scheduling.phases.waiting_concurrency }} · 准备 {{ detailAccount.v3_scheduling.phases.preparing }} · 等发 {{ detailAccount.v3_scheduling.phases.waiting_send }} · 退避 {{ detailAccount.v3_scheduling.phases.backoff }}</p>
              <div class="flex justify-between items-center"><span class="text-[length:var(--ui-font-small)] text-muted-foreground">{{ '智能偏好 ' + (detailAccount.v3_scheduling.factors.score * 100).toFixed(1) + '（高优）' }}</span><Button variant="outline" size="sm" class="text-xs h-7" @click="changeWorkspaceTab('scheduling')">调度详情</Button></div>
            </div>
            <div v-else-if="detailAccount.v3_scheduling_error" class="rounded-lg bg-amber-50 p-3 text-xs text-amber-700">{{ detailAccount.v3_scheduling_error }}，不代表零负载。<button class="underline ml-2" @click="changeWorkspaceTab('scheduling')">查看详情</button></div>
            <p class="text-xs text-muted-foreground">转发方式：{{ detailAccount.request_backend === 'native293' ? '原生运行时（280 / 293 自动匹配）' : '原有转发' }}</p>
            <div class="grid grid-cols-3 gap-3">
              <div class="text-center">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider">优先级</p>
                <p class="text-sm font-medium text-foreground">{{ detailAccount.priority }}</p>
              </div>
              <div class="text-center">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider">Billing</p>
                <p class="text-sm font-medium" :class="detailAccount.billing_mode === 'rewrite' ? 'text-amber-600' : 'text-foreground'">
                  {{ detailAccount.billing_mode === 'rewrite' ? '重写' : '清除' }}
                </p>
              </div>
              <div class="text-center">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider">上游池槽位</p>
                <p class="text-sm font-medium" :class="upstreamSessionPoolClass(detailAccount)">
                  {{ upstreamSessionPoolLabel(detailAccount) }}
                </p>
              </div>
            </div>
            <div class="account-detail-fields">
              <div>
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">代理</p>
                <p class="text-sm text-muted-foreground truncate">{{ publicProxy(detailAccount.proxy_url) }}</p>
              </div>
              <div>
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">认证方式</p>
                <p class="text-sm text-muted-foreground truncate">{{ authTypeLabel(detailAccount.auth_type) }}</p>
              </div>
              <div>
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">自动遥测</p>
                <p class="text-sm" :class="detailAccount.auto_telemetry ? 'text-emerald-600' : 'text-muted-foreground'">
                  {{ detailAccount.auto_telemetry ? '已开启' : '关闭' }}
                  <span v-if="detailAccount.telemetry_count > 0" class="text-muted-foreground text-xs">· 已发送 {{ detailAccount.telemetry_count }} 次</span>
                </p>
                <p v-if="detailAccount.telemetry_expires_at" class="text-xs text-amber-500 mt-0.5">
                  遥测中 · 停止于 {{ new Date(detailAccount.telemetry_expires_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }}
                </p>
              </div>
              <div v-if="detailAccount.upstream_session_pool_enabled && detailAccount.upstream_session_pool_size > 0">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">上游 Session 池</p>
                <p class="text-sm text-muted-foreground truncate">
                  TTL {{ detailAccount.upstream_session_ttl_minutes }} 分钟 · {{ upstreamSessionPolicyLabel(detailAccount.upstream_session_refresh_policy) }}
                </p>
              </div>
              <div v-if="detailAccount.auth_type === 'oauth'">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">自动轮询用量</p>
                <p class="text-sm" :class="detailAccount.auto_poll_usage ? 'text-emerald-600' : 'text-muted-foreground'">
                  {{ detailAccount.auto_poll_usage ? '已开启' : '关闭' }}
                </p>
              </div>
              <div>
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">
                  {{ detailAccount.auth_type === 'oauth' ? 'Refresh Token' : 'Setup Token' }}
                </p>
                <p class="font-mono text-[length:var(--ui-font-small)] text-muted-foreground truncate">{{ authSecretPreview(detailAccount) }}</p>
              </div>
              <div v-if="detailAccount.auth_type === 'oauth'">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">过期时间</p>
                <p class="text-sm text-muted-foreground truncate">{{ formatExpiresAt(detailAccount.expires_at) }}</p>
              </div>
              <div v-if="detailAccount.auth_type === 'oauth' && detailAccount.auth_error">
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">认证错误</p>
                <p class="text-xs text-red-500 line-clamp-2">{{ detailAccount.auth_error }}</p>
              </div>
              <div>
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">环境指纹</p>
                <p class="text-xs text-muted-foreground truncate">
                  {{ detailAccount.canonical_env?.platform || '—' }} / {{ detailAccount.canonical_env?.arch || '—' }}
                </p>
                <p class="text-xs text-muted-foreground mt-0.5">账号基础版本：v{{ detailAccount.canonical_env?.version || '—' }}</p>
              </div>
              <div>
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">画像选择方式</p>
                <p class="text-xs text-muted-foreground">
                  {{ profileSelectionMode === 'client_version' ? '按客户端 UA 适配' : profileSelectionMode === 'account' ? '使用账号画像' : '未提供画像配置' }}
                </p>
                <p v-if="profileSelectionMode === 'client_version' && defaultVersionProfile" class="text-xs text-muted-foreground mt-0.5">
                  默认回退：v{{ defaultVersionProfile }}（准入通过后）
                </p>
              </div>
              <div>
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">提示词环境</p>
                <p class="text-xs text-muted-foreground truncate">
                  {{ detailAccount.canonical_prompt_env?.platform || '—' }} · {{ detailAccount.canonical_prompt_env?.shell || '—' }} · {{ detailAccount.canonical_prompt_env?.working_dir || '—' }}
                </p>
              </div>
              <div>
                <p class="text-[length:var(--ui-font-small)] text-muted-foreground uppercase tracking-wider mb-0.5">进程指纹</p>
                <template v-if="detailAccount.canonical_process?.observation?.source === 'v3:procfs:cli'">
                  <p class="text-xs text-muted-foreground">
                    容器内存上限 {{ detailAccount.canonical_process.constrained_memory === 0 ? '不限' : formatBytes(detailAccount.canonical_process.constrained_memory, 2) }}
                  </p>
                  <p class="text-xs text-muted-foreground">
                    CLI RSS {{ detailAccount.canonical_process.observation.sample_count ? formatBytes(detailAccount.canonical_process.observation.rss_bytes ?? undefined, 2) : '未采集' }}
                  </p>
                  <p v-if="detailAccount.canonical_process.observation.sampled_at" class="text-[length:var(--ui-font-small)] text-muted-foreground">
                    官方 CLI 进程采样 · {{ new Date(detailAccount.canonical_process.observation.sampled_at * 1000).toLocaleString('zh-CN') }}
                  </p>
                </template>
                <p v-else class="text-xs text-muted-foreground truncate">内存 {{ formatBytes(detailAccount.canonical_process?.constrained_memory) }} · RSS {{ formatBytes(detailAccount.canonical_process?.rss_range?.[0]) }}–{{ formatBytes(detailAccount.canonical_process?.rss_range?.[1]) }}</p>
              </div>
            </div>
          </div>
          </details>
        </div>
      </DialogContent>
    </Dialog>

    <ConfirmationDialog :open="showDeleteConfirm" title="确认删除账号" message="此操作不可撤销，确认要删除此账号吗？" confirm-label="删除" danger :busy="deletingAccount" :error="deleteError" @confirm="executeDelete" @cancel="showDeleteConfirm=false" />

    <!-- 授权登录沿用定稿的紧凑表单，真实会话与凭据交接保持原接口。 -->
    <Dialog v-model:open="showOAuthFlow">
      <DialogContent class="account-oauth-dialog approved-oauth-dialog">
        <DialogHeader><DialogTitle>授权登录</DialogTitle><DialogDescription class="sr-only">通过浏览器授权接入账号</DialogDescription></DialogHeader>
        <div class="approved-oauth-body">
          <form v-if="oauthStep === 'generate'" @submit.prevent="generateOAuthUrl">
            <p class="oauth-context">将账号接入工作空间</p>
            <ChoiceSelect :model-value="oauthMode" @update:model-value="value => { if (value === 'oauth' || value === 'setup_token') oauthMode = value; }" label="授权方式" :disabled="oauthLoading" :options="[{value:'oauth',label:'OAuth'},{value:'setup_token',label:'Setup Token'}]" />
            <ProxyPicker v-model="oauthProxy" current-label="直连" :disabled="oauthLoading" help="选择本次授权使用的代理，后续账号配置沿用此线路。" />
            <p class="oauth-help">{{ oauthMode === 'oauth' ? '授权后支持账号信息与用量查询。' : 'Setup Token 仅用于推理，有效期 1 年。' }}</p>
            <p v-if="oauthError" class="oauth-error" role="alert">{{ oauthError }}</p>
            <footer class="oauth-actions"><Button type="submit" :disabled="oauthLoading">{{ oauthLoading ? '生成中…' : '生成授权链接' }}</Button></footer>
          </form>
          <form v-else-if="oauthStep === 'exchange'" @submit.prevent="exchangeOAuthCode">
            <p class="oauth-context">完成浏览器授权后，填写返回的授权码</p>
            <section class="oauth-link-panel"><a :href="oauthAuthUrl" target="_blank" rel="noopener noreferrer">点击打开授权页面 ↗</a><Button type="button" variant="outline" size="sm" @click="copyText(oauthAuthUrl)">复制链接</Button></section>
            <details class="oauth-link-details"><summary>查看完整授权链接</summary><Textarea :model-value="oauthAuthUrl" readonly :rows="3" aria-label="完整授权链接" /></details>
            <label class="approved-field"><span>授权码</span><Textarea v-model="oauthCode" :rows="3" autocomplete="off" spellcheck="false" :disabled="oauthLoading" placeholder="粘贴回调页面提供的授权码" /></label>
            <p class="oauth-help">在新页面完成 Claude 登录授权，再将回调页面的授权码粘贴到这里。</p>
            <p v-if="oauthError" class="oauth-error" role="alert">{{ oauthError }}</p>
            <footer class="oauth-actions"><Button type="button" variant="outline" :disabled="oauthLoading" @click="oauthStep = 'generate'; oauthError = ''">返回</Button><Button type="submit" :disabled="oauthLoading || !oauthCode.trim()">{{ oauthLoading ? '授权中…' : '完成授权' }}</Button></footer>
          </form>
          <section v-else-if="oauthResult" class="oauth-result">
            <p class="oauth-success">授权成功</p><p class="oauth-context">{{ oauthResult.email_address || '账号信息已获取' }} · 继续填写账号配置</p>
            <dl class="oauth-result-fields"><dt>授权方式</dt><dd>{{ oauthMode === 'oauth' ? 'OAuth' : 'Setup Token' }}</dd><dt>过期时间</dt><dd>{{ oauthResult.expires_at ? new Date(oauthResult.expires_at * 1000).toLocaleString('zh-CN') : '未提供' }}</dd></dl>
            <details class="oauth-result-details"><summary>查看授权详情</summary><dl class="oauth-result-fields"><dt>Account UUID</dt><dd>{{ oauthResult.account_uuid || '未提供' }}</dd><dt>Organization UUID</dt><dd>{{ oauthResult.organization_uuid || '未提供' }}</dd><dt>Scope</dt><dd>{{ oauthResult.scope || '未提供' }}</dd><dt>Access Token</dt><dd>已获取 <Button type="button" variant="outline" size="sm" aria-label="复制 Access Token" @click="copyText(oauthResult.access_token)">复制</Button></dd><template v-if="oauthResult.refresh_token"><dt>Refresh Token</dt><dd>已获取 <Button type="button" variant="outline" size="sm" aria-label="复制 Refresh Token" @click="copyText(oauthResult.refresh_token)">复制</Button></dd></template></dl></details>
            <footer class="oauth-actions"><Button type="button" variant="outline" @click="showOAuthFlow = false">关闭</Button><Button type="button" @click="applyOAuthResult">填入账号配置</Button></footer>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  </div>

</template>
