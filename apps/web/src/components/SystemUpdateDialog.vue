<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { ApiError, api, type SystemTuiReceipt, type SystemTuiReceiptPage, type SystemUpdateCatalog, type SystemUpdateControlProbe, type SystemUpdateRelease, type SystemUpdateRequest, type SystemUpdateStatus } from '../api';
import { formatLocalClock, formatLocalShort, formatLocalTime } from '../lib/time';
import { releaseNotes, releaseVersion } from '../lib/platformVersion';
import { UPDATE_PHASE_LABELS, databaseLabel, migrationStateLabel, snapshotLabel, updateSteps } from '../lib/updateSteps';
import { usePlatformVersion } from '../composables/usePlatformVersion';
import { useToast } from '../composables/useToast';
import { Button } from '@/components/ui/button';
import { NumberInput } from '@/components/ui/controls';
import { ConfirmationDialog } from '@/components/ui/feedback';
import { IconTile } from '@/components/ui/icon-tile';
import { ModalDialog } from '@/components/ui/modal';
import { NoticeStrip } from '@/components/ui/notice-strip';
import { AlertCircle, ArrowRight, ArrowUpCircle, Box, Check, ChevronDown, ChevronLeft, ChevronRight, Cpu, Download, History, Info, List, Pause, RefreshCw, RotateCcw, Server, Terminal, Users } from '@/components/ui/icon';

/**
 * 系统更新弹窗：版本概览与直接安装、按步骤的安装进度，以及版本记录、维护详情、操作详情三个二级视图。
 * 打开期间轮询更新状态，关闭即卸载并停止轮询。
 * v-model:open 控制弹窗开关；关闭后由外壳决定路由去向。
 */
const open = defineModel<boolean>('open', { default: false });

type Action = 'prepare' | 'install' | 'rollback' | 'recover';
type View = 'overview' | 'progress' | 'history' | 'maintenance' | 'details';
type RolloutState = NonNullable<SystemUpdateStatus['account_rollout']>['accounts'][number]['state'];
/** 一次冻结的写请求：网络结果不确定时整份重发，保持同一操作 ID 与等待期限。restart 为安装已下载的快速切换候选。 */
interface Frozen { action: Action; body: SystemUpdateRequest; accountChanged: boolean; label: string; sent: boolean; conflicted: boolean; confirm: boolean; restart: boolean }

const DEFAULT_DRAIN_MINUTES = 1;
const NODE_PHASES: Record<string, string> = { registering: '等待同步', checking: '核对组件', draining: '等待原工作完成', fenced: '原环境已停止', stopping: '停止原组件', backing_up: '备份资料', backed_up: '已停止，等待切换', switching: '切换组件', restoring: '恢复账号', completed: '同步完成', rolled_back: '已恢复原组件', rolling_back_control: '恢复原组件', platform_restoring: '恢复原组件', platform_restored: '恢复完成', waiting: '等待重试', needs_check: '等待核对' };
const ROLLOUT_STATES: Record<RolloutState, string> = { queued: '待更新', updating: '更新中', updated: '已更新', stopped: '保留启停状态', waiting: '等待空闲', needs_check: '待核对' };
const ROLLOUT_TONES: Record<RolloutState, string> = { queued: 'info', updating: 'info', updated: 'success', stopped: 'neutral', waiting: 'warning', needs_check: 'warning' };
const RECEIPT_STATES: Record<SystemTuiReceipt['state'], string> = {
  waiting: '原 V2 会话仍有活动',
  recoverable: '原会话已退出，可恢复',
  deferred: '该账号延期、平台可继续',
  binding_changed: '原账号或运行代次待核对',
  recovered: '原会话已退出，工具回执已收口',
  recovered_delivery_unknown: '工具回执已收口，原模型投递结果未知',
};
const CONTROL_CHECKS = { candidate: '新版本', restore: '恢复原版本' } as const;
const CONTROL_SERVICES = { gateway: '网关', orchestrator: '调度器' } as const;
const PROBE_STATES: Record<string, string> = { pending: '等待探测', ready: '就绪', timeout: '超时', http_error: '响应错误', connection_failed: '连接失败', invalid_response: '响应无效', request_failed: '探测失败' };
const RESTART_NOTICE = '重启会断开正在执行的推理。控制服务就绪后可重新请求。';

const toast = useToast();
const { version: runtimeVersion, refresh: refreshPlatformVersion } = usePlatformVersion();
const versionController = new AbortController();
const status = ref<SystemUpdateStatus | null>(null);
const catalog = ref<SystemUpdateCatalog | null>(null);
const error = ref('');
const loading = ref(true);
const writing = ref(false);
const checking = ref(false);
const failures = ref(0);
const notesOpen = ref(false);
const historyOpen = ref(false);
const expanded = ref('');
const planMinutes = ref<number | string>(DEFAULT_DRAIN_MINUTES);
const confirmMinutes = ref<number | string>(DEFAULT_DRAIN_MINUTES);
const frozen = ref<Frozen | null>(null);
const confirmOpen = ref(false);
/** 本次弹窗里观察到处于维护中的操作；结束后停在结局，直到用户点「完成」。 */
const followed = ref('');
const dismissedPrepared = ref('');
/** 二级视图的返回栈；为空时显示主视图。 */
const trail = ref<View[]>([]);
let alive = true;
let timer: ReturnType<typeof setTimeout> | undefined;
let controller: AbortController | undefined;
const receipts = ref<SystemTuiReceiptPage | null>(null);
const receiptAfter = ref('');
const receiptWriting = ref('');
const receiptError = ref('');
let receiptController: AbortController | undefined;

