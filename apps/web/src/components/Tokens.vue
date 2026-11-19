<script setup lang="ts">
import { KeyRound, Copy, Pencil, Trash2, Plus } from '@/components/ui/icon';
import AccountScopePicker from './AccountScopePicker.vue';
import { ref, onMounted, onUnmounted } from 'vue';
import { api, type ApiToken, type Account } from '../api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { useToast } from '../composables/useToast';
import { ConfirmationDialog } from './ui/feedback';

const { show: toast } = useToast();

/** 令牌列表 */
const tokens = ref<ApiToken[]>([]);
/** 所有账号（用于选择可用/不可用账号） */
const allAccounts = ref<Account[]>([]);
/** 表单弹窗是否可见 */
const showForm = ref(false);
/** 删除确认弹窗 */
const showDeleteConfirm = ref(false);
const deletingAccount = ref(false);
const deleteError = ref('');
/** 待删除令牌 ID */
const deleteTargetId = ref<number | null>(null);
/** 当前编辑的令牌 */
const editing = ref<ApiToken | null>(null);
/** 表单数据 */
const form = ref({ name: '', allowed_accounts: '', blocked_accounts: '' });
/** 已复制的令牌 ID */
const copiedId = ref<number | null>(null);
const loading = ref(false);
const loadError = ref('');
const accountError = ref('');
let alive = true;
onUnmounted(() => { alive = false; });

/** 分页读取令牌，失败时保留已有记录。@return 完成。 */
async function load(): Promise<void> {
  loading.value = true; loadError.value = '';
  try {
    const values: ApiToken[] = []; let page = 1;
    do { const result = await api.listTokens(page,100); values.push(...result.data); if (page >= result.total_pages || !alive) break; page++; } while (alive);
    if (alive) tokens.value = values;
  } catch (cause) { if (alive) loadError.value = (cause as Error).message || '令牌读取失败'; }
  finally { loading.value = false; }
}

/** 完整读取账号范围，名称缺失的历史ID继续保留。@return 完成。 */
async function loadAccounts(): Promise<void> {
  accountError.value = '';
  try {
    const values: Account[] = []; let page = 1;
    do { const result = await api.listAccounts(page,100,'','',undefined,'all'); values.push(...result.data); if (page >= result.total_pages || !alive) break; page++; } while (alive);
    if (alive) allAccounts.value = values;
  } catch (cause) { if (alive) accountError.value = (cause as Error).message || '账号范围读取失败'; }
}

onMounted(() => {
  load();
  loadAccounts();
});

/** 打开新建令牌弹窗 */
function openCreate() {
  editing.value = null;
  form.value = { name: '', allowed_accounts: '', blocked_accounts: '' };
  showForm.value = true;
}

/**
 * 打开编辑令牌弹窗
 * @param t 要编辑的令牌
 */
function openEdit(t: ApiToken) {
  editing.value = t;
  form.value = {
    name: t.name,
    allowed_accounts: t.allowed_accounts,
    blocked_accounts: t.blocked_accounts,
  };
  showForm.value = true;
}

/** 保存令牌 */
async function save() {
  try {
    if (editing.value) {
      await api.updateToken(editing.value.id, {
        name: form.value.name,
        allowed_accounts: form.value.allowed_accounts,
        blocked_accounts: form.value.blocked_accounts,
      });
    } else {
      await api.createToken({
        name: form.value.name,
        allowed_accounts: form.value.allowed_accounts,
        blocked_accounts: form.value.blocked_accounts,
      });
    }
    showForm.value = false;
    await load();
  } catch (e: unknown) {
    toast((e as Error).message || '保存失败');
  }
}

/** 确认删除 */
function confirmDelete(id: number) {
  deleteTargetId.value = id;
  deleteError.value = '';
  showDeleteConfirm.value = true;
}

/** 执行删除 */
async function executeDelete() {
  if (deleteTargetId.value === null || deletingAccount.value) return;
  deletingAccount.value = true; deleteError.value = '';
  try {
    await api.deleteToken(deleteTargetId.value);
    showDeleteConfirm.value = false;
    deleteTargetId.value = null;
    await load();
  } catch (e: unknown) {
    deleteError.value = (e as Error).message || '删除失败';
  } finally { deletingAccount.value = false; }
}

/** 切换令牌状态 */
async function toggleStatus(t: ApiToken) {
  try {
    const newStatus = t.status === 'active' ? 'disabled' : 'active';
    await api.updateToken(t.id, { status: newStatus });
    await load();
  } catch (e: unknown) {
    toast((e as Error).message || '操作失败');
  }
}

