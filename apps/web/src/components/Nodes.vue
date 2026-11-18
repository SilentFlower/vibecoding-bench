<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { api } from '../api';
import { useToast } from '../composables/useToast';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Boxes, Plus, RefreshCw, ShieldCheck, Trash2 } from './ui/icon';
import { ChoiceSelect, NumberInput } from './ui/controls';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { ConfirmationDialog } from './ui/feedback';
import { nodeApi, type ExecutionNode, type NodeHostKey } from './runtime/nodeApi';
import AccountNodeSelector from './runtime/AccountNodeSelector.vue';

const { show: toast } = useToast();
const rows = ref<ExecutionNode[]>([]), loading = ref(false), error = ref('');
const pending = reactive(new Set<number>());
const editor = ref(false), saving = ref(false), probing = ref(false), formError = ref('');
const name = ref(''), host = ref(''), port = ref<number | string>(22), username = ref('root');
const dataRoot = ref('/srv/flower2api-node'), privateKey = ref(''), selectedKey = ref(''), verified = ref(false);
const authMethod = ref<'private_key' | 'password'>('private_key'), password = ref('');
const authenticationOptions = [{ value: 'private_key', label: 'SSH 私钥' }, { value: 'password', label: 'SSH 密码' }];
const keys = ref<NodeHostKey[]>([]), deleting = ref<ExecutionNode | null>(null), deleteError = ref('');
const installing = ref<ExecutionNode | null>(null), installError = ref('');
const options = computed(() => keys.value.map(key => ({ value: key.key, label: `${key.algorithm} · ${key.sha256}` })));
const selectedFingerprint = computed(() => keys.value.find(key => key.key === selectedKey.value)?.sha256);
let alive = true, loadGeneration = 0, probeGeneration = 0;
let listRequest: AbortController | undefined, probeRequest: AbortController | undefined;

/** 保留已有列表并拒绝旧请求覆盖。@return 刷新完成。 */
async function load(): Promise<void> {
  const generation = ++loadGeneration;
  listRequest?.abort(); listRequest = new AbortController(); loading.value = true; error.value = '';
  try {
    await api.openRuntime();
    if (!alive || generation !== loadGeneration) return;
    const result = await nodeApi.list(listRequest.signal);
    if (alive && generation === loadGeneration) rows.value = result.items;
  } catch (cause) {
    if (alive && generation === loadGeneration && !listRequest.signal.aborted) error.value = (cause as Error).message;
  } finally { if (alive && generation === loadGeneration) loading.value = false; }
}
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
/** 服务端核对引用后归档节点。@return 完成。 */
async function remove(): Promise<void> {
  const node = deleting.value;
  if (!node || pending.has(node.id)) return;
  pending.add(node.id); deleteError.value = '';
  try { await nodeApi.remove(node); if (alive) { deleting.value = null; await load(); } }
  catch (cause) { if (alive) deleteError.value = (cause as Error).message; }
  finally { pending.delete(node.id); }
}
/** 管理员确认影响后安装远程执行组件。@return 安装完成。 */
async function install(): Promise<void> {
  const node = installing.value;
  if (!node || pending.has(node.id)) return;
  pending.add(node.id); installError.value = '';
  try {
    const result = await nodeApi.prepare(node);
    if (alive) { rows.value = rows.value.map(row => row.id === result.id ? result : row); installing.value = null; toast('节点执行组件已就绪', 'success'); }
  } catch (cause) { if (alive) installError.value = (cause as Error).message; }
  finally { pending.delete(node.id); }
}
/** 保留未知资源与真实零值的区别。@param value 字节数。@return 可读容量。 */
function bytes(value: number | null | undefined): string {
  if (value == null) return '未采集';
  return `${(value / 1024 ** 3).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} GiB`;
}
/** 来源时间与状态分别显示。@param node 节点。@return 连接说明。 */
function state(node: ExecutionNode): string {
  if (!node.enabled) return '已暂停接单';
  if (!node.observation) return '待检查';
  if (node.observation.stale) return '观测已过期';
  return node.observation.state === 'reachable' ? '连接正常' : '连接异常';
}
onMounted(() => { void load(); });
onUnmounted(() => { alive = false; loadGeneration++; listRequest?.abort(); resetProbe(); privateKey.value = ''; password.value = ''; });
</script>

