<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { Button } from '../ui/button';
import { ConfirmationDialog } from '../ui/feedback';
import { nodeApi, type AccountNodeAssignment, type ExecutionNode, type NodeMigration, type NodeMigrationStart, type NodeTaskAccount } from './nodeApi';

const props = defineProps<{ assignment: AccountNodeAssignment; account?: NodeTaskAccount; target?: ExecutionNode }>();
const emit = defineEmits<{ changed: []; busy: [value: boolean] }>();
const history = ref<NodeMigration[]>([]), loaded = ref(false), reading = ref(false), sending = ref(false);
const error = ref(''), failed = ref(false);
type Confirmation = { action: 'start' | 'cancel'; accountId: number; accountName: string; targetName: string; operation: string; body?: NodeMigrationStart };
const frozen = ref<Confirmation | null>(null);
const latest = computed(() => history.value[0]);
const failureStages: Record<string, string> = { draining: '等待原工作完成', fence: '隔离源环境', export: '导出资料', transfer: '传输资料', 'verify-import': '核验目标资料', 'prepare-import': '准备目标环境', commit: '保存新归属', 'activate-import': '激活目标环境', 'revoke-import': '撤销目标副本', 'restore-source': '恢复源环境', context: '核对原操作' };
const unfinished = computed(() => !!latest.value && !['completed', 'cancelled'].includes(latest.value.phase));
const canStart = computed(() => loaded.value && !unfinished.value && props.assignment.phase === 'ready'
  && !!props.account?.effective_claude_code_version && !!props.target?.enabled
  && props.target.id !== props.assignment.node_id && (props.target.kind === 'local' || props.target.preparation?.state === 'prepared'));
let alive = true, generation = 0, timer: ReturnType<typeof setTimeout> | undefined, controller: AbortController | undefined;

/** 串行读取当前账号的持久迁移状态，轮询保留已有内容。@return 读取结束。 */
async function refresh(): Promise<void> {
  if (!alive || reading.value || sending.value) return;
  if (timer) clearTimeout(timer);
  const current = ++generation;
  controller = new AbortController(); reading.value = true;
  const previous = latest.value;
  try {
    const value = await nodeApi.migrations(props.assignment.account_id, controller.signal);
    if (!alive || current !== generation) return;
    history.value = value.items; loaded.value = true; error.value = '';
    if (previous && !['completed', 'cancelled'].includes(previous.phase) && latest.value
      && ['completed', 'cancelled'].includes(latest.value.phase)) emit('changed');
  } catch (cause) {
    if (alive && current === generation) error.value = (cause as Error).message;
  } finally {
    if (alive && current === generation) {
      reading.value = false;
      if (unfinished.value || error.value) timer = setTimeout(refresh, 3000);
    }
  }
}

/** 冻结当前账号、版本和目标，确认窗口只展示该快照。@return 无。 */
function openStart(): void {
  if (!canStart.value || !props.account || !props.target) return;
  const operation = Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, '0')).join('');
  frozen.value = { action: 'start', accountId: props.assignment.account_id, accountName: props.account.name,
    targetName: props.target.name, operation, body: { operation_id: operation, node_id: props.target.id,
      revision: props.assignment.revision, version: props.account.effective_claude_code_version! } };
  failed.value = false; error.value = ''; emit('busy', true);
}

/** 冻结原迁移的取消范围。@return 无。 */
function openCancel(): void {
  const value = latest.value;
  if (!value?.can_cancel) return;
  frozen.value = { action: 'cancel', accountId: value.account_id, accountName: props.account?.name ?? '',
    targetName: value.target.name, operation: value.operation_id };
  failed.value = false; error.value = ''; emit('busy', true);
}

/** 关闭当前确认；未知结果继续由原持久记录核对。@return 无。 */
function close(): void { if (!sending.value) { frozen.value = null; emit('busy', false); void refresh(); } }