/**
 * 复制令牌到剪贴板
 * @param t 令牌对象
 */
async function copyToken(t: ApiToken) {
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(t.token);
  } else {
    const ta = document.createElement('textarea');
    ta.value = t.token;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
  copiedId.value = t.id;
  setTimeout(() => { copiedId.value = null; }, 2000);
}

/**
 * 遮蔽令牌显示
 * @param token 令牌值
 */
function maskToken(token: string): string {
  if (token.length <= 12) return token;
  return token.slice(0, 7) + '...' + token.slice(-4);
}

/**
 * 解析 ID 列表为账号名显示
 * @param ids 逗号分隔的 ID
 */
function formatAccountIds(ids: string): string {
  if (!ids) return '不限制';
  return ids.split(',').map(id => {
    const acc = allAccounts.value.find(a => a.id === Number(id.trim()));
    return acc ? (acc.name || acc.email) : `#${id.trim()}`;
  }).join(', ');
}

</script>

<template>
  <div class="tokens-page">
    <header class="page-heading"><div><p class="page-eyebrow">访问控制</p><h2>访问令牌</h2><p class="page-description">管理客户端凭据和可用账号范围。</p></div><Button @click="openCreate"><Plus :size="15" />创建令牌</Button></header>
    <p v-if="loadError" class="token-load-error" role="alert">{{ loadError }} <button type="button" @click="load">重试</button></p>
    <section class="token-panel" :aria-busy="loading"><header class="token-panel-head"><h3>访问令牌</h3><span>{{ tokens.length }} 个令牌</span></header>
      <article v-for="t in tokens" :key="t.id" class="token-row"><span class="token-icon"><KeyRound :size="19" /></span><div class="token-identity"><strong>{{ t.name || '未命名令牌' }}</strong><div class="token-meta"><code>{{ maskToken(t.token) }}</code><button type="button" class="token-copy" @click="copyToken(t)"><Copy :size="12" />{{ copiedId === t.id ? '已复制' : '复制' }}</button><span>{{ t.allowed_accounts ? `仅允许 ${formatAccountIds(t.allowed_accounts)}` : '全部可用账号' }}<template v-if="t.blocked_accounts"> · 排除 {{ formatAccountIds(t.blocked_accounts) }}</template></span></div></div>
      <div class="token-actions"><button type="button" class="token-toggle" role="switch" :aria-checked="t.status === 'active'" :aria-label="`${t.name || '未命名令牌'}启用状态`" @click="toggleStatus(t)"><span class="switch-track"><i /></span>{{ t.status === 'active' ? '启用' : '停用' }}</button><span class="action-divider" /><Button variant="outline" size="sm" @click="openEdit(t)"><Pencil :size="13" />编辑权限</Button><button type="button" class="token-delete" @click="confirmDelete(t.id)"><Trash2 :size="14" />删除</button></div>
      </article><p v-if="!tokens.length" class="token-empty">{{ loading ? '正在读取令牌…' : '还没有令牌，可创建客户端凭据。' }}</p>
    </section>
    <Dialog v-model:open="showForm"><DialogContent class="approved-token-editor"><DialogHeader><DialogTitle>{{ editing ? '编辑令牌权限' : '创建令牌' }}</DialogTitle><DialogDescription class="sr-only">选择允许与排除的账号，保存后生效。</DialogDescription></DialogHeader>
      <form @submit.prevent="save"><div class="token-form-scroll"><label class="token-name"><span>名称</span><Input v-model="form.name" placeholder="例如：开发客户端" /></label>
      <p v-if="accountError" class="token-load-error" role="alert">{{ accountError }} <button type="button" @click="loadAccounts">重试</button></p><AccountScopePicker v-model="form.allowed_accounts" :accounts="allAccounts" label="允许的账号" help="留空允许使用全部可用账号。" /><AccountScopePicker v-model="form.blocked_accounts" :accounts="allAccounts" label="排除的账号" help="排除的账号不会用于此令牌。" />
      </div><footer class="token-editor-footer"><Button type="button" variant="outline" @click="showForm = false">取消</Button><Button type="submit">{{ editing ? '保存权限' : '创建令牌' }}</Button></footer></form>
    </DialogContent></Dialog>

    <ConfirmationDialog :open="showDeleteConfirm" title="确认删除令牌" message="此操作不可撤销，删除后使用该令牌的客户端将无法访问。" confirm-label="删除" danger :busy="deletingAccount" :error="deleteError" @confirm="executeDelete" @cancel="showDeleteConfirm=false" />
  </div>
</template>