<template>
  <section class="nodes-page">
    <header class="nodes-heading"><div><p class="nodes-eyebrow">执行资源</p><h1>节点管理</h1><p>集中查看服务器，由你决定账号环境的执行位置。</p></div><div class="nodes-actions"><Button variant="outline" :disabled="loading" @click="load"><RefreshCw :size="16" />刷新列表</Button><Button @click="setEditor(true)"><Plus :size="16" />添加节点</Button></div></header>
    <p v-if="error" class="nodes-error" role="alert">{{ error }}</p>
    <p v-if="loading && !rows.length" role="status">正在读取节点…</p>
    <AccountNodeSelector v-if="rows.length" :nodes="rows" @changed="load" />
    <div class="nodes-grid">
      <article v-for="node in rows" :key="node.id" class="node-card">
        <header><span class="node-icon"><Boxes :size="22" /></span><div><h2>{{ node.name }}</h2><p>{{ node.kind === 'local' ? '默认本机节点' : `${node.username}@${node.host}:${node.port}` }}</p></div><span class="node-state" :class="{ failed: node.observation?.state === 'unreachable', muted: !node.enabled || node.observation?.stale }">{{ state(node) }}</span></header>
        <dl class="node-resources"><div><dt>CPU</dt><dd>{{ node.observation?.host_cpus ?? '未采集' }}<small v-if="node.observation?.host_cpus != null"> 核</small></dd></div><div><dt>可用内存</dt><dd>{{ bytes(node.observation?.memory?.MemAvailable) }}</dd></div><div><dt>可用磁盘</dt><dd>{{ bytes(node.observation?.disk_available_bytes) }}</dd></div><div><dt>归属账号</dt><dd>{{ node.account_count }}</dd></div></dl>
        <p v-if="node.observation?.reason" class="nodes-error" role="status">{{ node.observation.reason }}</p>
        <div class="node-meta"><span>最近检查</span><time>{{ node.observation && node.observation.observed_at > 0 ? new Date(node.observation.observed_at * 1000).toLocaleString('zh-CN') : '尚未检查' }}</time><span>Docker</span><span>{{ node.observation?.docker_version ?? '未采集' }}</span><template v-if="node.kind === 'ssh'"><span>运行组件</span><span>{{ node.preparation ? ({ preparing: '正在安装', prepared: '已就绪', failed: '安装失败', needs_check: '待核对' }[node.preparation.state]) : '待安装' }}</span><span v-if="node.preparation?.release">组件版本</span><span v-if="node.preparation?.release">{{ node.preparation.release }}</span></template></div>
        <p v-if="node.preparation?.reason" class="nodes-error" role="status">{{ node.preparation.reason }}</p>
        <details v-if="node.kind === 'ssh'" class="node-identity"><summary><ShieldCheck :size="14" />已确认的主机身份</summary><p><code>{{ node.host_key_sha256 }}</code></p><p>认证方式：{{ node.auth_method === 'password' ? 'SSH 密码' : 'SSH 私钥' }}</p><p>节点数据目录：<code>{{ node.data_root }}</code></p></details>
        <footer><Button variant="outline" :disabled="pending.has(node.id)" @click="operate(node, 'check')"><RefreshCw :size="14" />{{ pending.has(node.id) ? '处理中…' : '检查连接' }}</Button><Button v-if="node.kind === 'ssh'" variant="outline" :disabled="pending.has(node.id) || !node.enabled" @click="installError = ''; installing = node">准备运行组件</Button><Button variant="outline" :disabled="pending.has(node.id)" @click="operate(node, 'enable')">{{ node.enabled ? '暂停接单' : '恢复接单' }}</Button><Button v-if="node.kind === 'ssh'" variant="ghost" :disabled="pending.has(node.id) || node.account_count > 0" @click="deleteError = ''; deleting = node"><Trash2 :size="14" />移除</Button></footer>
      </article>
    </div>
    <Dialog :open="editor" @update:open="setEditor"><DialogContent class="node-editor" :show-close-button="!saving" @escape-key-down="event => { if (saving) event.preventDefault(); }" @interact-outside="event => { if (saving) event.preventDefault(); }"><DialogHeader><DialogTitle>添加 SSH 节点</DialogTitle><DialogDescription>服务器需要具备 SSH、Python 3 和 Docker。使用具有对应 Docker 权限的专用账号。</DialogDescription></DialogHeader>
      <form class="node-form" @submit.prevent="save"><div class="node-form-grid"><label>节点名称<Input v-model="name" required maxlength="80" :disabled="saving" /></label><label>服务器地址<Input v-model="host" required placeholder="IP 或主机名" :disabled="saving" /></label><NumberInput v-model="port" label="SSH 端口" :min="1" :max="65535" required :disabled="saving" /><label>SSH 用户<Input v-model="username" required autocomplete="off" :disabled="saving" /></label></div><label>独立数据目录<Input v-model="dataRoot" required :disabled="saving" /></label>
        <div class="node-fingerprint"><Button type="button" variant="outline" :disabled="saving || probing || !host.trim() || !port" @click="probe">{{ probing ? '正在探测…' : '探测主机公钥' }}</Button><ChoiceSelect v-if="keys.length" v-model="selectedKey" label="服务器主机公钥" :options="options" :disabled="saving" placeholder="选择已核对的公钥" /><code v-if="selectedFingerprint">{{ selectedFingerprint }}</code><label v-if="selectedFingerprint" class="node-verify"><input v-model="verified" type="checkbox" :disabled="saving" />我已通过可信渠道核对这个主机指纹</label></div>
        <ChoiceSelect v-model="authMethod" label="SSH 认证方式" :options="authenticationOptions" :disabled="saving" />
        <label v-if="authMethod === 'private_key'">专用 SSH 私钥<Textarea v-model="privateKey" required autocomplete="off" :spellcheck="false" :disabled="saving" rows="5" placeholder="粘贴专用无口令私钥" /></label>
        <label v-else>SSH 密码<Input v-model="password" type="password" required maxlength="4096" autocomplete="new-password" :disabled="saving" /></label><p class="node-note">认证材料由管理中心以受保护文件保存，关闭此窗口后清空输入。</p><p v-if="formError" class="nodes-error" role="alert">{{ formError }}</p><footer><Button type="button" variant="outline" :disabled="saving" @click="setEditor(false)">取消</Button><Button type="submit" :disabled="saving || !verified">{{ saving ? '正在登记…' : '登记节点' }}</Button></footer>
      </form>
    </DialogContent></Dialog>
    <ConfirmationDialog :open="!!deleting" title="移除节点" :message="`确认移除「${deleting?.name ?? ''}」？该操作归档节点登记并断开管理连接。远程容器与持久数据保留。`" confirm-label="移除节点" danger :busy="!!deleting && pending.has(deleting.id)" :error="deleteError" @confirm="remove" @cancel="deleting = null" />
    <ConfirmationDialog :open="!!installing" title="准备节点运行组件" :message="`将在「${installing?.name ?? ''}」创建独立数据目录、平台 Docker 网络和同批运行组件。镜像通过 SSH 通道传输，首次安装可能需要几分钟。`" confirm-label="开始准备" :busy="!!installing && pending.has(installing.id)" :error="installError" @confirm="install" @cancel="installing = null" />
  </section>