/** 提交或继续原操作；提交结果未知时只读取同一操作。@param resume 原阶段继续。@return 请求结束。 */
async function submit(resume = false): Promise<void> {
  const confirmation = frozen.value;
  const value = latest.value;
  if (sending.value || (!confirmation && !resume)) return;
  const accountId = confirmation?.accountId ?? props.assignment.account_id;
  const operation = confirmation?.operation ?? value?.operation_id;
  if (!operation) return;
  sending.value = true; error.value = ''; emit('busy', true);
  if (timer) clearTimeout(timer);
  generation++; controller?.abort(); reading.value = false;
  try {
    const result = failed.value && confirmation ? await nodeApi.migration(accountId, operation)
      : resume ? await nodeApi.migrationAction(accountId, operation, 'resume')
      : confirmation?.action === 'cancel' ? await nodeApi.migrationAction(accountId, operation, 'cancel')
      : await nodeApi.migrate(accountId, confirmation!.body!);
    if (!alive) return;
    history.value = [result, ...history.value.filter(row => row.operation_id !== result.operation_id)];
    frozen.value = null; failed.value = false; emit('changed');
  } catch (cause) {
    if (alive) { failed.value = true; error.value = `${(cause as Error).message}。请核对原操作状态。`; }
  } finally {
    if (alive) { sending.value = false; emit('busy', !!frozen.value); if (!frozen.value) void refresh(); }
  }
}

onMounted(refresh);
onUnmounted(() => { alive = false; generation++; controller?.abort(); if (timer) clearTimeout(timer); emit('busy', false); });
</script>

<template>
  <section class="node-migration">
    <div class="migration-heading"><div><h3>迁移已有环境</h3><p>先排空并停止源环境，再校验和迁移 HOME、身份与工程资料。</p></div><Button variant="outline" :disabled="!canStart || sending || !!frozen" @click="openStart">迁移到所选节点</Button></div>
    <p v-if="!account?.effective_claude_code_version">账号 CLI 版本待核对。</p>
    <div v-if="latest" class="migration-status" aria-live="polite">
      <strong>{{ latest.source.name }} → {{ latest.target.name }}</strong>
      <p>{{ latest.message }}<span v-if="latest.running"> · 后台处理中</span><span v-else-if="latest.cancelling && unfinished"> · 取消操作待继续</span></p>
      <p v-if="latest.failure" role="alert">{{ latest.failure.message }} · {{ latest.failure.action }}（{{ failureStages[latest.failure.stage] ?? '核对当前步骤' }}）</p>
      <p v-else-if="latest.phase === 'reconcile'">已保留原操作和维护状态，请继续核对。归属切换后继续目标激活。</p>
      <div class="migration-actions"><Button v-if="latest.can_resume" :disabled="sending || !!frozen" @click="submit(true)">{{ latest.cancelling ? '继续取消' : '继续原迁移' }}</Button><Button v-if="latest.can_cancel" variant="outline" :disabled="sending || !!frozen" @click="openCancel">取消迁移</Button><Button variant="outline" :disabled="reading || sending" @click="refresh">刷新迁移状态</Button></div>
    </div>
    <p v-else-if="loaded">当前账号还没有迁移记录。</p>
    <p v-else role="status">正在读取迁移记录…</p>
    <p v-if="error && !frozen" class="migration-error" role="alert">{{ error }}</p>
    <ConfirmationDialog :open="!!frozen" :title="frozen?.action === 'cancel' ? '取消原迁移' : '迁移账号环境'"
      :message="frozen?.action === 'cancel' ? `核对并停止「${frozen.targetName}」的本次目标副本，再恢复源节点。` : `将「${frozen?.accountName}」迁移到「${frozen?.targetName}」。迁移期间账号暂停接收新工作，源资料按操作保留。`"
      :confirm-label="failed ? '核对原操作' : frozen?.action === 'cancel' ? '确认取消迁移' : '开始迁移'" :busy="sending" :error="error" @confirm="submit()" @cancel="close" />
  </section>
</template>

<style scoped>
.node-migration{display:grid;gap:12px;border-top:1px solid var(--ui-border);padding-top:18px}.migration-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}h3{font-size:var(--ui-font-body,14px);font-weight:600}p{font-size:var(--ui-font-small,13px);color:var(--ui-muted);overflow-wrap:anywhere}.migration-status{display:grid;gap:8px;padding:16px;background:var(--ui-field-surface);border:1px solid var(--ui-border);border-radius:8px}strong{font-size:var(--ui-font-body,14px);overflow-wrap:anywhere}.migration-actions{display:flex;flex-wrap:wrap;gap:10px}.migration-error{color:var(--ui-danger)}@media(max-width:600px){.migration-heading{align-items:stretch;flex-direction:column}}
</style>
