<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { api, type Account } from '../api';
import { useToast } from '../composables/useToast';
import { Button } from './ui/button';
import { PageHeader } from './ui/page-header';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Server, Plus, RefreshCw, ShieldCheck, Trash2, Pencil } from './ui/icon';
import { ChoiceSelect, NumberInput } from './ui/controls';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { ConfirmationDialog } from './ui/feedback';
import { nodeApi, type ExecutionNode, type NodeHostKey } from './runtime/nodeApi';
import AccountNodeSelector from './runtime/AccountNodeSelector.vue';

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
/** 使用同一份正式账号列表更新归属选择和节点计数。@return 无。 */
function refresh(): void {
  void load();
  void loadAgyAccounts();
}
/** 汇总本机反重力账号和已有任务账号归属。@param node 节点。@return 归属数量或待核对占位。 */
function accountCount(node: ExecutionNode): number | string {
  if (node.kind !== 'local') return node.account_count;
  return agyAccounts.value === null ? '—' : node.account_count + agyAccounts.value.length;
}
const totalAccounts = computed(() => agyAccounts.value === null ? '—'
  : rows.value.reduce((total, node) => total + node.account_count, agyAccounts.value.length));
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
  newName.value = node.name; renameError.value = ''; renaming.value = node;
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
  const labels: Record<string, string> = { checking: '核对现有组件', draining: '等待原工作完成',
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
onMounted(refresh);
onUnmounted(() => { alive = false; loadGeneration++; if (refreshTimer) clearTimeout(refreshTimer); listRequest?.abort(); agyRequest?.abort(); resetProbe(); privateKey.value = ''; password.value = ''; });
</script>

<template>
  <section class="nodes-page">
    <PageHeader title="节点管理" description="管理执行服务器、组件状态与账号运行位置。"><template #actions><div class="nodes-actions"><Button variant="outline" :disabled="synchronizing" @click="synchronize">{{ synchronizing ? '提交中…' : '同步全部节点' }}</Button><Button variant="outline" :disabled="loading" @click="refresh"><RefreshCw :size="16" />刷新列表</Button><Button @click="setEditor(true)"><Plus :size="16" />添加节点</Button></div></template></PageHeader>
    <p v-if="error" class="nodes-error" role="alert">{{ error }}</p>
    <p v-if="agyError" class="nodes-error" role="alert">{{ agyError }}</p>
    <p v-if="loading && !rows.length" role="status">正在读取节点…</p>
    <div v-if="rows.length" class="nodes-summary"><span><strong>{{ rows.length }}</strong> 个节点</span><span><strong>{{ rows.filter(node => node.kind === 'ssh').length }}</strong> 台远程服务器</span><span><strong>{{ totalAccounts }}</strong> 个归属账号</span></div>
    <div class="nodes-grid">
      <article v-for="node in rows" :key="node.id" class="node-card">
        <header><span class="node-icon"><Server :size="20" /></span><div><h2>{{ node.name }}</h2><p>{{ node.kind === 'local' ? '默认本机节点' : `${node.username}@${node.host}:${node.port}` }}</p></div><span class="node-state" :class="{ failed: node.observation?.state === 'unreachable', muted: !node.enabled || node.observation?.stale }">{{ state(node) }}</span></header>
        <dl class="node-resources"><div><dt>CPU</dt><dd>{{ node.observation?.host_cpus ?? '未采集' }}<small v-if="node.observation?.host_cpus != null"> 核</small></dd></div><div><dt>可用内存</dt><dd>{{ bytes(node.observation?.memory?.MemAvailable) }}</dd></div><div><dt>可用磁盘</dt><dd>{{ bytes(node.observation?.disk_available_bytes) }}</dd></div><div><dt>归属账号</dt><dd>{{ accountCount(node) }}</dd></div></dl>
        <p v-if="node.observation?.reason" class="nodes-error" role="status">{{ node.observation.reason }}</p>
        <div class="node-meta"><span>最近检查</span><time>{{ node.observation && node.observation.observed_at > 0 ? new Date(node.observation.observed_at * 1000).toLocaleString('zh-CN') : '尚未检查' }}</time><span>Docker</span><span>{{ node.observation?.docker_version ?? '未采集' }}</span><template v-if="node.kind === 'ssh'"><span>运行组件</span><span>{{ preparationState(node) }}</span></template></div>
        <p v-if="node.preparation?.target_release && node.preparation.target_release !== (node.preparation.current_release || node.preparation.release)" class="node-note">{{ node.preparation.current_release || node.preparation.release || '首次安装' }} → {{ node.preparation.target_release }}</p>
        <p v-if="node.removal?.reason || (!node.removal && node.preparation?.reason)" class="nodes-error" role="status">{{ node.removal?.reason || node.preparation?.reason }}</p>
        <details v-if="node.kind === 'ssh'" class="node-identity"><summary><ShieldCheck :size="14" />主机身份与版本</summary><p>组件版本：<code>{{ node.preparation?.release || '待安装' }}</code></p><p><code>{{ node.host_key_sha256 }}</code></p><p>认证方式：{{ node.auth_method === 'password' ? 'SSH 密码' : 'SSH 私钥' }}</p><p>节点数据目录：<code>{{ node.data_root }}</code></p></details>
        <footer>
          <template v-if="!node.removal">
            <Button variant="outline" :disabled="pending.has(node.id)" @click="operate(node, 'check')"><RefreshCw :size="14" />检查连接</Button>
            <Button v-if="node.kind === 'ssh'" variant="outline" :disabled="pending.has(node.id) || !node.enabled || node.preparation?.state === 'preparing'" @click="installError = ''; installing = node">{{ node.preparation?.state === 'preparing' ? '后台同步中…' : node.preparation?.state === 'prepared' ? '检查并同步组件' : '准备运行组件' }}</Button>
            <Button variant="outline" :disabled="pending.has(node.id)" @click="operate(node, 'enable')">{{ node.enabled ? '暂停接单' : '恢复接单' }}</Button>
            <Button v-if="node.kind === 'ssh'" variant="ghost" :disabled="pending.has(node.id) || node.preparation?.state === 'preparing'" @click="openRename(node)"><Pencil :size="14" />改名</Button>
            <Button v-if="node.kind === 'ssh'" variant="ghost" :title="node.account_count ? '请先迁移归属账号' : undefined" :disabled="pending.has(node.id) || node.account_count > 0 || node.preparation?.state === 'preparing'" @click="deleteError = ''; deleting = node"><Trash2 :size="14" />移除</Button>
          </template>
          <Button v-else-if="node.removal.state === 'needs_check'" variant="outline" :disabled="pending.has(node.id)" @click="remove(node)"><RefreshCw :size="14" />重试移除</Button>
          <span v-else class="node-note" role="status">{{ node.removal.state === 'removing' ? '正在后台移除，可离开此页面' : '已清理远程组件和数据' }}</span>
        </footer>
      </article>
    </div>
    <AccountNodeSelector v-if="rows.length" :nodes="rows" :agy-accounts="agyAccounts ?? []" @changed="load" />
    <Dialog :open="editor" @update:open="setEditor"><DialogContent class="node-editor" :show-close-button="!saving" @escape-key-down="event => { if (saving) event.preventDefault(); }" @interact-outside="event => { if (saving) event.preventDefault(); }"><DialogHeader><DialogTitle>添加 SSH 节点</DialogTitle><DialogDescription>服务器需要具备 SSH、Python 3 和 Docker。使用具有对应 Docker 权限的专用账号。</DialogDescription></DialogHeader>
      <form class="node-form" @submit.prevent="save"><div class="node-form-grid"><label>节点名称<Input v-model="name" required maxlength="80" :disabled="saving" /></label><label>服务器地址<Input v-model="host" required placeholder="IP 或主机名" :disabled="saving" /></label><NumberInput v-model="port" label="SSH 端口" :min="1" :max="65535" required :disabled="saving" /><label>SSH 用户<Input v-model="username" required autocomplete="off" :disabled="saving" /></label></div><label>独立数据目录<Input v-model="dataRoot" required :disabled="saving" /></label>
        <div class="node-fingerprint"><Button type="button" variant="outline" :disabled="saving || probing || !host.trim() || !port" @click="probe">{{ probing ? '正在探测…' : '探测主机公钥' }}</Button><ChoiceSelect v-if="keys.length" v-model="selectedKey" label="服务器主机公钥" :options="options" :disabled="saving" placeholder="选择已核对的公钥" /><code v-if="selectedFingerprint">{{ selectedFingerprint }}</code><label v-if="selectedFingerprint" class="node-verify"><input v-model="verified" type="checkbox" :disabled="saving" />我已通过可信渠道核对这个主机指纹</label></div>
        <ChoiceSelect v-model="authMethod" label="SSH 认证方式" :options="authenticationOptions" :disabled="saving" />
        <label v-if="authMethod === 'private_key'">专用 SSH 私钥<Textarea v-model="privateKey" required autocomplete="off" :spellcheck="false" :disabled="saving" rows="5" placeholder="粘贴专用无口令私钥" /></label>
        <label v-else>SSH 密码<Input v-model="password" type="password" required maxlength="4096" autocomplete="new-password" :disabled="saving" /></label><p class="node-note">认证材料由管理中心以受保护文件保存，关闭此窗口后清空输入。</p><p v-if="formError" class="nodes-error" role="alert">{{ formError }}</p><footer><Button type="button" variant="outline" :disabled="saving" @click="setEditor(false)">取消</Button><Button type="submit" :disabled="saving || !verified">{{ saving ? '正在登记…' : '登记节点' }}</Button></footer>
      </form>
    </DialogContent></Dialog>
    <Dialog :open="!!renaming" @update:open="open => { if (!open && renaming && !pending.has(renaming.id)) renaming = null; }">
      <DialogContent class="node-rename" :show-close-button="!renaming || !pending.has(renaming.id)">
        <DialogHeader><DialogTitle>修改节点名称</DialogTitle><DialogDescription>{{ renaming?.username }}@{{ renaming?.host }}:{{ renaming?.port }}</DialogDescription></DialogHeader>
        <form class="node-form" @submit.prevent="rename">
          <label>节点名称<Input v-model="newName" required maxlength="80" :disabled="!!renaming && pending.has(renaming.id)" /></label>
          <p v-if="renameError" class="nodes-error" role="alert">{{ renameError }}</p>
          <footer><Button type="button" variant="outline" :disabled="!!renaming && pending.has(renaming.id)" @click="renaming = null">取消</Button><Button type="submit" :disabled="!newName.trim() || (!!renaming && pending.has(renaming.id))">保存名称</Button></footer>
        </form>
      </DialogContent>
    </Dialog>
    <ConfirmationDialog :open="!!deleting" title="移除节点" :message="`将停止并删除「${deleting?.name ?? ''}」的远程组件，清空 ${deleting?.data_root ?? ''} 中本节点的日志、产物和其他专属数据。中央操作历史会保留。`" confirm-label="移除节点" danger :busy="!!deleting && pending.has(deleting.id)" :error="deleteError" @confirm="remove()" @cancel="deleting = null" />
    <ConfirmationDialog :open="!!installing" title="准备节点运行组件" :message="`将在「${installing?.name ?? ''}」核对现有组件与当前批次，自动完成首次安装或更新。需要换批时先等待原工作完成，再原地切换组件并恢复账号。任务在后台执行，可离开页面后查看进度。`" confirm-label="开始准备" :busy="!!installing && pending.has(installing.id)" :error="installError" @confirm="install" @cancel="installing = null" />
  </section>
</template>

<style scoped>
.nodes-page{color:var(--foreground)}.nodes-actions,.node-card>header,.node-card>footer,.node-form>footer{display:flex;align-items:center;gap:12px}.nodes-actions{flex-wrap:wrap;max-width:100%}.node-card p{color:var(--muted-foreground);font-size:var(--ui-font-small)}.nodes-grid{margin-bottom:24px;display:grid;align-items:start;grid-template-columns:repeat(auto-fit,minmax(min(100%,390px),1fr));gap:20px}.node-card{background:var(--ui-surface,#fff);border:1px solid var(--ui-border,#e2e6ed);border-radius:12px;padding:20px;display:flex;flex-direction:column;gap:16px}.node-card h2{font-size:var(--ui-font-card);font-weight:650}.node-card>header>div{min-width:0}.node-card>header p{overflow-wrap:anywhere}.node-icon{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;background:var(--ui-accent-soft,#eee8f7);color:var(--ui-accent,#856b9e);flex-shrink:0}.node-state{margin-left:auto;padding:4px 8px;border-radius:6px;font-size:var(--ui-font-small);color:#39836a;background:#edf6f1;white-space:nowrap}.node-state.failed,.nodes-error{color:var(--ui-danger,#b45b67)}.node-state.muted{color:var(--ui-muted,#7d879a);background:var(--ui-field-surface,#f6f7fa)}.nodes-summary{display:flex;align-items:center;flex-wrap:wrap;gap:12px 24px;margin-bottom:24px;font-size:var(--ui-font-small);color:var(--muted-foreground)}.nodes-summary strong{font:650 var(--ui-font-heading) var(--font-mono);color:var(--foreground);margin-right:5px;font-variant-numeric:tabular-nums}.node-resources{display:grid;grid-template-columns:repeat(2,1fr);gap:20px}.node-resources dt,.node-meta{font-size:var(--ui-font-small);color:var(--ui-muted,#7d879a)}.node-resources dd{font-size:var(--ui-font-heading);margin-top:5px;font-variant-numeric:tabular-nums}.node-resources small{font-size:var(--ui-font-small)}.node-meta{display:grid;grid-template-columns:auto 1fr;gap:8px 16px}.node-meta>span:nth-child(even),.node-meta time{text-align:right;overflow-wrap:anywhere}.node-identity{font-size:var(--ui-font-small);border-top:1px solid var(--ui-border,#e2e6ed);padding-top:12px}.node-identity summary{cursor:pointer;display:flex;align-items:center;gap:8px}.node-identity p{margin-top:8px}.node-identity code,.node-fingerprint code{overflow-wrap:anywhere}.node-card>footer{flex-wrap:wrap;border-top:1px solid var(--ui-border,#e2e6ed);padding-top:16px}.node-form,.node-form label,.node-fingerprint{display:grid;gap:8px}.node-form{gap:18px}.node-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.node-form label{font-size:var(--ui-font-body)}.node-fingerprint{padding:14px;border:1px solid var(--ui-border,#e2e6ed);border-radius:8px}.node-fingerprint>button{justify-self:start}.node-form .node-verify{display:flex;align-items:flex-start;gap:8px}.node-verify input{margin-top:3px;accent-color:var(--ui-accent,#856b9e)}.node-note{overflow-wrap:anywhere;font-size:var(--ui-font-small);color:var(--ui-muted,#7d879a)}.node-form>footer{justify-content:flex-end}.nodes-error{font-size:var(--ui-font-body);overflow-wrap:anywhere}@media(max-width:600px){.node-form-grid{grid-template-columns:1fr}.node-card{padding:18px}}
</style>
<style>.node-editor,.node-rename{width:calc(100% - 32px);max-height:90dvh;overflow-y:auto}.node-editor{max-width:640px}.node-rename{max-width:420px}</style>