</template>

<style scoped>
.nodes-page{padding:28px;display:grid;gap:24px;color:var(--ui-text,#46546b)}.nodes-heading,.nodes-actions,.node-card>header,.node-card>footer,.node-form>footer{display:flex;align-items:center;gap:12px}.nodes-heading{justify-content:space-between;flex-wrap:wrap}.nodes-heading h1{font-size:28px;font-weight:650;margin:4px 0 8px}.nodes-heading p,.node-card p{color:var(--ui-muted,#7d879a);font-size:13px}.nodes-eyebrow{font-size:12px}.nodes-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,390px),1fr));gap:20px}.node-card{background:var(--ui-surface,#fff);border:1px solid var(--ui-border,#e2e6ed);border-radius:12px;padding:22px;display:grid;gap:20px}.node-card h2{font-size:16px;font-weight:600}.node-card>header>div{min-width:0}.node-card>header p{overflow-wrap:anywhere}.node-icon{color:var(--ui-accent,#856b9e);flex-shrink:0}.node-state{margin-left:auto;font-size:12px;color:#39836a;white-space:nowrap}.node-state.failed,.nodes-error{color:var(--ui-danger,#b45b67)}.node-state.muted{color:var(--ui-muted,#7d879a)}.node-resources{display:grid;grid-template-columns:repeat(2,1fr);gap:20px}.node-resources dt,.node-meta{font-size:12px;color:var(--ui-muted,#7d879a)}.node-resources dd{font-size:20px;margin-top:5px;font-variant-numeric:tabular-nums}.node-resources small{font-size:12px}.node-meta{display:grid;grid-template-columns:auto 1fr;gap:8px 16px}.node-meta>span:nth-child(even),.node-meta time{text-align:right;overflow-wrap:anywhere}.node-identity{font-size:12px}.node-identity summary{cursor:pointer;display:flex;align-items:center;gap:8px}.node-identity p{margin-top:8px}.node-identity code,.node-fingerprint code{overflow-wrap:anywhere}.node-card>footer{flex-wrap:wrap;border-top:1px solid var(--ui-border,#e2e6ed);padding-top:16px}.node-form,.node-form label,.node-fingerprint{display:grid;gap:8px}.node-form{gap:18px}.node-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.node-form label{font-size:13px}.node-fingerprint{padding:14px;border:1px solid var(--ui-border,#e2e6ed);border-radius:8px}.node-fingerprint>button{justify-self:start}.node-form .node-verify{display:flex;align-items:flex-start;gap:8px}.node-verify input{margin-top:3px;accent-color:var(--ui-accent,#856b9e)}.node-note{font-size:12px;color:var(--ui-muted,#7d879a)}.node-form>footer{justify-content:flex-end}.nodes-error{font-size:13px;overflow-wrap:anywhere}@media(max-width:600px){.nodes-page{padding:18px}.node-form-grid{grid-template-columns:1fr}.node-card{padding:18px}}@media(min-width:1920px){.nodes-heading h1{font-size:30px}.node-card h2{font-size:17px}.node-form label{font-size:14px}}@media(min-width:2560px){.nodes-heading h1{font-size:32px}.node-card h2{font-size:18px}.node-form label{font-size:15px}}
</style>
<style>.node-editor{width:calc(100% - 32px);max-width:640px;max-height:90dvh;overflow-y:auto}</style>
