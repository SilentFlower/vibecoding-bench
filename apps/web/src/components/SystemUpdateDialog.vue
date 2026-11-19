<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { ApiError, api, type SystemUpdateCatalog, type SystemUpdateRelease, type SystemUpdateRequest, type SystemUpdateStatus } from '../api';
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
import { AlertCircle, ArrowRight, ArrowUpCircle, Box, Check, ChevronDown, ChevronLeft, ChevronRight, Cpu, Download, History, Info, List, Pause, RefreshCw, Server, Terminal } from '@/components/ui/icon';

/**
 * 系统更新弹窗：版本概览与直接安装、按步骤的安装进度，以及版本记录、维护详情、操作详情三个二级视图。
 * 打开期间轮询更新状态，关闭即卸载并停止轮询。
 * v-model:open 控制弹窗开关；关闭后由外壳决定路由去向。
 */
const open = defineModel<boolean>('open', { default: false });

type Action = 'install' | 'rollback' | 'recover';
type View = 'overview' | 'progress' | 'history' | 'maintenance' | 'details';
/** 一次冻结的写请求：网络结果不确定时整份重发，保持同一操作 ID 与等待期限。 */
interface Frozen { action: Action; body: SystemUpdateRequest; accountChanged: boolean; label: string; sent: boolean; conflicted: boolean; confirm: boolean }

const DEFAULT_DRAIN_MINUTES = 1;
const NODE_PHASES: Record<string, string> = { registering: '等待同步', checking: '核对组件', draining: '等待原工作完成', fenced: '原环境已停止', stopping: '停止原组件', backing_up: '备份资料', backed_up: '已停止，等待切换', switching: '切换组件', restoring: '恢复账号', completed: '同步完成', rolled_back: '已恢复原组件', rolling_back_control: '恢复原组件', platform_restoring: '恢复原组件', platform_restored: '恢复完成', waiting: '等待重试', needs_check: '等待核对' };
const ACTION_TITLES: Record<Action, string> = { install: '确认安装更新', rollback: '确认版本回退', recover: '恢复本次操作' };

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
/** 二级视图的返回栈；为空时显示主视图。 */
const trail = ref<View[]>([]);
let alive = true;
let timer: ReturnType<typeof setTimeout> | undefined;
let controller: AbortController | undefined;

const progress = computed(() => status.value?.operation ?? null);
const cancelAllowed = computed(() => !!status.value?.busy && ['preparing', 'draining'].includes(progress.value?.phase ?? ''));
const recoveryAllowed = computed(() => ['reconcile', 'succeeded_cleanup_pending'].includes(progress.value?.phase ?? ''));
const mainView = computed<View>(() => {
  // 维护中与需要恢复的操作先于发布说明呈现；本次看着结束的操作停在结局。没有操作记录时只能显示概览。
  if (!progress.value) return 'overview';
  return status.value?.busy || recoveryAllowed.value || followed.value === progress.value.operation_id ? 'progress' : 'overview';
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
  return installable.value ? { text: '有可用更新', tone: 'success' } : { text: '当前已是最新版本', tone: 'neutral' };
});
const installLabel = computed(() => writing.value && frozen.value && !frozen.value.confirm ? '正在登记…'
  : catalog.value?.fresh === false ? '先检查更新' : latestRelease.value?.data_compatible === false ? '待验证兼容' : '安装更新');
const installDisabled = computed(() => !status.value?.revision || !!status.value.busy || writing.value || !catalog.value?.fresh
  || !latestRelease.value?.data_compatible || !!(frozen.value && !frozen.value.confirm && frozen.value.conflicted));
const planLocked = computed(() => !!(frozen.value && !frozen.value.confirm && frozen.value.sent));
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
const progressPill = computed(() => steps.value?.outcome
  ? { text: phaseLabel(steps.value.outcome), tone: outcomeTone.value }
  : { text: status.value?.busy ? '更新中' : phaseLabel(progress.value?.phase ?? ''), tone: 'info' });

/** 阶段中文名，未知阶段保持原值。@param phase 原始阶段。@return 文案。 */
function phaseLabel(phase: string): string { return UPDATE_PHASE_LABELS[phase] ?? phase; }

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
      timer = setTimeout(refresh, failures.value ? Math.min(30000, 2000 * 2 ** Math.min(failures.value, 4)) : status.value?.busy || catalog.value?.checking ? 2000 : 10000);
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
 * 冻结现场与目标。恢复沿用原操作 ID，其余动作生成新 ID。
 * @param action 动作。@param release 目标发行。@param digest 清单摘要。@param accountChanged 是否影响账号环境。@param confirm 是否经二次确认框。
 * @return 冻结请求；现场未就绪时为空。
 */
