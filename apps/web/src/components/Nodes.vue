<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { api, type Account } from '../api';
import { useToast } from '../composables/useToast';
import { Button } from './ui/button';
import { PageHeader } from './ui/page-header';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Server, Plus, RefreshCw, ShieldCheck, Trash2, Pencil, Globe, Users, AlertCircle } from './ui/icon';
import { ChoiceSelect, NumberInput } from './ui/controls';
import { ModalDialog } from './ui/modal';
import { OverviewCard, OverviewGrid } from './ui/overview';
import { EntityBlock, EntityCard } from './ui/entity-card';
import { IconTile } from './ui/icon-tile';
import { Badge } from './ui/badge';
import { ConfirmationDialog } from './ui/feedback';
import { nodeApi, type ExecutionNode, type NodeHostKey } from './runtime/nodeApi';
import AccountNodeSelector from './runtime/AccountNodeSelector.vue';
import '../nodes.css';

const { show: toast } = useToast();
const rows = ref<ExecutionNode[]>([]), loading = ref(false), error = ref('');
type AgyAccount = Pick<Account, 'id' | 'name' | 'email' | 'status'>;
const agyAccounts = ref<AgyAccount[] | null>(null), agyError = ref('');
const synchronizing = ref(false);
const pending = reactive(new Set<number>());
const editor = ref(false), saving = ref(false), probing = ref(false), formError = ref('');
const name = ref(''), host = ref(''), port = ref<number | string>(22), username = ref('root');
const dataRoot = ref('/srv/flower2api-node'), privateKey = ref(''), selectedKey = ref(''), verified = ref(false);
const authMethod = ref<'private_key' | 'password'>('private_key'), password = ref('');
const authenticationOptions = [{ value: 'private_key', label: 'SSH 私钥' }, { value: 'password', label: 'SSH 密码' }];
const keys = ref<NodeHostKey[]>([]), deleting = ref<ExecutionNode | null>(null), deleteError = ref('');
const installing = ref<ExecutionNode | null>(null), installError = ref('');
const renaming = ref<ExecutionNode | null>(null), newName = ref(''), renameError = ref('');
// 关闭淡出期间 renaming 已清空，说明沿用打开时的地址，避免显示空字段。
const renameAddress = ref('');
const options = computed(() => keys.value.map(key => ({ value: key.key, label: `${key.algorithm} · ${key.sha256}` })));
const selectedFingerprint = computed(() => keys.value.find(key => key.key === selectedKey.value)?.sha256);
let alive = true, loadGeneration = 0, probeGeneration = 0;
let listRequest: AbortController | undefined, probeRequest: AbortController | undefined, agyRequest: AbortController | undefined;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;

/** 保留已有列表并拒绝旧请求覆盖。@param background 沿已建立的会话轮询安装状态。@return 刷新完成。 */
async function load(background = false): Promise<void> {
  if (refreshTimer) clearTimeout(refreshTimer);
  const generation = ++loadGeneration;
  listRequest?.abort(); listRequest = new AbortController(); loading.value = true; error.value = '';
  try {
    if (!background) await api.openRuntime();
    if (!alive || generation !== loadGeneration) return;
    const result = await nodeApi.list(listRequest.signal);
    if (alive && generation === loadGeneration) rows.value = result.items;
  } catch (cause) {
    if (alive && generation === loadGeneration && !listRequest.signal.aborted) error.value = (cause as Error).message;
  } finally {
    if (alive && generation === loadGeneration) {
      loading.value = false;
      const syncing = rows.value.some(node => node.removal?.state === 'removing' || node.preparation?.state === 'preparing' || node.preparation?.phase === 'waiting');
      if (syncing || rows.value.some(node => node.kind === 'ssh' && node.preparation)) {
        refreshTimer = setTimeout(() => { void load(true); }, syncing ? 3000 : 15000);
      }
    }
  }
}
/** 读取网关正式反重力账号，并使用完整列表计算节点归属。@return 刷新完成。 */
async function loadAgyAccounts(): Promise<void> {
  agyRequest?.abort();
  const controller = new AbortController();
  agyRequest = controller;
  agyError.value = '';
  const accounts = new Map<number, AgyAccount>();
  try {
    let page = 1;
    while (!controller.signal.aborted) {
      const result = await api.listAccounts(page, 100, '', '', controller.signal, 'antigravity');
      if (controller.signal.aborted) return;
      for (const { id, name, email, status, platform } of result.data) {
        if (platform === 'antigravity') accounts.set(id, { id, name, email, status });
      }
      if (page >= result.total_pages) break;
      page++;
    }
    if (alive && !controller.signal.aborted) agyAccounts.value = [...accounts.values()];
  } catch {
    if (alive && !controller.signal.aborted) agyError.value = '反重力账号归属读取失败，请刷新列表';
  }
}
/** 刷新节点与正式账号选项。@return 无。 */
function refresh(): void {
  void load();
  void loadAgyAccounts();
}
/** 节点的 account_count 已由后端计入反重力账号归属，直接求和，避免前端重复累加。 */
const totalAccounts = computed(() => rows.value.reduce((total, node) => total + node.account_count, 0));
type Attention = 'connection' | 'component' | 'removal';
/** 待处理原因的单独说明与计数说明，顺序即说明行顺序。 */
const attentionLabels: Record<Attention, [string, string]> = {
  connection: ['需检查连接', '台需检查连接'], component: ['组件同步异常', '台组件异常'], removal: ['移除待重试', '台移除待重试'],
};
/**
 * 需管理员处理的原因，按 state() 的判定顺序取第一类。暂停接单是主动操作，同步中、移除中仍在后台推进，均不计入。
 * @param node 节点。@return 原因；无需处理时为 null。
 */
