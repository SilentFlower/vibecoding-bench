<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue';
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent } from 'reka-ui';
import { Users, ChevronRight, Check } from './ui/icon';
import { SearchInput } from './ui/controls';
import { api, type Account } from '../api';
/** 搜索账号名称或邮箱，筛选接口继续提交稳定ID。 */
const props = defineProps<{ modelValue: string; platform?: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const open = ref(false), query = ref(''), error = ref(''), loading = ref(false), label = ref('全部账号');
const rows = ref<Account[]>([]), page = ref(0), pages = ref(0);
let generation = 0, timer: ReturnType<typeof setTimeout>;
let controller: AbortController | undefined;
/** 查询全量账号集合，按页加载。@param more 追加页。@return 完成。 */
async function load(more = false): Promise<void> {
  controller?.abort();controller = new AbortController();const current = ++generation;loading.value = true;error.value = '';
  try { const result = await api.listAccounts(more ? page.value+1 : 1,20,query.value,'',controller.signal,props.platform);if(current!==generation || !open.value)return;rows.value = more ? [...rows.value,...result.data] : result.data;page.value=result.page;pages.value=result.total_pages; }
  catch(cause){if(current===generation && (cause as Error).name!=='AbortError')error.value=(cause as Error).message;}finally{if(current===generation)loading.value=false;}
}
/** 仅更新筛选草稿。@param account 账号或全部。@return 无。 */
function select(account: Account | null): void { label.value=account?.name || account?.email || '全部账号';emit('update:modelValue',account ? String(account.id) : '');open.value=false; }
watch(open,value=>{if(value){query.value='';void load();}else{generation++;controller?.abort();clearTimeout(timer);}});
watch(query,()=>{clearTimeout(timer);timer=setTimeout(()=>void load(),250);});watch(()=>props.modelValue,value=>{if(!value)label.value='全部账号';});
onUnmounted(()=>{generation++;controller?.abort();clearTimeout(timer);});
</script>
<template><div class="fui-field"><span class="fui-label">账号</span><PopoverRoot v-model:open="open"><PopoverTrigger class="fui-choice" aria-label="账号"><Users :size="14" /><span>{{ label }}</span><ChevronRight :size="12" /></PopoverTrigger><PopoverPortal><PopoverContent class="proxy-picker-popup" align="start" :side-offset="6" @escape-key-down="event=>{event.preventDefault();event.stopPropagation();open=false}"><SearchInput v-model="query" label="搜索请求账号" placeholder="名称或邮箱" @search="load()" /><div class="proxy-picker-options"><button type="button" @click="select(null)"><span>全部账号</span><Check v-if="!modelValue" :size="14" /></button><button v-for="account in rows" :key="account.id" type="button" @click="select(account)"><span><strong>{{ account.name || account.email }}</strong><small>{{ account.email }}<template v-if="platform==='all'"> · {{ account.platform==='antigravity' ? 'Antigravity' : 'Claude Code' }}</template></small></span><Check v-if="modelValue===String(account.id)" :size="14" /></button><p v-if="error" role="alert">{{ error }}</p><p v-if="loading">正在读取…</p><button v-if="page<pages" type="button" @click="load(true)">加载更多</button></div></PopoverContent></PopoverPortal></PopoverRoot></div></template>
