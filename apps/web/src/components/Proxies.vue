<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { Globe, Plus, Download, Activity, Pencil, Trash2, ArrowUpRight, ShieldCheck } from '@/components/ui/icon';
import { ChevronDown, LoaderCircle } from 'lucide-vue-next';
import { api, type ProxyRoute, type ProxyInput } from '../api';
import { useToast } from '../composables/useToast';
import { ConfirmationDialog } from './ui/feedback';
import { Button } from './ui/button';
import { PageHeader } from './ui/page-header';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { ChoiceSelect, DateTimeControl, NumberInput, SearchInput, Pagination } from './ui/controls';

const { show: toast } = useToast();
const rows = ref<ProxyRoute[]>([]);
const query = ref('');
const page = ref(1);
const pageSize = ref(20);
watch(pageSize, () => { page.value=1;void load(); });
const pages = ref(0);
const total = ref(0);
const loading = ref(false);
const error = ref('');
const complete = ref(true);
const counts = ref<{ all:number; available:number; used:number|null } | null>(null);
const expanded = ref<string | null>(null);
const AccountWorkspace = defineAsyncComponent(() => import('./Accounts.vue'));
const workspaceAccountId = ref<number | null>(null);
let accountOpener: HTMLElement | null = null;
let accountReturnButton: HTMLElement | null = null;
/** 在代理页复用账号工作区，查看和编辑保持当前路由及筛选。@param user 使用者。@param event 点击事件。@return 无。 */
function openUserAccount(user: ProxyRoute['users'][number], event: MouseEvent): void {
  if (user.kind !== 'gateway') return;
  const id = Number(user.id);
  if (!Number.isSafeInteger(id) || id < 1) return;
  accountOpener = event.currentTarget as HTMLElement;
  const row = accountOpener.closest('tr[data-proxy-id]') ?? accountOpener.closest('.proxy-expanded')?.previousElementSibling;
  accountReturnButton = row?.querySelector<HTMLElement>('.proxy-expand') ?? null;
  workspaceAccountId.value = id;
}
/** 关闭局部工作区并恢复原使用者按钮焦点。@return 无。 */
function closeUserAccount(): void {
  workspaceAccountId.value = null;
  void nextTick(() => { (accountOpener?.isConnected ? accountOpener : accountReturnButton)?.focus({preventScroll:true}); accountOpener=null;accountReturnButton=null; });
}
const now = ref(Date.now());
const probing = ref(new Set<string>());
const batch = ref({ running: false, done: 0, total: 0 });
const cancelBatch = ref(false);
let alive = true;
let request: AbortController | undefined;
let generation = 0;
let searchTimer: ReturnType<typeof setTimeout>;
let clock: ReturnType<typeof setInterval>;
let syncClock: ReturnType<typeof setInterval>;
const editor = ref(false);
const editing = ref<ProxyRoute | null>(null);
const saving = ref(false);
const formError = ref('');
const raw = ref('');
const recognizing = ref(false);
let editorGeneration = 0;
watch(editor, () => { editorGeneration++; }, { flush:'sync' });
const form = ref<ProxyInput>({ name:'', protocol:'http', host:'', port:8080, expires_at:null });
const port = ref<number | string>(8080);
const username = ref('');
const password = ref('');
const replaceAuth = ref(false);
const importOpen = ref(false);
const importText = ref('');
const deleting = ref<ProxyRoute | null>(null);
const connectionLocked = computed(() => !!editing.value && !!(rows.value.find(row=>row.id===editing.value?.id)?.sync_pending ?? editing.value.sync_pending));

