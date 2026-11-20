<script setup lang="ts">
import { KeyRound, Copy, Pencil, Trash2, Plus, AlertCircle } from '@/components/ui/icon';
import AccountScopePicker from './AccountScopePicker.vue';
import { computed, ref, onMounted, onUnmounted } from 'vue';
import { api, type ApiToken, type Account } from '../api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { IconTile } from '@/components/ui/icon-tile';
import { TableCard } from '@/components/ui/table-card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ModalDialog } from '@/components/ui/modal';
import { NoticeStrip } from '@/components/ui/notice-strip';
import { Empty } from '@/components/ui/empty';
import { SearchInput } from '@/components/ui/controls';
import { useToast } from '../composables/useToast';
import { ConfirmationDialog } from './ui/feedback';
import '../tokens.css';

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
/** 令牌名称搜索词，只在已读取的全部令牌中过滤 */
const query = ref('');
/** 按名称过滤后的令牌；未命名令牌按「未命名令牌」匹配 */
const visibleTokens = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase();
  return keyword ? tokens.value.filter(t => (t.name || '未命名令牌').toLocaleLowerCase().includes(keyword)) : tokens.value;
});
/** 标题旁计数：搜索时显示「匹配 / 全部」 */
const countLabel = computed(() => query.value.trim() ? `${visibleTokens.value.length} / ${tokens.value.length} 个令牌` : `${tokens.value.length} 个令牌`);
/** 空状态文案：读取中、尚无令牌与搜索无结果三种 */
const emptyTitle = computed(() => loading.value && !tokens.value.length ? '正在读取令牌…' : !tokens.value.length ? '还没有令牌，可创建客户端凭据。' : '没有匹配的令牌');
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
 * 可用账号范围说明：允许列表为空时为全部可用账号，有排除时追加
 * @param t 令牌对象
 * @return 范围文字
 */
function scopeLabel(t: ApiToken): string {
  const allowed = t.allowed_accounts ? `仅允许 ${formatAccountIds(t.allowed_accounts)}` : '全部可用账号';
  return t.blocked_accounts ? `${allowed} · 排除 ${formatAccountIds(t.blocked_accounts)}` : allowed;
}

/**
 * 创建时间只显示本地日期
 * @param value 接口时间戳
 * @return yyyy/mm/dd，缺失或非法为「—」
 */
function createdDate(value: string): string {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date) : '—';
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
    <PageHeader title="访问令牌" description="管理客户端凭据和可用账号范围。"><template #actions><Button @click="openCreate"><Plus :size="15" />创建令牌</Button></template></PageHeader>
    <NoticeStrip v-if="loadError" tone="danger" role="alert" class="token-load-error"><AlertCircle />{{ loadError }}<template #end><Button variant="outline" size="sm" @click="load">重试</Button></template></NoticeStrip>
    <TableCard class="token-panel" title="访问令牌" :count="countLabel" :aria-busy="loading">
      <template #toolbar><SearchInput v-model="query" label="搜索令牌" placeholder="搜索令牌名称" /></template>
      <Table class="fui-table-fixed">
        <TableHeader><TableRow><TableHead class="token-col-name">名称</TableHead><TableHead class="token-col-token">令牌</TableHead><TableHead class="token-col-scope token-scope-column">可用账号</TableHead><TableHead class="token-col-created token-created-column">创建时间</TableHead><TableHead class="token-col-status">状态</TableHead><TableHead class="token-col-actions fui-table-end">操作</TableHead></TableRow></TableHeader>
        <TableBody>
          <TableRow v-for="t in visibleTokens" :key="t.id" class="token-row" :data-token-id="t.id">
            <TableCell><div class="token-identity"><IconTile size="sm"><KeyRound /></IconTile><span class="token-identity-text"><strong class="fui-table-strong">{{ t.name || '未命名令牌' }}</strong><span class="fui-table-sub token-mobile-scope">{{ scopeLabel(t) }}</span></span></div></TableCell>
            <TableCell><span class="token-value"><code class="fui-table-mono">{{ maskToken(t.token) }}</code><Badge as="button" type="button" variant="secondary" class="token-copy" @click="copyToken(t)"><Copy :size="12" />{{ copiedId === t.id ? '已复制' : '复制' }}</Badge></span></TableCell>
            <TableCell class="token-scope-column" :title="scopeLabel(t)">{{ scopeLabel(t) }}</TableCell>
            <TableCell class="fui-table-num token-created token-created-column">{{ createdDate(t.created_at) }}</TableCell>
            <TableCell><span class="token-status" :data-active="t.status === 'active'"><Switch :model-value="t.status === 'active'" :label="`${t.name || '未命名令牌'}启用状态`" @update:model-value="toggleStatus(t)" /><span class="token-status-text">{{ t.status === 'active' ? '启用' : '停用' }}</span></span></TableCell>
            <TableCell><div class="fui-table-ops token-actions"><Button variant="outline" size="sm" @click="openEdit(t)"><Pencil :size="13" />编辑权限</Button><Button variant="destructive-ghost" size="sm" @click="confirmDelete(t.id)"><Trash2 :size="13" />删除</Button></div></TableCell>
          </TableRow>
          <TableRow v-if="!visibleTokens.length"><TableCell :colspan="6" class="token-empty"><Empty :title="emptyTitle"><template #icon><KeyRound /></template></Empty></TableCell></TableRow>
        </TableBody>
      </Table>
    </TableCard>
    <ModalDialog v-model:open="showForm" class="approved-token-editor" :title="editing ? '编辑令牌权限' : '创建令牌'" description="选择允许与排除的账号，保存后生效。" :width="760">
      <form id="token-editor-form" class="token-form" @submit.prevent="save">
        <label class="token-name"><span class="fui-label">名称</span><Input v-model="form.name" placeholder="例如：开发客户端" /></label>
        <NoticeStrip v-if="accountError" tone="danger" role="alert" class="token-account-error"><AlertCircle />{{ accountError }}<template #end><Button type="button" variant="outline" size="sm" @click="loadAccounts">重试</Button></template></NoticeStrip>
        <AccountScopePicker v-model="form.allowed_accounts" :accounts="allAccounts" label="允许的账号" help="留空允许使用全部可用账号。" />
        <AccountScopePicker v-model="form.blocked_accounts" :accounts="allAccounts" label="排除的账号" help="排除的账号不会用于此令牌。" />
      </form>
      <template #footer><Button type="button" variant="outline" class="token-editor-cancel" @click="showForm = false">取消</Button><Button type="submit" form="token-editor-form">{{ editing ? '保存权限' : '创建令牌' }}</Button></template>
    </ModalDialog>

    <ConfirmationDialog :open="showDeleteConfirm" title="确认删除令牌" message="此操作不可撤销，删除后使用该令牌的客户端将无法访问。" confirm-label="删除" danger :busy="deletingAccount" :error="deleteError" @confirm="executeDelete" @cancel="showDeleteConfirm=false" />
  </div>
</template>
