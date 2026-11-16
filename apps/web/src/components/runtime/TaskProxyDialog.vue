<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { ProxyRoute } from '../../api';
import ProxyPicker from '../ProxyPicker.vue';
import { readTaskProxy, saveTaskProxy, type TaskProxySelection, type TaskProxySummary } from './taskProxyApi';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Globe, RefreshCw, AlertCircle } from '../ui/icon';

const props = defineProps<{ accountId: number; accountName?: string }>();
const emit = defineEmits<{ close: []; saved: [selection: TaskProxySelection] }>();
const snapshot = ref<TaskProxySelection>();
const choice = ref<ProxyRoute | null | undefined>();
const loading = ref(true), saving = ref(false), error = ref('');
let alive = true, generation = 0, request: AbortController | undefined;
const candidate = computed<TaskProxySummary | undefined>(() => choice.value === undefined ? snapshot.value?.current : choice.value === null ? { kind: 'direct', name: '直连', public_url: '', status: 'unknown', observation: null } : { ...choice.value, kind: 'directory' });
const changed = computed(() => choice.value !== undefined && (choice.value === null ? snapshot.value?.current.kind !== 'direct' : snapshot.value?.current.id !== choice.value.id || snapshot.value.current.revision !== choice.value.revision));
const expired = computed(() => !!candidate.value?.expires_at && Date.parse(candidate.value.expires_at) <= Date.now());
/** 重新读取时明确恢复服务端快照，丢弃过期选值。@return 读取完成。 */
async function load(): Promise<void> {
  if (saving.value) return;
  request?.abort(); request = new AbortController(); const current = ++generation;
  loading.value = true; error.value = '';
  try { const value = await readTaskProxy(props.accountId, request.signal); if (alive && current === generation) { snapshot.value = value; choice.value = undefined; } }
  catch (cause) { if (alive && current === generation && (cause as Error).name !== 'AbortError') error.value = (cause as Error).message; }
  finally { if (alive && current === generation) loading.value = false; }
}
/** 使用打开时版本保存，错误保留当前候选。@return 保存完成。 */
async function save(): Promise<void> {
  if (!snapshot.value || choice.value === undefined || saving.value || loading.value) return;
  const current = ++generation; request?.abort(); request = new AbortController(); saving.value = true; error.value = '';
  try { const value = await saveTaskProxy(snapshot.value, choice.value, request.signal); if (alive && current === generation) emit('saved', value); }
  catch (cause) { if (alive && current === generation && (cause as Error).name !== 'AbortError') error.value = (cause as Error).message; }
  finally { if (alive && current === generation) saving.value = false; }
}
/** 提交期间由业务回执收口窗口。@return 无。 */
function close(): void { if (!saving.value) emit('close'); }
onMounted(load);
onUnmounted(() => { alive = false; generation++; request?.abort(); });
</script>
<template>
  <Dialog open @update:open="value => { if (!value) close(); }"><DialogContent class="task-proxy-dialog" :show-close-button="!saving" @escape-key-down="event => { if (saving) event.preventDefault(); }" @interact-outside="event => { if (saving) event.preventDefault(); }">
    <DialogHeader><DialogTitle>切换代理<span v-if="snapshot"> · {{ accountName || snapshot.name }}</span></DialogTitle><DialogDescription>{{ snapshot?.gateway_account_id != null ? '保存后同步更新任务账号与关联的网关账号。' : '选择任务账号的代理线路，保存后生效。' }}</DialogDescription></DialogHeader>
    <div class="task-proxy-body" :aria-busy="loading || saving">
      <p v-if="loading" class="task-proxy-loading" role="status"><RefreshCw :size="18" class="fui-spinning" />正在读取当前线路…</p>
      <template v-else-if="snapshot">
        <p class="task-proxy-current">当前线路 <strong>{{ snapshot.current.name }}</strong></p>
        <ProxyPicker v-model="choice" :current-label="snapshot.current.name" :disabled="saving" help="搜索代理管理中的线路，或选择直连" />
        <section v-if="candidate" class="task-proxy-summary" aria-label="所选代理详情"><header><Globe :size="20" /><strong>{{ candidate.name }}</strong><span :data-status="candidate.status">{{ candidate.kind === 'direct' ? '直连' : candidate.status === 'ready' ? '可用' : candidate.status === 'failed' ? '检测失败' : '待检测' }}</span></header><code>{{ candidate.public_url || (candidate.kind === 'direct' ? '使用直接网络连接' : '线路配置待核对') }}</code><div v-if="candidate.observation" class="task-proxy-observation"><span>{{ candidate.observation.country || candidate.observation.country_code || '地区未知' }}<small>{{ candidate.observation.ip }}</small></span><strong>{{ candidate.observation.latency_ms }}<small> ms</small></strong></div><p v-if="candidate.observation">{{ candidate.status === 'ready' ? '最近检测' : '上次成功结果' }} · {{ new Date(candidate.observation.observed_at).toLocaleString() }}</p><p v-else>出口 IP、地区与延迟尚未观测<span v-if="candidate.checked_at"> · 最近检测 {{ new Date(candidate.checked_at).toLocaleString() }}</span></p><p v-if="candidate.kind === 'directory'" class="task-proxy-expiry" :class="{ expired }">{{ candidate.expires_at ? (expired ? '已过期 · ' : '到期时间 · ') + new Date(candidate.expires_at).toLocaleString() : '未设置到期时间' }}</p></section>
      </template>
      <div v-if="error" class="task-proxy-error" role="alert"><AlertCircle :size="18" /><span>{{ error }}</span><Button variant="outline" size="sm" :disabled="saving" @click="load">重新读取</Button></div>
    </div>
    <footer class="fui-confirm-footer"><Button variant="outline" :disabled="saving" @click="close">取消</Button><Button :disabled="loading || saving || !snapshot || !changed" @click="save">{{ saving ? '正在保存…' : '保存并切换' }}</Button></footer>
  </DialogContent></Dialog>