const progress = computed(() => status.value?.operation ?? null);
const download = computed(() => progress.value?.phase === 'preparing' ? progress.value.download_progress : null);
const downloadPercent = computed(() => {
  const current = download.value?.downloaded_bytes;
  const total = download.value?.total_bytes;
  return current != null && total != null && Number.isSafeInteger(current) && Number.isSafeInteger(total)
    && current >= 0 && total > 0 && current <= total ? Math.floor(current / total * 100) : undefined;
});
const downloadComponents = { control: '平台与网关镜像', account: '账号运行镜像', bundle: '离线镜像包' };
const downloadStates = { downloading: '下载中', cached: '使用本地缓存', loading: '正在解包', verifying: '正在校验' };
const byteFormat = new Intl.NumberFormat('zh-CN');
/** 将实际传输量换算成二进制容量。@param bytes 字节数。@return 带单位的容量。 */
function transferSize(bytes: number): string {
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 1 }) + ' ' + units[unit];
}
const progressRestart = computed(() => {
  const candidate = status.value?.prepared_candidate;
  const operation = progress.value;
  if (status.value?.busy || operation?.phase !== 'prepared' || candidate?.fast_transition !== true
    || candidate.operation_id !== operation.operation_id || candidate.target_release !== operation.target_release) return null;
  if (catalog.value?.fresh === false) return null;
  return catalog.value?.releases.find(release => release.release === candidate.target_release
    && release.manifest_sha256 === candidate.manifest_sha256 && release.data_compatible) ?? null;
});
const cancelAllowed = computed(() => !!status.value?.busy && ['preparing', 'draining'].includes(progress.value?.phase ?? ''));
const recoveryAllowed = computed(() => ['reconcile', 'succeeded_cleanup_pending'].includes(progress.value?.phase ?? ''));
const rollout = computed(() => status.value?.account_rollout ?? null);
const rolloutActive = computed(() => !!rollout.value?.accounts.some(item => item.state === 'queued' || item.state === 'updating'));
const mainView = computed<View>(() => {
  // 维护中与需要恢复的操作先于发布说明呈现；本次看着结束的操作停在结局。没有操作记录时只能显示概览。
  if (!progress.value) return 'overview';
  return status.value?.busy || recoveryAllowed.value || followed.value === progress.value.operation_id
    || (progressRestart.value && dismissedPrepared.value !== progress.value.operation_id) ? 'progress' : 'overview';
});
const view = computed<View>(() => trail.value[trail.value.length - 1] ?? mainView.value);
const runningEnvironments = computed(() => status.value?.environments?.filter(item => item.running).length ?? 0);
const environmentSources = computed(() => {
  const counts = new Map<string, number>();
  for (const item of status.value?.environments ?? []) {
    const source = item.verified ? item.release ?? '已停止，启动时使用所选镜像' : '来源待对账';
    counts.set(source, (counts.get(source) ?? 0) + 1);
  }
  return Array.from(counts, ([release, count]) => ({ release, count }));
});
const prominent = computed(() => (catalog.value?.releases ?? []).filter((release, index) => index === 0 || release.release === status.value?.current_release));
const older = computed(() => (catalog.value?.releases ?? []).filter(release => !prominent.value.includes(release)));
const displayed = computed(() => historyOpen.value ? [...prominent.value, ...older.value] : prominent.value);
const currentVersion = computed(() => {
  const installed = catalog.value?.releases.find(item => item.release === status.value?.current_release);
  return runtimeVersion.value ?? (installed ? releaseVersion(installed.changes) : null) ?? '历史构建';
});
/** 根据现有目录和现场显示检查结果，不用构建序号推断升级关系。 */
const latestRelease = computed(() => catalog.value?.releases[0]);
const installable = computed(() => !!latestRelease.value && latestRelease.value.release !== status.value?.current_release);
const preparedCandidate = computed(() => latestRelease.value ? preparedFor(latestRelease.value) : null);
const latestAction = computed<'prepare' | 'install'>(() => latestRelease.value ? updateAction(latestRelease.value) : 'install');
/** 最新版本已下载且支持快速切换：安装即重启，不再询问在途等待上限。 */
const restartReady = computed(() => latestAction.value === 'install' && !!preparedCandidate.value?.fast_transition);
const checkError = computed(() => catalog.value?.check_error ?? status.value?.check_error ?? '');
/** 从真实发布文本提取前三段概览，完整原文由「查看完整发布说明」展开。 */
const releaseHighlights = computed(() => releaseNotes(latestRelease.value?.changes ?? '').split(/\n\s*\n/).filter(part => part.trim()).slice(0, 3).map(part => {
  const lines = part.trim().split('\n');
  const heading = lines.length > 1 && (lines[0]?.length ?? 0) < 64;
  return { title: heading ? (lines[0] ?? '').replace(/^#{1,6}\s+/, '') : '', description: heading ? lines.slice(1).join('\n') : part.trim() };
}));
const summary = computed<{ text: string; tone: string }>(() => {
  if (status.value?.busy) return { text: '正在执行维护', tone: 'info' };
  if (checking.value || catalog.value?.checking) return { text: '正在检查更新', tone: 'info' };
  if (checkError.value) return { text: '检查遇到问题', tone: 'warning' };
  if (!catalog.value?.fresh) return { text: '等待检查版本', tone: 'neutral' };
  if (!latestRelease.value) return { text: '暂无可用发行', tone: 'neutral' };
  if (preparedCandidate.value) return { text: preparedCandidate.value.fast_transition ? '待重启' : '已下载更新', tone: 'success' };
  return installable.value ? { text: '有可用更新', tone: 'success' } : { text: '当前已是最新版本', tone: 'neutral' };
});
const installLabel = computed(() => writing.value && frozen.value && !frozen.value.confirm ? '正在登记…'
  : latestRelease.value ? updateButton(latestRelease.value, '安装更新') : '安装更新');
const installDisabled = computed(() => !status.value?.revision || !!status.value.busy || writing.value || !catalog.value?.fresh
  || !latestRelease.value?.data_compatible || !!(frozen.value && !frozen.value.confirm && frozen.value.conflicted));
const planLocked = computed(() => !!(frozen.value && !frozen.value.confirm && frozen.value.sent && frozen.value.body.target_release === latestRelease.value?.release));
const steps = computed(() => progress.value ? updateSteps(progress.value, {
  snapshot: !!status.value?.migration_capability,
  migrate: !!catalog.value?.releases.find(item => item.release === progress.value?.target_release)?.migrations?.length,
  busy: !!status.value?.busy,
}) : null);
const outcomeTone = computed(() => {
  const phase = steps.value?.outcome;
  if (phase === 'succeeded' || phase === 'prepared') return 'success';
  if (phase === 'failed') return 'danger';
  if (phase === 'cancelled') return 'neutral';
  return 'warning';
});
const progressPill = computed(() => {
  if (steps.value?.outcome) return { text: phaseLabel(steps.value.outcome), tone: outcomeTone.value };
  if (!status.value?.busy) return { text: phaseLabel(progress.value?.phase ?? ''), tone: 'info' };
  // 后台准备与中央恢复接单后的清理期间平台照常接单，标签与普通维护区分开。
  if (progress.value?.phase === 'preparing') return { text: '正在后台准备', tone: 'info' };
  if (progress.value?.phase === 'cleaning' && progress.value.admission_reopened_at) return { text: '平台已恢复接单', tone: 'success' };
  return { text: '更新中', tone: 'info' };
});
const maintenanceMessage = computed(() => {
  const operation = progress.value;
  if (!operation) return '';
  if (operation.phase === 'preparing') return '后台准备候选镜像与项目库，平台继续接单。';
  if (operation.phase === 'prepared') return '候选下载和校验已完成，平台继续接单。';
  if (operation.admission_reopened_at) return '平台已恢复接单。';
  if (operation.phase === 'draining') return operation.fast_transition
    ? '新请求暂缓。系统正在关闭旧推理连接，并等待资源释放。'
    : '新请求暂缓，等待在途工作结束。';
  return '正在切换或验收平台服务，新请求暂缓。';
});

/**
 * 当前操作的阶段中文名，未知阶段保持原值。快速切换的等待在途改称关闭推理连接；非快速候选下载完成称为已下载更新。
 * @param phase 原始阶段。@return 文案。
 */
function phaseLabel(phase: string): string {
  if (phase === 'draining' && progress.value?.fast_transition) return '正在关闭推理连接';
  if (phase === 'prepared' && !progress.value?.fast_transition) return '已下载更新';
  return UPDATE_PHASE_LABELS[phase] ?? phase;
}

/** 格式化最近一次健康探测。@param probe 已记录的服务探测。@return 「状态 · HTTP 码 · 耗时 · 第 N 次」。 */
function probeResult(probe: SystemUpdateControlProbe): string {
  return [PROBE_STATES[probe.state] ?? probe.state, probe.http_status && `HTTP ${probe.http_status}`,
    probe.duration_ms != null && `${(probe.duration_ms / 1000).toFixed(2)} 秒`,
    probe.attempts > 0 && `第 ${probe.attempts} 次`].filter(Boolean).join(' · ');
}

/** 核对该发行的下载回执：目标与清单摘要都一致才算。@param release 受信发行。@return 回执或空。 */
function preparedFor(release: SystemUpdateRelease) {
  const prepared = status.value?.prepared_candidate;
  return prepared && prepared.target_release === release.release && prepared.manifest_sha256 === release.manifest_sha256 ? prepared : null;
}

/** 依目标与宿主回执选择下一步：支持分步更新且尚未下载时先下载。@param release 受信发行。@return 写动作。 */
function updateAction(release: SystemUpdateRelease): 'prepare' | 'install' {
  return status.value?.staged_updates && !preparedFor(release) ? 'prepare' : 'install';
}

/** 目标版本下一步操作的按钮文字。@param release 受信发行。@param legacy 旧底座的安装文案。@return 按钮文字。 */
function updateButton(release: SystemUpdateRelease, legacy: string): string {
  if (catalog.value?.fresh === false) return '先检查更新';
  if (!release.data_compatible) return '待验证兼容';
  if (updateAction(release) === 'prepare') return '下载更新';
  const prepared = preparedFor(release);
  return prepared?.fast_transition ? '立即重启' : prepared ? '安装更新' : legacy;
}

/** 使用受信版本标题；旧来源保留历史构建语义。@param id 原发行身份。@return 人类可读版本。 */
function releaseLabel(id: string): string {
  const release = catalog.value?.releases.find(item => item.release === id);
  if (release) return releaseVersion(release.changes) ?? `历史构建 · ${formatLocalTime(release.published_at)}`;
  return id === status.value?.current_release ? currentVersion.value : '历史构建';
}

/** 显示受信发布说明的首段摘要。@param release 完整发行摘要。@return 短说明。 */
function releaseSummary(release: SystemUpdateRelease): string { return releaseNotes(release.changes).split('\n')[0] ?? ''; }

/** 操作 ID 的紧凑写法，完整值放在 title。@param id UUID。@return 前 8 位…后 4 位。 */
function shortId(id: string): string { return id.length > 14 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id; }

/** 进入二级视图。@param next 目标视图。@return 无。 */
function enter(next: View): void { trail.value = [...trail.value, next]; }

/** 返回上一层视图。@return 无。 */
function back(): void { trail.value = trail.value.slice(0, -1); }

/** 结束结局展示回到概览。@return 无。 */
function finish(): void {
  if (progress.value?.phase === 'prepared') dismissedPrepared.value = progress.value.operation_id;
  followed.value = '';
  trail.value = [];
}

/** 版本列表只保留一个详情展开。@param id 当前条目标识。@return 无。 */
function toggleDetails(id: string): void { expanded.value = expanded.value === id ? '' : id; }

/** 为安全和普通 HTTP 环境生成 UUID。@return 规范 UUID。 */
function operationId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 15) | 64;
  bytes[8] = (bytes[8]! & 63) | 128;
  const text = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  return `${text.slice(0, 8)}-${text.slice(8, 12)}-${text.slice(12, 16)}-${text.slice(16, 20)}-${text.slice(20)}`;
}

