<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import type { Account } from '../../api';
import { Button } from '../ui/button';
import { ChoiceSelect } from '../ui/controls';
import { ConfirmationDialog } from '../ui/feedback';
import { nodeApi, type AccountNodeAssignment, type ExecutionNode, type NodeTaskAccount } from './nodeApi';
import { runtimeRequest } from './runtimeApi';
import AccountNodeMigration from './AccountNodeMigration.vue';

const props = defineProps<{ nodes: ExecutionNode[]; agyAccounts: Pick<Account, 'id' | 'name' | 'email' | 'status'>[] }>();
const emit = defineEmits<{ changed: [] }>();
const accounts = ref<NodeTaskAccount[]>([]);
const selectedAccount = ref(''), selectedNode = ref('');
const assignment = ref<AccountNodeAssignment | null>(null);
const loading = ref(false), saving = ref(false), confirming = ref(false), error = ref(''), message = ref('');
const migrationBusy = ref(false);
const accountOptions = computed(() => [
  ...accounts.value.map(row => ({ value: String(row.id), label: row.enabled ? row.name : `${row.name}（已停用）` })),
  ...props.agyAccounts.map(row => ({ value: `agy:${row.id}`,
    label: `${row.name || row.email}（反重力${row.status === 'disabled' ? ' · 已停用' : ''}）` })),
]);
const selectedAgy = computed(() => selectedAccount.value.startsWith('agy:'));
const nodeOptions = computed(() => props.nodes.map(row => ({ value: String(row.id), label: row.name,
  disabled: !row.enabled || selectedAgy.value && row.kind === 'ssh' && row.preparation?.state !== 'prepared' })));
const accountName = computed(() => accountOptions.value.find(row => row.value === selectedAccount.value)?.label ?? '');
const nodeName = computed(() => props.nodes.find(row => String(row.id) === selectedNode.value)?.name ?? '');
const currentAccount = computed(() => accounts.value.find(row => String(row.id) === selectedAccount.value));
const currentNode = computed(() => props.nodes.find(row => String(row.id) === selectedNode.value));
let alive = true, generation = 0, request: AbortController | undefined;
const lifecycle = new AbortController();

/** 账号切换后丢弃原归属和迟到响应，保留版本比较。@return 读取结束。 */
async function readAssignment(): Promise<void> {
  const current = ++generation;
  request?.abort(); request = new AbortController();
  assignment.value = null; selectedNode.value = ''; error.value = ''; message.value = ''; confirming.value = false;
  loading.value = false;
  if (!selectedAccount.value) return;
  const id = Number(selectedAgy.value ? selectedAccount.value.slice(4) : selectedAccount.value);
  loading.value = true;
  try {
    const value = await nodeApi.assignment(id, request.signal, selectedAgy.value);
    if (alive && current === generation) { assignment.value = value; selectedNode.value = String(value.node_id); }
  } catch (cause) {
    if (alive && current === generation && !request.signal.aborted) error.value = (cause as Error).message;
  } finally { if (alive && current === generation) loading.value = false; }
}

/** 固定账号和分配版本提交首次执行位置。@return 保存结束。 */
async function save(): Promise<void> {
  const original = assignment.value;
  if (!original || saving.value || !selectedNode.value) return;
  saving.value = true; error.value = '';
  try {
    const value = await nodeApi.assignInitial(original.account_id, Number(selectedNode.value), original.revision);
    if (!alive) return;
    assignment.value = value; confirming.value = false; message.value = `已将「${accountName.value}」分配到「${value.node_name}」。`;
    emit('changed');
  } catch (cause) { if (alive) error.value = (cause as Error).message; }
  finally { if (alive) saving.value = false; }
}

watch(selectedAccount, readAssignment);
watch(accountOptions, options => {
  if (selectedAgy.value && !options.some(option => option.value === selectedAccount.value)) selectedAccount.value = '';
});
onMounted(async () => {
  try { const value = await runtimeRequest<typeof accounts.value>('/accounts', { signal: lifecycle.signal }); if (alive) accounts.value = value; }
  catch (cause) { if (alive) error.value = (cause as Error).message; }
});
onUnmounted(() => { alive = false; generation++; request?.abort(); lifecycle.abort(); });
</script>

<template>
  <section class="account-node-selector">
    <header><h2>账号执行节点</h2><p>为首次执行的账号选择服务器。已有运行资料的账号通过迁移变更节点。</p></header>
    <div class="assignment-fields">
      <ChoiceSelect :model-value="selectedAccount || undefined" label="账号" :options="accountOptions" :disabled="saving || migrationBusy" placeholder="选择账号" @update:model-value="selectedAccount = $event" />
      <ChoiceSelect :model-value="selectedNode || undefined" label="执行节点" :options="nodeOptions" :disabled="saving || migrationBusy || loading || !assignment" placeholder="选择已准备的节点" @update:model-value="selectedNode = $event" />
    </div>
    <p v-if="assignment">当前节点：{{ assignment.node_name }} · {{ assignment.phase === 'retired' ? '归属已归档' : assignment.phase === 'ready' ? '归属已保存' : '正在维护核对' }}<span v-if="!assignment.enabled"> · 已暂停接单</span></p>
    <p v-if="loading" role="status">正在读取当前归属…</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error && !confirming" class="assignment-error" role="alert">{{ error }}</p>
    <footer><Button variant="outline" :disabled="!selectedAccount || loading || saving || migrationBusy" @click="readAssignment">重新读取归属</Button><Button v-if="!selectedAgy" :disabled="!assignment || !selectedNode || Number(selectedNode) === assignment.node_id || loading || saving || migrationBusy || assignment.phase !== 'ready'" @click="error = ''; confirming = true">保存首次执行节点</Button></footer>
    <AccountNodeMigration v-if="assignment" :key="selectedAccount" :assignment="assignment" :account-name="accountName" :agy="selectedAgy" :version="selectedAgy ? '1.5.9' : currentAccount?.effective_claude_code_version" :target="currentNode" @busy="migrationBusy = $event" @changed="readAssignment(); emit('changed')" />
    <ConfirmationDialog :open="confirming" title="设置首次执行节点" :message="`将「${accountName}」的首次执行节点设为「${nodeName}」。后续账号环境和工程资料保存在该节点。`" confirm-label="保存节点" :busy="saving" :error="error" @confirm="save" @cancel="confirming = false" />
  </section>
</template>

<style scoped>
.account-node-selector{display:grid;gap:16px;padding:22px;border:1px solid var(--ui-border);border-radius:12px;background:var(--ui-surface)}h2{font-size:var(--ui-font-card-title,16px);font-weight:600}p{font-size:var(--ui-font-small,13px);color:var(--ui-muted);overflow-wrap:anywhere}.assignment-fields{display:grid;grid-template-columns:1fr 1fr;gap:16px}footer{display:flex;justify-content:flex-end;gap:12px;flex-wrap:wrap}.assignment-error{color:var(--ui-danger)}@media(max-width:600px){.assignment-fields{grid-template-columns:1fr}.account-node-selector{padding:18px}}
</style>