</template>
<style>
.task-proxy-dialog[data-slot=dialog-content]{width:min(600px,calc(100vw - 32px));max-width:none;max-height:calc(100dvh - 32px);padding:0;gap:0;border-radius:16px;display:flex;flex-direction:column;background:#fff;overflow:hidden}
.task-proxy-dialog>[data-slot=dialog-header]{padding:24px 28px;border-bottom:1px solid #ecebf2;text-align:left;gap:8px}.task-proxy-dialog [data-slot=dialog-title]{font-size:var(--ui-font-heading);line-height:1.5;padding-right:24px;overflow-wrap:anywhere}.task-proxy-dialog [data-slot=dialog-description]{font-size:var(--ui-font-small);line-height:1.7;color:#75849a}
.task-proxy-body{padding:24px 28px;min-height:0;overflow:auto;display:grid;gap:20px;font-size:var(--ui-font-body)}.task-proxy-current{color:#7d879a;display:flex;gap:12px;align-items:baseline}.task-proxy-current strong{color:#44516a;overflow-wrap:anywhere}
.task-proxy-summary{padding:18px;border:1px solid #e8e4ef;border-radius:12px;background:#faf9fc;min-width:0}.task-proxy-summary header{display:flex;gap:10px;align-items:center}.task-proxy-summary header strong{flex:1;min-width:0;overflow-wrap:anywhere;color:#44516a}.task-proxy-summary header>span{font-size:var(--ui-font-small);color:#648975;white-space:nowrap}.task-proxy-summary>code{display:block;overflow-wrap:anywhere;margin:12px 0;font-size:var(--ui-font-small);color:#72829a}.task-proxy-summary p{color:#7d879a;font-size:var(--ui-font-small);margin:12px 0 0}.task-proxy-observation{display:flex;justify-content:space-between;gap:20px}.task-proxy-observation span>small{display:block;margin-top:4px}.task-proxy-observation small{font-size:var(--ui-font-small);color:#7d879a}
.task-proxy-summary header>span[data-status=failed],.task-proxy-summary .task-proxy-expiry.expired{color:#ad4d65}.task-proxy-summary header>span[data-status=unknown]{color:#7d879a}
.task-proxy-error{display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap;color:#ad4d65;font-size:var(--ui-font-body);line-height:1.7}.task-proxy-error span{flex:1;min-width:150px;overflow-wrap:anywhere}.task-proxy-error svg{flex:none;margin-top:3px}.task-proxy-loading{display:flex;gap:10px;color:#75849a;align-items:center}
@media(max-width:600px){.task-proxy-body,.task-proxy-dialog>[data-slot=dialog-header]{padding:20px}}
</style>