function attention(node: ExecutionNode): Attention | null {
  if (node.removal) return node.removal.state === 'needs_check' ? 'removal' : null;
  if (!node.enabled) return null;
  if (!node.observation || node.observation.stale || node.observation.state === 'unreachable') return 'connection';
  return node.preparation?.state === 'failed' || node.preparation?.state === 'needs_check' ? 'component' : null;
}
const remoteNodes = computed(() => rows.value.filter(node => node.kind === 'ssh'));
const attentionNodes = computed(() => rows.value.filter(node => attention(node)));
/** 只有一类原因时直接写原因，多类时逐类计数。 */
const attentionCaption = computed(() => {
  const counts = new Map<Attention, number>();
  for (const node of attentionNodes.value) {
    const reason = attention(node)!;
    counts.set(reason, (counts.get(reason) ?? 0) + 1);
  }
  if (!counts.size) return '全部正常';
  if (counts.size === 1) return attentionLabels[[...counts.keys()][0]!][0];
  return (Object.keys(attentionLabels) as Attention[]).filter(reason => counts.has(reason))
    .map(reason => `${counts.get(reason)} ${attentionLabels[reason][1]}`).join(' · ');
});
const remoteCaption = computed(() => {
  if (!remoteNodes.value.length) return '尚未添加';
  const count = remoteNodes.value.filter(node => attention(node)).length;
  return count ? `${count} 台待处理` : '全部正常';
});
/** 地址变化使旧公钥确认失效。@return 无。 */
function resetProbe(): void {
  probeGeneration++; probeRequest?.abort(); probing.value = false;
  keys.value = []; selectedKey.value = ''; verified.value = false;
}
watch([host, port], resetProbe);
watch(selectedKey, () => { verified.value = false; });
watch(authMethod, () => { privateKey.value = ''; password.value = ''; });
/** 清理离开的登记表单，认证材料随弹窗生命周期释放。@param open 新状态。@return 无。 */
function setEditor(open: boolean): void {
  if (saving.value) return;
  editor.value = open; formError.value = '';
  if (!open) { privateKey.value = ''; password.value = ''; resetProbe(); }
}
/** 仅探测当前目标的公钥，显式核对由管理员完成。@return 探测完成。 */
async function probe(): Promise<void> {
  resetProbe(); const generation = probeGeneration;
  probeRequest = new AbortController(); probing.value = true; formError.value = '';
  try {
    const result = await nodeApi.hostKeys(host.value.trim(), Number(port.value), probeRequest.signal);
    if (alive && generation === probeGeneration && editor.value) keys.value = result.items;
  } catch (cause) {
    if (alive && generation === probeGeneration && !probeRequest.signal.aborted) formError.value = (cause as Error).message;
  } finally { if (generation === probeGeneration) probing.value = false; }
}
/** 保存已核对身份的节点，认证材料随本次成功提交清空。@return 登记完成。 */
async function save(): Promise<void> {
  if (saving.value) return;
  if (!verified.value || !selectedFingerprint.value) { formError.value = '请先选择主机公钥并核对指纹'; return; }
  saving.value = true; formError.value = '';
  try {
    const authentication = authMethod.value === 'password'
      ? { auth_method: 'password' as const, password: password.value }
      : { auth_method: 'private_key' as const, private_key: privateKey.value };
    await nodeApi.register({ name: name.value.trim(), host: host.value.trim(), port: Number(port.value),
      username: username.value.trim(), data_root: dataRoot.value, host_key: selectedKey.value, ...authentication });
    privateKey.value = ''; password.value = ''; editor.value = false; resetProbe();
    if (alive) { toast('节点已登记，可以检查连接与资源', 'success'); await load(); }
  } catch (cause) { if (alive) formError.value = (cause as Error).message; }
  finally { saving.value = false; }
}
/** 按原配置版本操作节点，迟到结果通过刷新读取权威。@param node 原节点。@param operation 动作。@return 完成。 */
async function operate(node: ExecutionNode, operation: 'check' | 'enable'): Promise<void> {
  if (pending.has(node.id)) return;
  pending.add(node.id);
  try {
    const result = operation === 'check' ? await nodeApi.check(node) : await nodeApi.enable(node, !node.enabled);
    if (alive) { rows.value = rows.value.map(row => row.id === result.id ? result : row); }
  } catch (cause) { if (alive) toast((cause as Error).message); }
  finally { pending.delete(node.id); }
}
/** 打开改名表单并冻结当前配置版本。@param node 当前节点。@return 无。 */
function openRename(node: ExecutionNode): void {
  newName.value = node.name; renameError.value = ''; renameAddress.value = `${node.username}@${node.host}:${node.port}`; renaming.value = node;
}
/** 保存节点显示名称。@return 更新完成。 */
async function rename(): Promise<void> {
  const node = renaming.value;
  if (!node || pending.has(node.id) || !newName.value.trim()) return;
  pending.add(node.id); renameError.value = '';
  try {
    await nodeApi.rename(node, newName.value.trim());
    if (alive) { renaming.value = null; await load(); }
  } catch (cause) {
    if (alive) { renameError.value = (cause as Error).message; void load(true); }
  } finally { pending.delete(node.id); }
}
/** 提交原节点清理或续接已经确认的移除。@param node 当前节点。@return 已读取最新状态。 */
async function remove(node = deleting.value): Promise<void> {
  if (!node || pending.has(node.id)) return;
  pending.add(node.id); deleteError.value = '';
  try {
    const removal = await nodeApi.remove(node);
    if (alive) {
      deleting.value = null;
      rows.value = rows.value.map(row => row.id === node.id ? { ...row, enabled: false, removal } : row);
      await load(true);
    }
  } catch (cause) {
    if (alive) {
      if (deleting.value) deleteError.value = (cause as Error).message;
      else toast((cause as Error).message);
      void load(true);
    }
  }
  finally { pending.delete(node.id); }
}
/** 管理员确认影响后安装远程执行组件。@return 安装完成。 */
async function install(): Promise<void> {
  const node = installing.value;
  if (!node || pending.has(node.id)) return;
  pending.add(node.id); installError.value = '';
  try {
    const result = await nodeApi.prepare(node);
    if (alive) {
      rows.value = rows.value.map(row => row.id === result.id ? result : row); installing.value = null;
      toast(result.preparation?.state === 'prepared' ? '节点执行组件已就绪' : '已提交后台安装，可离开页面后查看状态', 'success');
      void load(true);
    }
  } catch (cause) {
    if (alive) { installError.value = (cause as Error).message; void load(true); }
  }
  finally { pending.delete(node.id); }
}
/** 统一同步由后台逐台推进，离页后仍可查看原状态。@return 受理完成。 */
async function synchronize(): Promise<void> {
  if (synchronizing.value) return;
  synchronizing.value = true;
  try {
    const result = await nodeApi.synchronize();
    if (alive) { rows.value = result.items; toast('节点同步已提交，可离开页面后查看进度', 'success'); void load(true); }
  } catch (cause) { if (alive) toast((cause as Error).message); }
  finally { synchronizing.value = false; }
}
/** 将持久阶段显示为实际处理进度。@param node 当前节点。@return 阶段说明。 */
function preparationState(node: ExecutionNode): string {
  if (node.removal) return {
    checking: '核对远程归属', retiring_components: '移除远程组件', clearing_data: '清理远程数据', completed: '已移除',
  }[node.removal.phase];
  const phase = node.preparation?.phase;
  const labels: Record<string, string> = { checking: '核对现有组件', prefetching: '准备新镜像', draining: '等待原工作完成',
    waiting: '等待同步', waiting_for_platform: '已停止，等待平台切换', stopping: '停止原组件', backing_up: '备份节点资料', switching: '切换组件', restoring: '恢复原账号环境', ready: '已就绪' };
  return (phase && labels[phase]) || (node.preparation ?
    { preparing: '后台同步中', prepared: '已就绪', failed: '同步失败', needs_check: '待核对' }[node.preparation.state] : '待安装');
}
/** 保留未知资源与真实零值的区别。@param value 字节数。@return 可读容量。 */
function bytes(value: number | null | undefined): string {
  if (value == null) return '未采集';
  return `${(value / 1024 ** 3).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} GiB`;
}
/** 来源时间与状态分别显示。@param node 节点。@return 连接说明。 */
function state(node: ExecutionNode): string {
  if (node.removal) return { removing: '移除中', needs_check: '移除待重试', completed: '已移除' }[node.removal.state];
  if (!node.enabled) return '已暂停接单';
  if (!node.observation) return '待检查';
  if (node.observation.stale) return '观测已过期';
  return node.observation.state === 'reachable' ? '连接正常' : '连接异常';
}
/** 状态徽标色调，与 state() 的判定顺序一致：待检查与观测过期为琥珀色。@param node 节点。@return Badge 变体。 */
function stateVariant(node: ExecutionNode): 'success' | 'warning' | 'destructive' | 'info' | 'secondary' {
  if (node.removal) return ({ removing: 'info', needs_check: 'destructive', completed: 'secondary' } as const)[node.removal.state];
  if (!node.enabled) return 'secondary';
  if (!node.observation || node.observation.stale) return 'warning';
  return node.observation.state === 'reachable' ? 'success' : 'destructive';
}
onMounted(refresh);
onUnmounted(() => { alive = false; loadGeneration++; if (refreshTimer) clearTimeout(refreshTimer); listRequest?.abort(); agyRequest?.abort(); resetProbe(); privateKey.value = ''; password.value = ''; });
</script>