/** 读取缓存状态并串行安排下一次轮询。@return 本轮读取完成。 */
async function refresh(): Promise<void> {
  if (!alive) return;
  clearTimeout(timer);
  if (controller) return;
  controller = new AbortController();
  const signal = controller.signal;
  void refreshPlatformVersion(versionController.signal);
  try {
    const current = await api.systemUpdateStatus(signal);
    const available = current.installed ? await api.systemUpdateReleases(signal) : null;
    if (!alive) return;
    status.value = current;
    catalog.value = available;
    if (current.installed) void loadReceipts(receiptAfter.value);
    if (current.busy && current.operation) followed.value = current.operation.operation_id;
    error.value = '';
    failures.value = 0;
  } catch (cause) {
    if (!alive || signal.aborted) return;
    failures.value += 1;
    error.value = status.value?.busy ? '平台正在切换，正在重新连接…'
      : cause instanceof Error ? cause.message : '系统更新状态暂不可用';
  } finally {
    controller = undefined;
    if (alive) {
      loading.value = false;
      timer = setTimeout(refresh, failures.value ? Math.min(30000, 2000 * 2 ** Math.min(failures.value, 4))
        : status.value?.busy || catalog.value?.checking || rolloutActive.value ? 2000 : 10000);
    }
  }
}

/** 手动检查只更新提示。@return 检查入队完成。 */
async function check(): Promise<void> {
  if (checking.value || writing.value) return;
  checking.value = true;
  try {
    await api.systemUpdateCheck();
    toast.show('正在检查受信版本', 'success');
    await refresh();
  } catch (cause) {
    toast.show(cause instanceof Error ? cause.message : '检查版本失败');
  } finally {
    checking.value = false;
  }
}

/**
 * 冻结现场与目标。恢复沿用原操作 ID，其余动作生成新 ID；安装已下载的候选时带上下载操作 ID。
 * @param action 动作。@param release 目标发行。@param digest 清单摘要。@param accountChanged 是否影响账号环境。@param confirm 是否经二次确认框。
 * @return 冻结请求；现场未就绪时为空。
 */