/** 服务端过滤后分页，取消旧查询且拒绝迟到响应。@return 完成。 */
async function load(): Promise<void> {
  request?.abort(); const current = ++generation; request = new AbortController(); loading.value = true; error.value = '';
  try {
    const result = await api.listProxies(page.value, query.value.trim(), request.signal, true, pageSize.value);
    if (current !== generation || !alive) return;
    if (result.total_pages && page.value > result.total_pages) { page.value = result.total_pages; return load(); }
    rows.value = result.data; total.value = result.total; pages.value = result.total_pages; complete.value = result.references_complete; counts.value = result.counts ?? null;
  } catch (cause) { if (current === generation && (cause as Error).name !== 'AbortError') error.value = (cause as Error).message; }
  finally { if (current === generation) loading.value = false; }
}
/** 重置分页后查询。@return 无。 */
function search(): void { clearTimeout(searchTimer); page.value = 1; void load(); }
watch(query, () => { clearTimeout(searchTimer); searchTimer = setTimeout(search, 250); });
/** 打开独立编辑草稿。@param value 原记录或新建。@return 无。 */
function edit(value: ProxyRoute | null): void {
  editorGeneration++;
  editing.value = value; formError.value = ''; raw.value = ''; username.value = ''; password.value = ''; replaceAuth.value = false;
  form.value = { name:value?.name ?? '', protocol:value?.protocol ?? 'http', host:value?.host ?? '', port:value?.port ?? 8080, expires_at:value?.expires_at ?? null, revision:value?.revision };
  port.value = form.value.port; editor.value = true;
}
/** 原输入先完整识别再写入草稿。@return 完成。 */
async function recognize(): Promise<void> {
  recognizing.value = true; formError.value = ''; const generation = editorGeneration;
  try {
    const fields = await api.identifyProxy(raw.value);
    if (!editor.value || generation !== editorGeneration) return;
    Object.assign(form.value, fields); port.value = fields.port; username.value = fields.username ?? ''; password.value = fields.password ?? ''; replaceAuth.value = true;
    if (!form.value.name) form.value.name = fields.host;
    raw.value = '';
  } catch (cause) { formError.value = (cause as Error).message; }
  finally { recognizing.value = false; }
}
/** 只更新本地到期草稿。@param days 延长天数。@return 无。 */
function extend(days: number): void { form.value.expires_at = new Date(Math.max(Date.now(), Date.parse(form.value.expires_at ?? '') || 0) + days * 86400000).toISOString(); }
/** 保存表单，认证留空保持原值，清除需显式选择。@return 完成。 */
async function save(): Promise<void> {
  if (saving.value) return;
  const current = editorGeneration;
  saving.value = true; formError.value = '';
  try {
    if (port.value === '' || !Number.isInteger(Number(port.value)) || Number(port.value) < 1 || Number(port.value) > 65535) throw new Error('端口需要是1～65535的整数');
    const payload = { ...form.value, port:Number(port.value) };
    delete payload.username; delete payload.password;
    if (!editing.value || replaceAuth.value || username.value) payload.username = username.value;
    if (!editing.value || replaceAuth.value || password.value) payload.password = password.value;
    const result = await api.saveProxy(editing.value?.id ?? null, payload);
    if (current === editorGeneration) editor.value = false;
    toast(result.sync_pending ? '线路已保存，关联账号将在空闲后自动同步' : '代理已保存', 'success'); await load();
  } catch (cause) { if (current === editorGeneration) formError.value = (cause as Error).message; else toast((cause as Error).message); }
  finally { saving.value = false; }
}
/** 原子导入全部行。@return 完成。 */
async function importRows(): Promise<void> {
  saving.value = true; formError.value = '';
  try { const result = await api.importProxies(importText.value); importOpen.value = false; importText.value = ''; toast(`已导入 ${result.created} 条代理`, 'success'); await load(); }
  catch (cause) { formError.value = (cause as Error).message; } finally { saving.value = false; }
}
/** 探测结果按身份更新，不替换展开的使用者。@param row 线路。@return 完成。 */
async function probe(row: ProxyRoute): Promise<void> {
  if (probing.value.has(row.id)) return;
  probing.value.add(row.id);
  try { const result = await api.probeProxy(row.id); const current = rows.value.find(value => value.id === row.id); if (current && current.revision === row.revision) Object.assign(current, result); }
  catch (cause) { toast((cause as Error).message); } finally { probing.value.delete(row.id); }
}
/** 检测当前搜索范围，最多并发4条，离开页面停止后续派发。@return 完成。 */
async function probeAll(): Promise<void> {
  cancelBatch.value = false; batch.value = { running:true, done:0, total:total.value };
  const search = query.value;
  try {
    let current = 1;
    do {
      const result = await api.listProxies(current, search, undefined, false);
      if (cancelBatch.value || !alive) break;
      for (let start = 0; start < result.data.length && !cancelBatch.value && alive; start += 4) {
        await Promise.all(result.data.slice(start, start + 4).map(async row => { await probe(row); batch.value.done++; }));
      }
      if (current >= result.total_pages) break;
      current++;
    } while (alive && !cancelBatch.value);
  } catch (cause) { toast((cause as Error).message); }
  finally { batch.value.running = false; }
}
/** 重新核对版本及引用后删除。@return 完成。 */
async function remove(): Promise<void> {
  if (!deleting.value || saving.value) return;
  saving.value = true; formError.value = '';
  try { await api.deleteProxy(deleting.value.id, deleting.value.revision); deleting.value = null; await load(); }
  catch (cause) { formError.value = (cause as Error).message; } finally { saving.value = false; }
}
/** 到期倒计时保留未设置和已过期语义。@param value ISO瞬时。@return 显示文字。 */
function remaining(value: string | null): string {
  if (!value) return '未设置到期时间';
  const deadline = Date.parse(value);
  if (!Number.isFinite(deadline)) return '时间异常';
  const delta = deadline - now.value, minutes = Math.max(0,Math.floor(Math.abs(delta)/60000));
  const days = Math.floor(minutes/1440), hours = Math.floor(minutes%1440/60), rest = minutes%60;
  const duration = days ? `${days} 天${hours ? ` ${hours} 小时` : ''}` : hours ? `${hours} 小时${rest ? ` ${rest} 分钟` : ''}` : minutes ? `${minutes} 分钟` : '不足 1 分钟';
  return (delta <= 0 ? '已过期 ' : '剩余 ') + duration;
}
/** 日期安全显示。@param value ISO瞬时。@return 本地时间。 */
function date(value: string | null): string { return value ? new Date(value).toLocaleString('zh-CN', { year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false }) : '尚未检测'; }
/** 引用入口归账号配置，目录不提供关联写入。@param user 使用者。@return 控制台地址。 */
function userLink(user: ProxyRoute['users'][number]): string { return user.kind === 'gateway' ? `/?account=${encodeURIComponent(user.id)}&tab=configuration` : `/tasks?tab=accounts&${user.kind === 'draft' ? 'draft' : 'account'}=${encodeURIComponent(user.id)}`; }
onMounted(() => { void load(); clock = setInterval(() => now.value = Date.now(), 60000); syncClock = setInterval(() => { if (!document.hidden && !loading.value && rows.value.some(row => row.sync_pending)) void load(); }, 5000); });
onUnmounted(() => { alive = false; cancelBatch.value = true; generation++; request?.abort(); clearTimeout(searchTimer); clearInterval(clock); clearInterval(syncClock); });
</script>