<template>
  <section class="nodes-page">
    <PageHeader title="节点管理" description="管理执行服务器、组件状态与账号运行位置。"><template #actions><div class="nodes-actions"><Button variant="outline" :disabled="synchronizing" @click="synchronize">{{ synchronizing ? '提交中…' : '同步全部节点' }}</Button><Button variant="outline" :disabled="loading" @click="refresh"><RefreshCw :size="16" />刷新列表</Button><Button @click="setEditor(true)"><Plus :size="16" />添加节点</Button></div></template></PageHeader>
    <p v-if="error" class="nodes-error" role="alert">{{ error }}</p>
    <p v-if="agyError" class="nodes-error" role="alert">{{ agyError }}</p>
    <p v-if="loading && !rows.length" class="nodes-loading" role="status">正在读取节点…</p>
    <OverviewGrid v-if="rows.length" class="nodes-overview">
      <OverviewCard label="节点" :value="rows.length" :caption="`${rows.length - remoteNodes.length} 台本机 · ${remoteNodes.length} 台远程`"><template #icon><Server /></template></OverviewCard>
      <OverviewCard label="远程服务器" :value="remoteNodes.length" :caption="remoteCaption" tone="info"><template #icon><Globe /></template></OverviewCard>
      <OverviewCard label="归属账号" :value="totalAccounts" caption="已分配执行位置" tone="success"><template #icon><Users /></template></OverviewCard>
      <OverviewCard label="待处理" :value="attentionNodes.length" :caption="attentionCaption" tone="warning"><template #icon><AlertCircle /></template></OverviewCard>
    </OverviewGrid>
    <div class="nodes-grid">
      <EntityCard v-for="node in rows" :key="node.id" class="node-card" :title="node.name">
        <template #media><IconTile size="lg"><Server /></IconTile></template>
        <template #subtitle><span :class="{ 'node-address': node.kind === 'ssh' }">{{ node.kind === 'local' ? '默认本机节点' : `${node.username}@${node.host}:${node.port}` }}</span></template>
        <template #status><Badge dot :variant="stateVariant(node)" class="node-state">{{ state(node) }}</Badge></template>
        <dl class="node-resources">
          <div><dt>CPU</dt><dd :class="{ 'is-empty': node.observation?.host_cpus == null }">{{ node.observation?.host_cpus != null ? `${node.observation.host_cpus} 核` : '未采集' }}</dd></div>
          <div><dt>可用内存</dt><dd :class="{ 'is-empty': node.observation?.memory?.MemAvailable == null }">{{ bytes(node.observation?.memory?.MemAvailable) }}</dd></div>
          <div><dt>可用磁盘</dt><dd :class="{ 'is-empty': node.observation?.disk_available_bytes == null }">{{ bytes(node.observation?.disk_available_bytes) }}</dd></div>
          <div><dt>归属账号</dt><dd>{{ node.account_count }}</dd></div>
        </dl>
        <EntityBlock class="node-meta">
          <div><span>最近检查</span><time>{{ node.observation && node.observation.observed_at > 0 ? new Date(node.observation.observed_at * 1000).toLocaleString('zh-CN') : '尚未检查' }}</time></div>
          <div><span>Docker</span><b>{{ node.observation?.docker_version ?? '未采集' }}</b></div>
          <div v-if="node.kind === 'ssh'"><span>运行组件</span><b>{{ preparationState(node) }}</b></div>
        </EntityBlock>
        <p v-if="node.preparation?.target_release && node.preparation.target_release !== (node.preparation.current_release || node.preparation.release)" class="node-note">{{ node.preparation.current_release || node.preparation.release || '首次安装' }} → {{ node.preparation.target_release }}</p>
        <p v-if="node.observation?.reason" class="node-alert" role="status">{{ node.observation.reason }}</p>
        <p v-if="node.removal?.reason || (!node.removal && node.preparation?.reason)" class="node-alert" role="status">{{ node.removal?.reason || node.preparation?.reason }}</p>
        <details v-if="node.kind === 'ssh'" class="node-identity"><summary><ShieldCheck :size="14" />主机身份与版本 ›</summary><p>组件版本：<code>{{ node.preparation?.release || '待安装' }}</code></p><p><code>{{ node.host_key_sha256 }}</code></p><p>认证方式：{{ node.auth_method === 'password' ? 'SSH 密码' : 'SSH 私钥' }}</p><p>节点数据目录：<code>{{ node.data_root }}</code></p></details>
        <div class="node-actions">
          <template v-if="!node.removal">
            <Button variant="outline" size="sm" :disabled="pending.has(node.id)" @click="operate(node, 'check')"><RefreshCw :size="14" />检查连接</Button>
            <Button v-if="node.kind === 'ssh'" variant="outline" size="sm" :disabled="pending.has(node.id) || !node.enabled || node.preparation?.state === 'preparing'" @click="installError = ''; installing = node">{{ node.preparation?.state === 'preparing' ? '后台同步中…' : node.preparation?.state === 'prepared' ? '检查并同步组件' : '准备运行组件' }}</Button>
            <Button variant="outline" size="sm" :disabled="pending.has(node.id)" @click="operate(node, 'enable')">{{ node.enabled ? '暂停接单' : '恢复接单' }}</Button>
            <Button v-if="node.kind === 'ssh'" variant="ghost" size="sm" :disabled="pending.has(node.id) || node.preparation?.state === 'preparing'" @click="openRename(node)"><Pencil :size="14" />改名</Button>
            <Button v-if="node.kind === 'ssh'" variant="destructive-ghost" size="sm" class="node-remove" :title="node.account_count ? '请先迁移归属账号' : undefined" :disabled="pending.has(node.id) || node.account_count > 0 || node.preparation?.state === 'preparing'" @click="deleteError = ''; deleting = node"><Trash2 :size="14" />移除</Button>
          </template>
          <Button v-else-if="node.removal.state === 'needs_check'" variant="outline" size="sm" :disabled="pending.has(node.id)" @click="remove(node)"><RefreshCw :size="14" />重试移除</Button>
          <span v-else class="node-note" role="status">{{ node.removal.state === 'removing' ? '正在后台移除，可离开此页面' : '已清理远程组件和数据' }}</span>
        </div>
      </EntityCard>
    </div>
    <AccountNodeSelector v-if="rows.length" :nodes="rows" :agy-accounts="agyAccounts ?? []" @changed="load" />
    <ModalDialog :open="editor" class="node-editor" title="添加 SSH 节点" description="服务器需要具备 SSH、Python 3 和 Docker。使用具有对应 Docker 权限的专用账号。" :width="640" :show-close-button="!saving" @update:open="setEditor" @escape-key-down="(event: Event) => { if (saving) event.preventDefault(); }" @interact-outside="(event: Event) => { if (saving) event.preventDefault(); }">
      <form id="node-editor-form" class="node-form" @submit.prevent="save">
        <div class="node-form-grid"><label class="node-field" for="node-name">节点名称<Input id="node-name" v-model="name" required maxlength="80" :disabled="saving" /></label><label class="node-field" for="node-host">服务器地址<Input id="node-host" v-model="host" required placeholder="IP 或主机名" :disabled="saving" /></label><NumberInput v-model="port" label="SSH 端口" :min="1" :max="65535" required :disabled="saving" /><label class="node-field" for="node-username">SSH 用户<Input id="node-username" v-model="username" required autocomplete="off" :disabled="saving" /></label></div>
        <label class="node-field" for="node-data-root">独立数据目录<Input id="node-data-root" v-model="dataRoot" required :disabled="saving" /></label>
        <div class="node-fingerprint"><Button type="button" variant="outline" :disabled="saving || probing || !host.trim() || !port" @click="probe">{{ probing ? '正在探测…' : '探测主机公钥' }}</Button><ChoiceSelect v-if="keys.length" v-model="selectedKey" label="服务器主机公钥" :options="options" :disabled="saving" placeholder="选择已核对的公钥" /><code v-if="selectedFingerprint">{{ selectedFingerprint }}</code><label v-if="selectedFingerprint" class="node-verify"><input v-model="verified" type="checkbox" :disabled="saving" />我已通过可信渠道核对这个主机指纹</label></div>
        <ChoiceSelect v-model="authMethod" label="SSH 认证方式" :options="authenticationOptions" :disabled="saving" />
        <label v-if="authMethod === 'private_key'" class="node-field" for="node-private-key">专用 SSH 私钥<Textarea id="node-private-key" v-model="privateKey" required autocomplete="off" :spellcheck="false" :disabled="saving" rows="5" placeholder="粘贴专用无口令私钥" /></label>
        <label v-else class="node-field" for="node-password">SSH 密码<Input id="node-password" v-model="password" type="password" required maxlength="4096" autocomplete="new-password" :disabled="saving" /></label>
        <p class="node-note">认证材料由管理中心以受保护文件保存，关闭此窗口后清空输入。</p>
        <p v-if="formError" class="nodes-error" role="alert">{{ formError }}</p>
      </form>
      <template #footer><Button type="button" variant="outline" :disabled="saving" @click="setEditor(false)">取消</Button><Button type="submit" form="node-editor-form" :disabled="saving || !verified">{{ saving ? '正在登记…' : '登记节点' }}</Button></template>
    </ModalDialog>
    <ModalDialog :open="!!renaming" class="node-rename" title="修改节点名称" :description="renameAddress" :width="420" :show-close-button="!renaming || !pending.has(renaming.id)" @update:open="(open: boolean) => { if (!open && renaming && !pending.has(renaming.id)) renaming = null; }">
      <form id="node-rename-form" class="node-form" @submit.prevent="rename">
        <label class="node-field" for="node-new-name">节点名称<Input id="node-new-name" v-model="newName" required maxlength="80" :disabled="!!renaming && pending.has(renaming.id)" /></label>
        <p v-if="renameError" class="nodes-error" role="alert">{{ renameError }}</p>
      </form>
      <template #footer><Button type="button" variant="outline" :disabled="!!renaming && pending.has(renaming.id)" @click="renaming = null">取消</Button><Button type="submit" form="node-rename-form" :disabled="!newName.trim() || (!!renaming && pending.has(renaming.id))">保存名称</Button></template>
    </ModalDialog>
    <ConfirmationDialog :open="!!deleting" title="移除节点" :message="`将停止并删除「${deleting?.name ?? ''}」的远程组件，清空 ${deleting?.data_root ?? ''} 中本节点的日志、产物和其他专属数据。中央操作历史会保留。`" confirm-label="移除节点" danger :busy="!!deleting && pending.has(deleting.id)" :error="deleteError" @confirm="remove()" @cancel="deleting = null" />
    <ConfirmationDialog :open="!!installing" title="准备节点运行组件" :message="`将在「${installing?.name ?? ''}」核对现有组件与当前批次，自动完成首次安装或更新。需要换批时先等待原工作完成，再原地切换组件并恢复账号。任务在后台执行，可离开页面后查看进度。`" confirm-label="开始准备" :busy="!!installing && pending.has(installing.id)" :error="installError" @confirm="install" @cancel="installing = null" />
  </section>
</template>