function freeze(action: Action, release: string, digest: string, accountChanged: boolean, confirm: boolean): Frozen | null {
  if (!status.value?.revision) return null;
  const candidate = status.value.prepared_candidate;
  const prepared = action === 'install' && candidate?.target_release === release && candidate.manifest_sha256 === digest ? candidate : null;
  return { action, accountChanged, confirm, sent: false, conflicted: false, restart: prepared?.fast_transition === true, label: releaseLabel(release), body: {
    operation_id: action === 'recover' ? progress.value!.operation_id : operationId(), expected_revision: status.value.revision,
    target_release: release, target_manifest_sha256: digest, drain_timeout_seconds: DEFAULT_DRAIN_MINUTES * 60,
    ...(prepared && { prepared_operation_id: prepared.operation_id }) } };
}

/** 提交冻结请求，网络不确定时保留同一个操作 ID。@param minutes 等待上限（分钟）。@return 本次提交完成。 */
async function submit(minutes: number | string): Promise<void> {
  const selected = frozen.value;
  if (!selected || writing.value || selected.conflicted) return;
  // 下载期间平台继续接单，快速切换的重启不等在途；两者与恢复都不询问期限，保持冻结时的默认值。
  const askWait = selected.action !== 'recover' && selected.action !== 'prepare' && !selected.restart;
  const wait = Number(minutes);
  if (askWait && (!Number.isInteger(wait) || wait < 1 || wait > 120)) {
    toast.show('等待期限应为 1～120 分钟');
    return;
  }
  if (!selected.sent && askWait) {
    // 首次发送前才采用当前期限；之后锁定，重试保持整份冻结参数。
    selected.body.drain_timeout_seconds = wait * 60;
  }
  writing.value = true;
  selected.sent = true;
  try {
    const operation = selected.action === 'recover'
      ? await api.systemUpdateControl(selected.body.operation_id, 'recover', selected.body.expected_revision)
      : await api.systemUpdateInstall(selected.action, selected.body);
    if (!alive) return;
    frozen.value = null;
    confirmOpen.value = false;
    followed.value = operation.operation_id;
    trail.value = [];
    toast.show(selected.action === 'prepare' ? '已开始下载更新' : '操作已登记', 'success');
    await refresh();
  } catch (cause) {
    if (!alive) return;
    selected.conflicted = cause instanceof ApiError && cause.status === 409;
    toast.show(cause instanceof Error ? cause.message : '提交结果待核对，请重试同一操作');
  } finally {
    if (alive) writing.value = false;
  }
}

/**
 * 不经二次确认直接提交：概览的安装方式即确认，版本记录里的下载也直接开始。
 * 动作、目标或下载回执不变时重发同一冻结，否则重新冻结。
 * @param release 目标发行。@return 提交完成。
 */
async function submitDirect(release: SystemUpdateRelease): Promise<void> {
  const action = updateAction(release);
  const prepared = action === 'install' ? preparedFor(release) : null;
  const current = frozen.value;
  if (!current || current.confirm || current.action !== action || current.body.target_release !== release.release
    || current.body.target_manifest_sha256 !== release.manifest_sha256
    || current.body.prepared_operation_id !== prepared?.operation_id) {
    frozen.value = freeze(action, release.release, release.manifest_sha256, release.account_changed, false);
  }
  await submit(planMinutes.value);
}

/** 直接安装（或下载、重启）最新版本。@return 提交完成。 */
async function installLatest(): Promise<void> {
  const latest = latestRelease.value;
  if (!latest || installDisabled.value) return;
  await submitDirect(latest);
}

/** 版本记录里的安装：需要先下载时直接开始下载，其余先二次确认。@param release 目标发行。@return 无。 */
function installRelease(release: SystemUpdateRelease): void {
  if (writing.value || status.value?.busy) return;
  if (updateAction(release) === 'prepare') void submitDirect(release);
  else confirm('install', release.release, release.manifest_sha256, release.account_changed);
}

/** 回退、版本记录中的安装与恢复先打开二次确认。@param action 动作。@param release 目标。@param digest 摘要。@param accountChanged 环境影响。@return 无。 */
function confirm(action: Action, release: string, digest: string, accountChanged = true): void {
  if (writing.value || (status.value?.busy && action !== 'recover')) return;
  const selected = freeze(action, release, digest, accountChanged, true);
  if (!selected) return;
  confirmMinutes.value = DEFAULT_DRAIN_MINUTES;
  frozen.value = selected;
  confirmOpen.value = true;
}

/** 二次确认框标题。@param selected 冻结请求。@return 标题。 */
function confirmTitle(selected: Frozen): string {
  if (selected.action === 'recover') return '恢复本次操作';
  if (selected.action === 'rollback') return '确认版本回退';
  return selected.restart ? '重启并切换版本' : '确认安装更新';
}

/** 关闭二次确认，提交中保持。@return 无业务写入。 */
function closeConfirm(): void {
  if (writing.value) return;
  confirmOpen.value = false;
  frozen.value = null;
}

/** 取消安全阶段的等待。@return 原操作收口请求完成。 */
async function cancel(): Promise<void> {
  if (!cancelAllowed.value || !status.value?.revision || !progress.value || writing.value) return;
  writing.value = true;
  try {
    await api.systemUpdateControl(progress.value.operation_id, 'cancel', status.value.revision);
    if (!alive) return;
    toast.show('已请求取消，正在核对原版本', 'success');
    await refresh();
  } catch (cause) {
    if (alive) toast.show(cause instanceof Error ? cause.message : '取消结果待核对');
  } finally {
    writing.value = false;
  }
}

/** 重新排队一个账号的后台更新。@param environmentId 该账号的运行环境。@return 提交完成。 */
async function retryAccount(environmentId: string): Promise<void> {
  if (!rollout.value || !status.value?.revision || status.value.busy || writing.value) return;
  writing.value = true;
  try {
    await api.systemUpdateRetryAccount(rollout.value.operation_id, environmentId, status.value.revision);
    if (alive) await refresh();
  } catch (cause) {
    if (alive) toast.show(cause instanceof Error ? cause.message : '账号重试提交失败');
  } finally {
    writing.value = false;
  }
}

/** 独立读取回执，失联时版本状态和安装操作可以继续刷新。@param after 页游标。@param replace 操作完成后重新读取。@return 本轮读取结束。 */
async function loadReceipts(after: string, replace = false): Promise<void> {
  if (receiptController && after === receiptAfter.value && !replace) return;
  receiptController?.abort();
  const request = new AbortController();
  receiptController = request;
  receiptAfter.value = after;
  try {
    const page = await api.systemTuiReceipts(after, request.signal);
    if (alive && !request.signal.aborted) {
      receipts.value = page;
      receiptError.value = '';
    }
  } catch (cause) {
    if (alive && !request.signal.aborted) receiptError.value = '工具回执状态暂不可用';
  } finally {
    if (receiptController === request) receiptController = undefined;
  }
}