<template>
  <div class="proxy-page">
    <PageHeader title="代理管理" description="出口位置、连接质量与账号使用情况，一处查看。"><template #actions><Button variant="outline" @click="importOpen = true; formError = ''"><Download :size="15" />批量导入</Button><Button @click="edit(null)"><Plus :size="15" />添加代理</Button></template></PageHeader>
    <div class="proxy-summary"><span><strong>{{ counts?.all ?? total }}</strong> 条代理</span><span><strong>{{ counts?.available ?? '—' }}</strong> 条可用</span><span><strong>{{ counts?.used ?? '—' }}</strong> 条被使用</span><span v-if="!complete" class="text-amber-700">部分使用情况待核对</span><span>出口信息来自最近一次检测</span></div>
    <section class="proxy-panel">
      <header class="proxy-toolbar"><h3>代理线路 <small>{{ total }} / {{ counts?.all ?? total }} 条</small></h3><SearchInput v-model="query" label="搜索代理" placeholder="名称、地址、出口 IP 或地区" maxlength="256" @search="search" /><Button variant="outline" size="sm" :disabled="batch.running || !total || loading" @click="probeAll"><Activity :size="14" />批量检测</Button></header>
      <div v-if="batch.running" class="proxy-batch" role="status">正在检测 {{ batch.done }} / {{ batch.total }}<button type="button" @click="cancelBatch = true">停止后续检测</button></div>
      <p v-if="error" class="proxy-error" role="alert">{{ error }} <button type="button" @click="load">重试</button></p>
      <div class="proxy-table-scroll" :aria-busy="loading"><table class="proxy-table"><thead><tr><th>代理线路</th><th>出口 IP / 地区</th><th>检测延迟</th><th>连接状态</th><th>到期时间</th><th>账号使用情况</th><th>操作</th></tr></thead><tbody>
        <template v-for="row in rows" :key="row.id"><tr :data-proxy-id="row.id"><td><div class="proxy-identity"><span class="proxy-icon"><Globe :size="18" /></span><div><strong>{{ row.name }}</strong><small><code>{{ row.public_url }}</code></small></div></div></td>
          <td><div class="proxy-exit"><code>{{ row.observation?.ip ?? '—' }}</code><span><template v-if="row.observation"><b>{{ row.observation.country_code || '—' }}</b>{{ [row.observation.country, row.observation.city !== row.observation.country ? row.observation.city || row.observation.region : ''].filter(Boolean).join(' · ') || '地区未知' }}</template><template v-else>等待检测</template></span><small v-if="row.observation && row.status !== 'ready'">上次成功结果</small></div></td>
          <td><div class="proxy-latency"><strong :class="{ slow: row.observation && row.observation.latency_ms > 120 }">{{ row.observation?.latency_ms ?? '—' }} <small v-if="row.observation">ms</small></strong><span>{{ row.checked_at ? '最近检测 ' + new Date(row.observation?.observed_at ?? row.checked_at).toLocaleTimeString('zh-CN', { hour12:false }) : '尚未检测' }}</span></div></td>
          <td><span class="proxy-status" :data-state="row.status"><LoaderCircle v-if="probing.has(row.id)" :size="13" class="animate-spin" />{{ probing.has(row.id) ? '检测中…' : row.status === 'ready' ? '可用' : row.status === 'failed' ? '检测失败' : '待检测' }}</span></td>
          <td class="proxy-expiry-cell"><span class="proxy-expiry" :class="{ expired: row.expires_at && Date.parse(row.expires_at) <= now, soon: row.expires_at && Date.parse(row.expires_at) > now && Date.parse(row.expires_at) - now < 7 * 86400000, unset: !row.expires_at }">{{ remaining(row.expires_at) }}</span><small v-if="row.expires_at">{{ date(row.expires_at) }}</small></td>
          <td><div class="proxy-usage"><div class="proxy-usage-count"><strong>{{ row.users.length }}</strong> 个使用 · <strong>{{ row.active_accounts }}</strong> 个活跃</div><span>{{ row.in_flight }} 个请求处理中</span><div class="proxy-user-chips"><component :is="user.kind === 'gateway' ? 'button' : 'span'" v-for="user in row.users.slice(0, 2)" :key="user.kind + user.id" :type="user.kind === 'gateway' ? 'button' : undefined" @click="openUserAccount(user,$event)">{{ user.name }}</component><span v-if="row.users.length > 2">+{{ row.users.length - 2 }}</span></div><button type="button" class="proxy-expand" :aria-expanded="expanded === row.id" @click="expanded = expanded === row.id ? null : row.id">{{ expanded === row.id ? '收起账号' : '查看使用账号' }}<ChevronDown :size="12" /></button></div></td>
          <td><div class="proxy-row-actions"><span v-if="row.sync_pending" class="proxy-sync-status" role="status">关联同步中</span><Button size="sm" variant="outline" :disabled="probing.has(row.id) || batch.running" @click="probe(row)"><LoaderCircle v-if="probing.has(row.id)" :size="13" class="animate-spin" /><Activity v-else :size="13" />{{ probing.has(row.id) ? '检测中…' : '检测' }}</Button><Button size="sm" variant="outline" @click="edit(row)"><Pencil :size="13" />编辑</Button><Button type="button" size="sm" variant="ghost" class="proxy-delete" @click="deleting = row; formError = ''"><Trash2 :size="13" />删除</Button></div></td></tr>
          <tr v-if="expanded === row.id" class="proxy-expanded"><td colspan="7"><section><header class="proxy-expanded-heading"><div><h3>使用此代理的账号</h3><p>代理由账号配置选择，这里展示当前使用情况</p></div><span>当前请求数来自最近一次读取</span></header><div class="proxy-accounts-grid"><article v-for="user in row.users" :key="user.kind + user.id" class="proxy-account-item"><component :is="user.kind === 'gateway' ? 'button' : 'div'" :type="user.kind === 'gateway' ? 'button' : undefined" class="proxy-account-identity" @click="openUserAccount(user,$event)"><span class="proxy-account-avatar">{{ Array.from(user.name)[0] || '账' }}</span><span><strong>{{ user.name }}</strong><small>{{ user.kind === 'gateway' ? '网关账号' : user.kind === 'task' ? '任务账号' : user.kind === 'authorization' ? '授权流程' : '登录草稿' }} · #{{ user.id }}</small></span></component><div class="proxy-account-state"><span class="proxy-status" :data-state="user.status === 'disabled' ? 'disabled' : user.kind === 'draft' ? 'pending' : 'ready'">{{ user.status === 'disabled' ? '已停用' : user.kind === 'draft' ? '登录草稿' : user.kind === 'authorization' ? '授权中' : '已关联' }}</span><small>{{ user.in_flight == null ? '请求数待核对' : user.in_flight + ' 个请求处理中' }}</small><button v-if="user.kind === 'gateway'" type="button" class="proxy-account-config" @click="openUserAccount(user,$event)">账号配置 <ArrowUpRight :size="12" /></button><router-link v-else-if="user.kind !== 'authorization'" :to="userLink(user)" class="proxy-account-config">{{ user.kind === 'draft' ? '继续登录' : user.kind === 'task' ? '任务账号配置' : '账号配置' }} <ArrowUpRight :size="12" /></router-link></div></article><p v-if="!row.users.length" class="proxy-account-empty">{{ row.references_complete ? '当前没有账号使用此线路' : '使用情况待核对' }}</p></div></section></td></tr>
        </template><tr v-if="!rows.length"><td colspan="7" class="proxy-empty">{{ loading ? '正在读取代理…' : error ? '代理列表读取失败' : query ? '没有匹配的代理' : '还没有代理，可添加或批量导入' }}</td></tr>
      </tbody></table></div>
      <footer class="proxy-pagination"><Pagination v-model:page-size="pageSize" :page="page" :total="total" :disabled="loading" label="代理列表分页" @update:page="value => { page=value;load(); }" /></footer>
    </section><p class="proxy-note"><ShieldCheck :size="14" />检测延迟为经该代理访问出口观测服务的往返耗时；到期提醒用于维护管理。</p>

    <Dialog v-model:open="editor"><DialogContent class="proxy-editor"><DialogHeader><DialogTitle>{{ editing ? '编辑代理' : '添加代理' }}</DialogTitle><DialogDescription class="sr-only">连接参数与有效期，保存后生效。</DialogDescription></DialogHeader>
      <form class="proxy-form" @submit.prevent="save"><div class="proxy-form-scroll">
        <section class="proxy-recognize"><label for="proxy-recognize">一键识别代理</label><div><Input id="proxy-recognize" v-model="raw" type="password" autocomplete="new-password" placeholder="粘贴代理地址，自动拆分类型与认证信息" :disabled="connectionLocked || recognizing" /><Button type="button" variant="outline" :disabled="recognizing || connectionLocked || !raw" @click="recognize"><Activity :size="14" />识别填入</Button></div><p>支持 协议://用户:密码@主机:端口、主机:端口:用户:密码 · 省略协议默认 HTTP</p></section>
        <p v-if="connectionLocked" class="proxy-form-notice">正在向关联账号同步连接参数，空闲后自动应用。名称和到期时间可继续编辑。</p>
        <p v-else-if="editing?.users.length" class="proxy-form-notice">保存后将同步 {{ editing.users.length }} 个关联账号或授权流程，正在使用的账号将在空闲后应用新连接。</p>
        <div class="proxy-form-grid"><label class="proxy-full"><span>代理名称</span><Input v-model="form.name" required maxlength="100" placeholder="例如：新加坡主线路" /></label><ChoiceSelect v-model="form.protocol" label="代理类型" :disabled="connectionLocked || recognizing" :options="[{value:'http',label:'HTTP'},{value:'socks5',label:'SOCKS5'},{value:'socks5h',label:'SOCKS5H'}]" /><NumberInput v-model="port" label="端口" :min="1" :max="65535" required :disabled="connectionLocked || recognizing" /><label class="proxy-full"><span>主机 / IP 地址</span><Input v-model="form.host" required :disabled="connectionLocked || recognizing" placeholder="proxy.example.test 或 IPv4 / IPv6" /></label><label><span>用户名{{ editing?.has_username ? ' · 已设置' : '' }}</span><Input v-model="username" :disabled="connectionLocked || recognizing" autocomplete="off" :placeholder="editing ? '留空保留原值' : '可选'" /></label><label><span>密码{{ editing?.has_password ? ' · 已设置' : '' }}</span><Input v-model="password" :disabled="connectionLocked || recognizing" type="password" autocomplete="new-password" :placeholder="editing ? '留空保留原值' : '可选'" /></label><label v-if="editing && !connectionLocked" class="proxy-full proxy-checkbox"><input v-model="replaceAuth" type="checkbox" />替换认证信息（空字段将清除原值）</label>
          <section class="proxy-full proxy-expiry-editor"><DateTimeControl v-model="form.expires_at" label="到期时间" /><div class="proxy-expiry-actions"><span>快速延长</span><button type="button" @click="extend(30)">延长 30 天</button><button type="button" @click="extend(90)">延长 90 天</button><button type="button" @click="form.expires_at = null">不设置</button></div><p>按浏览器本地时间填写。未到期从原时间延长，其余从现在延长。</p></section>
        </div><p v-if="formError" class="proxy-error" role="alert">{{ formError }}</p>
      <footer class="proxy-form-footer"><span>{{ editing ? '保存前会重新核对配置版本' : '支持 HTTP / SOCKS5 / SOCKS5H' }}</span><Button type="button" variant="outline" :disabled="saving" @click="editor = false">取消</Button><Button type="submit" :disabled="saving || recognizing">{{ saving ? '保存中…' : '保存代理' }}</Button></footer></div></form>
    </DialogContent></Dialog>
    <Dialog v-model:open="importOpen"><DialogContent class="proxy-import-dialog"><DialogHeader><DialogTitle>批量导入代理</DialogTitle><DialogDescription>每行一条，最多 200 条。格式全部通过后统一保存。</DialogDescription></DialogHeader><form @submit.prevent="importRows"><Textarea v-model="importText" aria-label="代理连接列表" rows="9" placeholder="http://user:password@host:port" autocomplete="off" spellcheck="false" /><p v-if="formError" class="proxy-error" role="alert">{{ formError }}</p><footer class="proxy-form-footer"><Button type="button" variant="outline" :disabled="saving" @click="importOpen = false">取消</Button><Button type="submit" :disabled="saving || !importText.trim()">导入代理</Button></footer></form></DialogContent></Dialog>
    <ConfirmationDialog :open="!!deleting" title="删除代理" :message="`确认删除「${deleting?.name || ''}」？账号和登录草稿正在使用的线路会保留。`" confirm-label="确认删除" danger :busy="saving" :error="formError" @confirm="remove" @cancel="deleting=null" />
    <AccountWorkspace v-if="workspaceAccountId" :key="workspaceAccountId" :workspace-account-id="workspaceAccountId" @close="closeUserAccount" @refresh="load" />
  </div>
</template>