function freeze(action: Action, release: string, digest: string, accountChanged: boolean, confirm: boolean): Frozen | null {
  if (!status.value?.revision) return null;
  return { action, accountChanged, confirm, sent: false, conflicted: false, label: releaseLabel(release), body: {
    operation_id: action === 'recover' ? progress.value!.operation_id : operationId(), expected_revision: status.value.revision,
    target_release: release, target_manifest_sha256: digest, drain_timeout_seconds: DEFAULT_DRAIN_MINUTES * 60 } };
}

/** 提交冻结请求，网络不确定时保留同一个操作 ID。@param minutes 等待上限（分钟）。@return 本次提交完成。 */
async function submit(minutes: number | string): Promise<void> {
  const selected = frozen.value;
  if (!selected || writing.value || selected.conflicted) return;
  const wait = Number(minutes);
  if (selected.action !== 'recover' && (!Number.isInteger(wait) || wait < 1 || wait > 120)) {
    toast.show('等待期限应为 1～120 分钟');
    return;
  }
  if (!selected.sent && selected.action !== 'recover') {
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
    toast.show('操作已登记，进度会持续保存', 'success');
    await refresh();
  } catch (cause) {
    if (!alive) return;
    selected.conflicted = cause instanceof ApiError && cause.status === 409;
    toast.show(cause instanceof Error ? cause.message : '提交结果待核对，请重试同一操作');
  } finally {
    if (alive) writing.value = false;
  }
}