/** 立即核对单条回执。@param receipt 当前可见回执。@return 操作结果已展示。 */
async function recoverReceipt(receipt: SystemTuiReceipt): Promise<void> {
  if (receiptWriting.value || status.value?.busy) return;
  receiptWriting.value = receipt.id;
  try {
    const result = await api.systemTuiReceiptRecover(receipt);
    if (!alive) return;
    toast.show(RECEIPT_STATES[result.state]);
    if (result.state === 'recovered' || result.state === 'recovered_delivery_unknown') {
      const pending = rollout.value?.accounts.find(item => item.gateway_account_id === receipt.account_id
        && item.state === 'waiting' && item.retryable !== false);
      if (pending) await retryAccount(pending.environment_id);
    }
  } catch (cause) {
    if (alive) toast.show(cause instanceof Error ? cause.message : '工具回执核对失败');
  } finally {
    receiptWriting.value = '';
    if (alive) void loadReceipts(receiptAfter.value, true);
  }
}

/** 恢复连接并读取当前现场。@return 初始化完成。 */
async function connect(): Promise<void> {
  try {
    await api.openRuntime();
    await refresh();
  } catch (cause) {
    if (alive) {
      error.value = cause instanceof Error ? cause.message : '连接更新服务失败';
      loading.value = false;
    }
  }
}

onMounted(connect);
onUnmounted(() => { alive = false; clearTimeout(timer); controller?.abort(); receiptController?.abort(); versionController.abort(); });
</script>

<template>
  <ModalDialog v-model:open="open" title="系统更新" description="检查版本、阅读发布说明，选择合适的时间安装。" :width="768" class="system-update-dialog">
    <template #media><IconTile tone="success" size="lg" class="su-head-icon"><ArrowUpCircle /></IconTile></template>

    <NoticeStrip v-if="error" tone="warning" role="alert"><AlertCircle />{{ error }}</NoticeStrip>
    <p v-if="loading" class="su-empty">正在读取系统版本…</p>
    <!-- 未接入底座，或更新服务暂不可用（只显示当前版本，错误见上方提示条）。 -->
    <section v-else-if="!status?.installed" class="su-section" data-update-view="uninstalled">
      <template v-if="status">
        <div class="su-head"><div><small>flower2api</small><h3>首次接入系统更新</h3></div></div>
        <p class="su-text">{{ status.message }}</p>
        <p class="su-text">接入独立更新服务及维护底座后，即可安装后续版本。</p>
      </template>
      <p class="su-text">当前版本：{{ currentVersion }}</p>
    </section>

    <template v-else-if="status?.installed">
      <!-- 概览：版本、发布说明与安装方式。 -->
      <div v-if="view === 'overview'" class="su-view" data-update-view="overview">
        <section class="su-section">
          <div class="su-head"><div><small>flower2api</small><h3>平台与网关镜像</h3></div><span class="su-pill" :data-tone="summary.tone" role="status"><ArrowUpCircle v-if="summary.tone === 'success'" />{{ summary.text }}</span></div>
          <div class="su-tiles">
            <div data-update-tile="current"><span>当前版本</span><b :title="currentVersion">{{ currentVersion }}</b></div>
            <div data-update-tile="latest"><span>最新版本</span><b>{{ latestRelease ? releaseLabel(latestRelease.release) : '等待检查' }}</b></div>
            <div data-update-tile="published"><span>发布于</span><b :title="latestRelease ? formatLocalTime(latestRelease.published_at) : undefined">{{ latestRelease ? formatLocalShort(latestRelease.published_at) : '—' }}</b></div>
            <div data-update-tile="checked"><span>最近检查</span><b :title="catalog?.checked_at ? formatLocalTime(catalog.checked_at) : undefined">{{ catalog?.checked_at ? formatLocalShort(catalog.checked_at) : '尚未检查' }}</b></div>
          </div>
          <NoticeStrip v-if="!catalog?.fresh" tone="neutral"><Info />版本目录待刷新</NoticeStrip>
          <NoticeStrip v-else-if="latestRelease && !latestRelease.data_compatible" tone="warning"><AlertCircle />兼容性待核对 · {{ latestRelease.compatibility_reason === 'migration_evidence_missing' ? '此来源版本的升级与回退演练证据待发布端补齐。' : '此版本的数据兼容声明待发布端验证。' }}</NoticeStrip>
          <NoticeStrip v-else-if="latestRelease" tone="success"><Check />兼容性检查通过{{ status.migration_capability ? ' · 安装前自动保存平台与网关数据库快照' : '' }}</NoticeStrip>
          <NoticeStrip v-if="checkError" tone="warning" role="status"><AlertCircle />{{ checkError }}</NoticeStrip>
        </section>

        <section class="su-section">
          <div class="su-head"><h4>发布说明</h4><span v-if="latestRelease" class="su-mono">{{ releaseLabel(latestRelease.release) }}</span></div>
          <template v-if="latestRelease">
            <ul v-if="releaseHighlights.length" class="su-notes"><li v-for="(highlight, index) in releaseHighlights" :key="index"><b v-if="highlight.title">{{ highlight.title }}</b><span v-if="highlight.description">{{ highlight.description }}</span></li></ul>
            <p v-else class="su-text">该发行未提供额外说明。</p>
            <button type="button" class="su-link" :aria-expanded="notesOpen" aria-controls="latest-release-notes" @click="notesOpen = !notesOpen">{{ notesOpen ? '收起完整发布说明' : '查看完整发布说明' }}<ArrowRight /></button>
            <div v-if="notesOpen" id="latest-release-notes" class="su-full-notes" data-release-details>{{ releaseNotes(latestRelease.changes) }}</div>
          </template>
          <p v-else class="su-text">等待检查可用版本</p>
        </section>

        <!-- 安装方式按下一步动作切换：先下载（继续接单）/ 立即重启（不问等待上限）/ 兼容安装（暂停接单并等待在途）。 -->
        <section v-if="installable && latestRelease" class="su-section su-plan" :data-update-plan="latestAction === 'prepare' ? 'prepare' : restartReady ? 'restart' : 'install'">
          <template v-if="latestAction === 'prepare'">
            <IconTile tone="info" class="su-plan-icon"><Download /></IconTile>
            <div class="su-plan-copy"><b>先在后台下载并校验</b><p>平台继续接单；下载完成后再选择重启时间。刷新页面或更新器重启后仍可继续。</p></div>
          </template>
          <template v-else-if="restartReady">
            <IconTile tone="info" class="su-plan-icon"><RotateCcw /></IconTile>
            <div class="su-plan-copy"><b>重启并切换版本</b><p>{{ RESTART_NOTICE }}</p></div>
          </template>
          <template v-else>
            <IconTile tone="info" class="su-plan-icon"><Pause /></IconTile>
            <div class="su-plan-copy"><b>安装时暂停新接单</b><p>等待在途工作结束后切换平台服务；{{ latestRelease.account_changed ? `预计更新 ${runningEnvironments} 个运行环境，已停止环境保留原状态。` : `${runningEnvironments} 个账号运行环境运行中，兼容的运行环境继续复用。` }}</p></div>
            <div class="su-plan-minutes"><NumberInput v-model="planMinutes" label="在途等待上限（分钟）" :min="1" :max="120" :disabled="planLocked" :invalid="!Number.isInteger(Number(planMinutes)) || Number(planMinutes) < 1 || Number(planMinutes) > 120" /></div>
          </template>
        </section>
        <NoticeStrip v-if="frozen && !frozen.confirm && frozen.conflicted" tone="warning" role="alert"><AlertCircle />现场版本已经变化，请关闭窗口并刷新后重新选择。</NoticeStrip>

        <NoticeStrip v-if="progress" :tone="progress.phase === 'succeeded' || progress.phase === 'prepared' ? 'success' : progress.phase === 'failed' ? 'danger' : progress.phase === 'cancelled' ? 'neutral' : 'warning'" class="su-last">
          <History />上次操作 · {{ phaseLabel(progress.phase) }} · {{ releaseLabel(progress.target_release) }} · {{ formatLocalShort(progress.updated_at) }}
          <template #end><Button variant="link" size="sm" @click="enter('progress')">查看记录</Button></template>
        </NoticeStrip>
      </div>

      <!-- 进度：按步骤推进，结局沿用阶段文案。 -->
      <div v-else-if="view === 'progress' && progress && steps" class="su-view" data-update-view="progress" aria-live="polite">
        <section class="su-section">
          <div class="su-head"><div><small>flower2api</small><h3>平台与网关镜像</h3></div><span class="su-pill" :data-tone="progressPill.tone"><RefreshCw v-if="status.busy && !steps.outcome" class="animate-spin motion-reduce:animate-none" />{{ progressPill.text }}</span></div>
          <div class="su-tiles">
            <div data-update-tile="current"><span>当前版本</span><b :title="currentVersion">{{ currentVersion }}</b></div>
            <div data-update-tile="target"><span>目标版本</span><b :title="progress.target_release">{{ releaseLabel(progress.target_release) }}</b></div>
            <div data-update-tile="operation"><span>操作 ID</span><b :title="progress.operation_id">{{ shortId(progress.operation_id) }}</b></div>
            <div data-update-tile="updated"><span>最近更新</span><b :title="formatLocalTime(progress.updated_at)">{{ formatLocalClock(progress.updated_at) }}</b></div>
          </div>
          <NoticeStrip v-if="(status.busy && !steps.outcome) || progress.admission_reopened_at" :tone="progress.admission_reopened_at ? 'success' : 'neutral'" data-update-maintenance><Info />{{ maintenanceMessage }}</NoticeStrip>
          <NoticeStrip v-if="steps.outcome" :tone="outcomeTone" role="status"><component :is="steps.outcome === 'succeeded' ? Check : Info" />{{ phaseLabel(steps.outcome) }}</NoticeStrip>
          <NoticeStrip v-if="progressRestart" tone="warning"><Info />{{ RESTART_NOTICE }}</NoticeStrip>
          <NoticeStrip v-if="progressRestart && frozen?.conflicted" tone="warning" role="alert"><AlertCircle />现场版本已经变化，请关闭窗口并刷新后重新选择。</NoticeStrip>
          <NoticeStrip v-if="progress.error" tone="danger" role="alert"><AlertCircle />{{ progress.error }}</NoticeStrip>
        </section>

        <section class="su-section su-progress">
          <div class="su-head"><h4><Terminal />更新进度<span v-if="steps.total" class="su-mono">已完成 {{ steps.done }} / {{ steps.total }} 步</span></h4><span v-if="status.busy && !steps.outcome" class="su-live" :data-offline="failures > 0 || undefined">{{ failures ? '重新连接中' : '实时' }}</span></div>
          <div v-if="download" class="su-download-progress" data-update-download :data-state="download.state">
            <div class="su-head"><b>{{ downloadComponents[download.component] }}</b><span class="su-download-state"><RefreshCw v-if="download.state === 'downloading' && downloadPercent === undefined" aria-hidden="true" class="animate-spin motion-reduce:animate-none" />{{ downloadStates[download.state] }}</span></div>
            <div v-if="downloadPercent !== undefined" class="su-download-track" role="progressbar"
              aria-label="当前组件下载进度" :aria-valuenow="downloadPercent">
              <span :style="{ width: downloadPercent + '%' }"></span>
            </div>
            <details v-if="download.downloaded_bytes != null" class="su-meta su-mono su-byte-details">
              <summary>已下载 {{ transferSize(download.downloaded_bytes) }}<template v-if="downloadPercent !== undefined"> / {{ transferSize(download.total_bytes!) }} · {{ downloadPercent }}%</template><template v-else-if="download.state === 'downloading'"> · 总大小待获取</template></summary>
              <p>已下载 {{ byteFormat.format(download.downloaded_bytes) }} B<template v-if="download.total_bytes != null"> / {{ byteFormat.format(download.total_bytes) }} B</template></p>
            </details>
            <p v-else-if="download.state === 'downloading'" class="su-meta">总大小待获取</p>
          </div>
          <ol v-if="steps.rows.length" class="su-log">
            <li v-for="row in steps.rows" :key="row.phase" data-update-step :data-state="row.state">
              <time :datetime="row.at ?? undefined" :title="row.at ? formatLocalTime(row.at) : undefined">{{ formatLocalClock(row.at) }}</time><i aria-hidden="true" /><b>{{ phaseLabel(row.phase) }}</b><em>{{ row.detail }}</em>
              <span class="sr-only">{{ row.state === 'done' ? '已完成' : row.state === 'active' ? '进行中' : '待执行' }}</span>
            </li>
          </ol>
          <p v-else class="su-text">本次操作没有步骤记录。</p>
          <ul v-if="progress.blockers?.length" class="su-blockers" aria-label="在途工作"><li v-for="blocker in progress.blockers" :key="blocker">{{ blocker }}</li></ul>
          <div v-if="progress.cluster_nodes?.phase === 'background'" class="su-background" data-update-nodes="background">
            <Server /><span>{{ progress.admission_reopened_at ? '远程节点独立更新' : '远程节点将在中央切换后独立更新' }}</span>
            <router-link :to="{ name: 'nodes' }" class="su-link">查看节点进度<ArrowRight /></router-link>
          </div>
          <ul v-else-if="progress.cluster_nodes?.nodes.length" class="su-nodes" aria-label="节点同步进度">
            <li v-for="node in progress.cluster_nodes.nodes" :key="node.node_id">
              <div><Server /><b>{{ node.name ?? `节点 ${node.node_id}` }}</b><span>{{ NODE_PHASES[node.preparation?.phase ?? node.phase] ?? NODE_PHASES[node.phase] ?? '正在核对' }}</span></div>
              <p v-if="node.preparation?.reason">{{ node.preparation.reason }}</p>
            </li>
          </ul>
        </section>
      </div>

      <!-- 账号后台更新：已生效版本的账号逐个后台更新，概览与进度两个主视图都在末尾显示。 -->
      <section v-if="rollout?.accounts.length && (view === 'overview' || view === 'progress')" class="su-section su-rollout" aria-label="账号后台更新">
        <div class="su-head"><h4><Users />账号后台更新</h4><span class="su-meta">{{ releaseLabel(rollout.target_release) }} 已生效</span></div>
        <ul class="su-rollout-list">
          <li v-for="item in rollout.accounts" :key="item.environment_id" :data-rollout-state="item.state">
            <div><b>{{ item.name }}</b><p v-if="item.error">{{ item.error }}</p></div>
            <span class="su-pill" :data-tone="ROLLOUT_TONES[item.state]">{{ ROLLOUT_STATES[item.state] }}</span>
            <Button v-if="item.retryable !== false && (item.state === 'waiting' || item.state === 'needs_check')" variant="outline" size="sm" :disabled="!!status.busy || writing" @click="retryAccount(item.environment_id)">重试</Button>
          </li>
        </ul>
      </section>

      <!-- 版本记录与回退。 -->
      <div v-else-if="view === 'history'" class="su-view" data-update-view="history">
        <section id="available-releases" class="su-section" aria-label="可用版本">
          <div class="su-head"><h4>可用版本</h4><time class="su-meta" :title="catalog?.checked_at ?? undefined">最近检查：{{ catalog?.checked_at ? formatLocalTime(catalog.checked_at) : '等待首次检查' }}</time></div>
          <NoticeStrip v-if="checkError" tone="warning" role="status"><AlertCircle />{{ checkError }}</NoticeStrip>
          <article v-for="(release, index) in displayed" :key="release.release" class="su-release" data-release-card>
            <div class="su-release-head">
              <button type="button" class="su-release-toggle" :aria-expanded="expanded === release.release" :aria-controls="`release-detail-${release.release}`" @click="toggleDetails(release.release)">
                <component :is="expanded === release.release ? ChevronDown : ChevronRight" class="su-chevron" />
                <span class="su-release-copy">
                  <span class="su-release-title"><strong>{{ releaseLabel(release.release) }}</strong><span v-if="release.release === status.current_release" class="su-pill" data-tone="primary">当前版本</span><span v-else-if="index === 0" class="su-pill" data-tone="neutral">最新可用</span></span>
                  <span class="su-meta" :title="release.published_at">{{ formatLocalTime(release.published_at) }}</span>
                  <span class="su-text">{{ releaseSummary(release) }}</span>
                </span>
              </button>
              <Button v-if="release.release !== status.current_release" size="sm" :disabled="!!status.busy || writing || catalog?.fresh === false || !release.data_compatible" @click="installRelease(release)"><Download />{{ updateButton(release, '安装更新') }}</Button>
            </div>
            <div v-if="expanded === release.release" :id="`release-detail-${release.release}`" class="su-release-detail" data-release-details>
              <p class="su-full-text">{{ releaseNotes(release.changes) }}</p>
              <p v-if="release.compatibility_reason" class="su-warning">{{ release.compatibility_reason === 'migration_evidence_missing' ? '此来源版本的升级与回退演练证据待发布端补齐。' : '此版本的数据兼容声明待发布端验证。' }}</p>
              <p v-if="release.migrations?.length" class="su-meta">包含已验证的数据库迁移，安装前自动保存两库快照。</p>
              <p v-for="migration in release.migrations ?? []" :key="migration.database" class="su-meta">{{ databaseLabel(migration.database) }} → 版本 {{ migration.target_version }} · {{ migration.steps }} 项登记</p>
              <p class="su-meta">{{ release.account_changed ? `预计重建 ${runningEnvironments} 个运行环境，已停止环境保留原状态。` : '兼容的账号运行环境继续复用。' }}</p>
              <dl class="su-ids"><dt>发行标识</dt><dd>{{ release.release }}</dd><dt>清单 SHA256</dt><dd>{{ release.manifest_sha256 }}</dd></dl>
            </div>
          </article>
          <p v-if="!catalog?.releases.length" class="su-empty">{{ catalog?.checking ? '正在检查受信版本…' : '等待检查可用版本' }}</p>
          <button v-if="older.length || status.history?.length" type="button" class="su-link" :aria-expanded="historyOpen" aria-controls="update-history" @click="historyOpen = !historyOpen; expanded = ''"><component :is="historyOpen ? ChevronDown : ChevronRight" />{{ historyOpen ? '收起历史版本' : `查看历史版本与回退（${older.length} 个其它发行）` }}</button>
        </section>
        <section v-if="historyOpen" id="update-history" class="su-section" aria-label="已安装版本与回退">
          <div class="su-head"><h4>已安装版本与回退</h4></div>
          <div v-for="item in status.history ?? []" :key="item.release" class="su-installed">
            <div><b>{{ releaseLabel(item.release) }}</b><p class="su-meta">{{ formatLocalTime(item.installed_at) }} · {{ item.rollback_available ? '满足当前数据回退条件' : '当前数据合同阻止回退' }}</p><code>{{ item.release }}</code></div>
            <Button variant="outline" size="sm" :disabled="!!status.busy || writing || !item.rollback_available" @click="confirm('rollback', item.release, item.manifest_sha256)">回退到此版本</Button>
          </div>
          <p v-if="!status.history?.length" class="su-meta">首次接入后，成功更新会保存可回退的历史组合。</p>
        </section>
      </div>

      <!-- 运行组件与维护详情。 -->
      <div v-else-if="view === 'maintenance'" class="su-view su-maintenance" data-update-view="maintenance">
        <section class="su-section">
          <div class="su-head"><h4><Box />账号运行环境</h4></div>
          <p class="su-count">{{ runningEnvironments }}<span>个运行中</span></p>
          <router-link :to="{ name: 'environments' }" class="su-link">管理环境<ArrowRight /></router-link>
          <details class="su-sources"><summary>镜像来源</summary><p class="su-mono-text">所选：{{ status.components?.account.release }}</p><p v-for="source in environmentSources" :key="source.release">{{ source.release }} · {{ source.count }} 个</p></details>
        </section>
        <section class="su-section">
          <div class="su-head"><h4><Cpu />CLI 与请求内核</h4></div>
          <p class="su-count">按账号独立管理</p>
          <p class="su-meta">各账号显示实际 CLI 版本和内核选择</p>
          <router-link :to="{ name: 'environments' }" class="su-link">查看版本与切换入口<ArrowRight /></router-link>
        </section>
      </div>

      <!-- 操作详情与数据库快照。 -->
      <div v-else-if="view === 'details'" class="su-view" data-update-view="details">
        <section class="su-section">
          <div class="su-head"><h4><List />操作详情与数据库快照</h4></div>
          <template v-for="(label, check) in CONTROL_CHECKS" :key="check">
            <div v-if="progress?.control_health?.[check]" class="su-health" :data-update-health="check">
              <h5>{{ label }}健康检查</h5>
              <p v-for="(probe, service) in progress.control_health[check]" :key="service">{{ CONTROL_SERVICES[service] }} · {{ probeResult(probe) }}</p>
            </div>
          </template>
          <dl v-if="progress" class="su-ids">
            <dt>目标发行</dt><dd>{{ progress.target_release }}</dd>
            <dt>操作 ID</dt><dd>{{ progress.operation_id }}</dd>
            <dt>更新时间</dt><dd :title="progress.updated_at">{{ formatLocalTime(progress.updated_at) }}</dd>
            <template v-if="progress.admission_blocked_at"><dt>暂停接单</dt><dd :title="progress.admission_blocked_at">{{ formatLocalTime(progress.admission_blocked_at) }}</dd></template>
            <template v-if="progress.admission_reopened_at"><dt>恢复接单</dt><dd :title="progress.admission_reopened_at">{{ formatLocalTime(progress.admission_reopened_at) }}</dd></template>
          </dl>
          <p v-else class="su-text">暂无操作记录。</p>
          <p v-if="progress?.database_snapshot" class="su-text">{{ snapshotLabel(progress.database_snapshot) }}</p>
          <p v-for="(migration, database) in progress?.database_migrations ?? {}" :key="database" class="su-text">{{ databaseLabel(String(database)) }} · 目标版本 {{ migration.target_version }} · {{ migrationStateLabel(migration.state) }}</p>
        </section>
      </div>
      <section v-if="(view === 'overview' || view === 'progress') && (receipts?.items.length || receiptAfter || receiptError)"
        class="su-section su-rollout" aria-label="V2 工具回执">
        <div class="su-head"><h4><RotateCcw />V2 工具回执</h4></div>
        <NoticeStrip v-if="receiptError" tone="warning" role="status"><AlertCircle />{{ receiptError }}</NoticeStrip>
        <ul v-if="receipts?.items.length" class="su-rollout-list">
          <li v-for="item in receipts.items" :key="item.id" :data-tui-receipt-state="item.state">
            <div><b>{{ item.account_name }}</b><p>{{ RECEIPT_STATES[item.state] }}</p></div>
            <Button variant="outline" size="sm" :disabled="!!status.busy || !!receiptWriting || writing"
              @click="recoverReceipt(item)">{{ receiptWriting === item.id ? '正在核对…' : '核对并恢复' }}</Button>
          </li>
        </ul>
        <div v-if="receiptAfter || receipts?.next" class="su-head">
          <Button v-if="receiptAfter" variant="ghost" size="sm" @click="loadReceipts('')">回到首页</Button>
          <Button v-if="receipts?.next" variant="ghost" size="sm" @click="loadReceipts(receipts.next)">下一页</Button>
        </div>
      </section>
    </template>

    <template v-if="status?.installed && !loading" #footer>
      <template v-if="trail.length && view !== 'progress'">
        <Button variant="ghost" size="sm" @click="back"><ChevronLeft />返回</Button><span class="su-push" />
      </template>
      <template v-else-if="view === 'overview'">
        <Button variant="ghost" size="sm" @click="enter('history')"><History />版本记录与回退</Button>
        <Button variant="ghost" size="sm" @click="enter('maintenance')"><Box />运行组件与维护详情</Button>
        <Button variant="outline" class="su-push" :disabled="checking || catalog?.checking" @click="check"><RefreshCw :class="checking || catalog?.checking ? 'animate-spin motion-reduce:animate-none' : ''" />{{ checking || catalog?.checking ? '正在检查…' : '检查更新' }}</Button>
        <Button v-if="installable" :disabled="installDisabled" @click="installLatest"><component :is="restartReady ? RotateCcw : Download" />{{ installLabel }}</Button>
      </template>
      <template v-else-if="view === 'progress'">
        <Button variant="ghost" size="sm" @click="enter('details')"><List />操作详情与数据库快照</Button>
        <span class="su-push" />
        <Button v-if="cancelAllowed" variant="outline" :disabled="writing || progress?.cancel_requested" @click="cancel">{{ progress?.cancel_requested ? '正在取消…' : '取消等待' }}</Button>
        <Button v-if="recoveryAllowed" variant="outline" :disabled="writing" @click="confirm('recover', progress!.target_release, '', true)">恢复操作</Button>
        <Button v-if="status.busy && !steps?.outcome" disabled><RefreshCw class="animate-spin motion-reduce:animate-none" />更新中…</Button>
        <template v-else-if="progressRestart">
          <Button variant="outline" :disabled="writing" @click="trail.length ? back() : finish()">返回</Button>
          <Button :disabled="writing || !!frozen?.conflicted" @click="submitDirect(progressRestart)"><RotateCcw />立即重启</Button>
        </template>
        <Button v-else-if="!recoveryAllowed" @click="trail.length ? back() : finish()">{{ trail.length ? '返回' : '完成' }}</Button>
      </template>
    </template>
  </ModalDialog>

  <ConfirmationDialog :open="confirmOpen" :title="frozen ? confirmTitle(frozen) : ''" :message="frozen?.restart ? RESTART_NOTICE : '镜像准备期间继续接单。支持快速切换时，正在执行的推理会断开。'"
    :confirm-label="frozen?.action === 'recover' ? '开始恢复' : frozen?.restart ? '立即重启' : '确认执行'" :busy="writing" :confirm-disabled="!!frozen?.conflicted" :error="frozen?.conflicted ? '现场版本已经变化，请关闭窗口并刷新后重新选择。' : ''"
    @confirm="submit(confirmMinutes)" @cancel="closeConfirm">
    <div v-if="frozen" class="su-confirm">
      <p class="su-confirm-label">{{ frozen.label }}</p>
      <code>{{ frozen.body.target_release }}</code>
      <p v-if="frozen.action !== 'recover'" class="su-text">{{ frozen.accountChanged ? '将按计划核对并更新受影响的账号环境。' : '兼容的账号容器继续复用。' }}</p>
      <NumberInput v-if="frozen.action !== 'recover' && !frozen.restart" v-model="confirmMinutes" label="在途等待上限（分钟）" :min="1" :max="120" :disabled="writing || frozen.sent" />
    </div>
  </ConfirmationDialog>
</template>