/** 直接安装最新版本：弹窗中的安装方式即确认，冻结后立即提交。@return 提交完成。 */
async function installLatest(): Promise<void> {
  const latest = latestRelease.value;
  if (!latest || installDisabled.value) return;
  if (!frozen.value || frozen.value.confirm || frozen.value.body.target_release !== latest.release) {
    frozen.value = freeze('install', latest.release, latest.manifest_sha256, latest.account_changed, false);
  }
  await submit(planMinutes.value);
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
onUnmounted(() => { alive = false; clearTimeout(timer); controller?.abort(); versionController.abort(); });
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

        <section v-if="installable && latestRelease" class="su-section su-plan">
          <IconTile tone="info" class="su-plan-icon"><Pause /></IconTile>
          <div class="su-plan-copy"><b>安装时暂停新接单</b><p>等待在途工作结束后切换平台服务；{{ latestRelease.account_changed ? `预计更新 ${runningEnvironments} 个运行环境，已停止环境保留原状态。` : `${runningEnvironments} 个账号运行环境运行中，兼容的运行环境继续复用。` }}</p></div>
          <div class="su-plan-minutes"><NumberInput v-model="planMinutes" label="在途等待上限（分钟）" :min="1" :max="120" :disabled="planLocked" :invalid="!Number.isInteger(Number(planMinutes)) || Number(planMinutes) < 1 || Number(planMinutes) > 120" /></div>
        </section>
        <NoticeStrip v-if="frozen && !frozen.confirm && frozen.conflicted" tone="warning" role="alert"><AlertCircle />现场版本已经变化，请关闭窗口并刷新后重新选择。</NoticeStrip>

        <NoticeStrip v-if="progress" :tone="progress.phase === 'succeeded' ? 'success' : progress.phase === 'failed' ? 'danger' : progress.phase === 'cancelled' ? 'neutral' : 'warning'" class="su-last">
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
          <NoticeStrip v-if="status.busy && !steps.outcome" tone="neutral"><Info />维护期间新工作暂缓，在途工作自然结束后继续。</NoticeStrip>
          <NoticeStrip v-else-if="steps.outcome" :tone="outcomeTone" role="status"><component :is="steps.outcome === 'succeeded' ? Check : Info" />{{ phaseLabel(steps.outcome) }}</NoticeStrip>
          <NoticeStrip v-if="progress.error" tone="danger" role="alert"><AlertCircle />{{ progress.error }}</NoticeStrip>
        </section>

        <section class="su-section su-progress">
          <div class="su-head"><h4><Terminal />更新进度<span v-if="steps.total" class="su-mono">{{ steps.done }} / {{ steps.total }}</span></h4><span v-if="status.busy && !steps.outcome" class="su-live" :data-offline="failures > 0 || undefined">{{ failures ? '重新连接中' : '实时' }}</span></div>
          <ol v-if="steps.rows.length" class="su-log">
            <li v-for="row in steps.rows" :key="row.phase" data-update-step :data-state="row.state">
              <time :datetime="row.at ?? undefined" :title="row.at ? formatLocalTime(row.at) : undefined">{{ formatLocalClock(row.at) }}</time><i aria-hidden="true" /><b>{{ phaseLabel(row.phase) }}</b><em>{{ row.detail }}</em>
              <span class="sr-only">{{ row.state === 'done' ? '已完成' : row.state === 'active' ? '进行中' : '待执行' }}</span>
            </li>
          </ol>
          <p v-else class="su-text">本次操作没有步骤记录。</p>
          <ul v-if="progress.blockers?.length" class="su-blockers" aria-label="在途工作"><li v-for="blocker in progress.blockers" :key="blocker">{{ blocker }}</li></ul>
          <ul v-if="progress.cluster_nodes?.nodes.length" class="su-nodes" aria-label="节点同步进度">
            <li v-for="node in progress.cluster_nodes.nodes" :key="node.node_id">
              <div><Server /><b>{{ node.name ?? `节点 ${node.node_id}` }}</b><span>{{ NODE_PHASES[node.preparation?.phase ?? node.phase] ?? NODE_PHASES[node.phase] ?? '正在核对' }}</span></div>
              <p v-if="node.preparation?.reason">{{ node.preparation.reason }}</p>
            </li>
          </ul>
        </section>
      </div>

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
              <Button v-if="release.release !== status.current_release" size="sm" :disabled="!!status.busy || writing || catalog?.fresh === false || !release.data_compatible" @click="confirm('install', release.release, release.manifest_sha256, release.account_changed)"><Download />{{ catalog?.fresh === false ? '先检查更新' : release.data_compatible ? '安装更新' : '待验证兼容' }}</Button>
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
          <dl v-if="progress" class="su-ids">
            <dt>目标发行</dt><dd>{{ progress.target_release }}</dd>
            <dt>操作 ID</dt><dd>{{ progress.operation_id }}</dd>
            <dt>更新时间</dt><dd :title="progress.updated_at">{{ formatLocalTime(progress.updated_at) }}</dd>
          </dl>
          <p v-else class="su-text">暂无操作记录。</p>
          <p v-if="progress?.database_snapshot" class="su-text">{{ snapshotLabel(progress.database_snapshot) }}</p>
          <p v-for="(migration, database) in progress?.database_migrations ?? {}" :key="database" class="su-text">{{ databaseLabel(String(database)) }} · 目标版本 {{ migration.target_version }} · {{ migrationStateLabel(migration.state) }}</p>
        </section>
      </div>
    </template>

    <template v-if="status?.installed && !loading" #footer>
      <template v-if="trail.length && view !== 'progress'">
        <Button variant="ghost" size="sm" @click="back"><ChevronLeft />返回</Button><span class="su-push" />
      </template>
      <template v-else-if="view === 'overview'">
        <Button variant="ghost" size="sm" @click="enter('history')"><History />版本记录与回退</Button>
        <Button variant="ghost" size="sm" @click="enter('maintenance')"><Box />运行组件与维护详情</Button>
        <Button variant="outline" class="su-push" :disabled="checking || catalog?.checking" @click="check"><RefreshCw :class="checking || catalog?.checking ? 'animate-spin motion-reduce:animate-none' : ''" />{{ checking || catalog?.checking ? '正在检查…' : '检查更新' }}</Button>
        <Button v-if="installable" :disabled="installDisabled" @click="installLatest"><Download />{{ installLabel }}</Button>
      </template>
      <template v-else-if="view === 'progress'">
        <Button variant="ghost" size="sm" @click="enter('details')"><List />操作详情与数据库快照</Button>
        <span class="su-push" />
        <Button v-if="cancelAllowed" variant="outline" :disabled="writing || progress?.cancel_requested" @click="cancel">{{ progress?.cancel_requested ? '正在取消…' : '取消等待' }}</Button>
        <Button v-if="recoveryAllowed" variant="outline" :disabled="writing" @click="confirm('recover', progress!.target_release, '', true)">恢复操作</Button>
        <Button v-if="status.busy && !steps?.outcome" disabled><RefreshCw class="animate-spin motion-reduce:animate-none" />更新中…</Button>
        <Button v-else-if="!recoveryAllowed" @click="trail.length ? back() : finish()">{{ trail.length ? '返回' : '完成' }}</Button>
      </template>
    </template>
  </ModalDialog>

  <ConfirmationDialog :open="confirmOpen" :title="frozen ? ACTION_TITLES[frozen.action] : ''" message="系统会暂停新接单，等待在途工作结束，再执行维护切换。"
    :confirm-label="frozen?.action === 'recover' ? '开始恢复' : '确认执行'" :busy="writing" :confirm-disabled="!!frozen?.conflicted" :error="frozen?.conflicted ? '现场版本已经变化，请关闭窗口并刷新后重新选择。' : ''"
    @confirm="submit(confirmMinutes)" @cancel="closeConfirm">
    <div v-if="frozen" class="su-confirm">
      <p class="su-confirm-label">{{ frozen.label }}</p>
      <code>{{ frozen.body.target_release }}</code>
      <p v-if="frozen.action !== 'recover'" class="su-text">{{ frozen.accountChanged ? '将按计划核对并更新受影响的账号环境。' : '兼容的账号容器继续复用。' }}</p>
      <NumberInput v-if="frozen.action !== 'recover'" v-model="confirmMinutes" label="在途等待上限（分钟）" :min="1" :max="120" :disabled="writing || frozen.sent" />
    </div>
  </ConfirmationDialog>
</template>
