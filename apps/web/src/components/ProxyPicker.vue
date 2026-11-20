<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import { Globe, ChevronDown, Check } from 'lucide-vue-next';
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent } from 'reka-ui';
import { api, type ProxyRoute } from '../api';
import { SearchInput } from './ui/controls';

/** 大量线路采用搜索及分批加载，选择只写调用方草稿。 */
const props = defineProps<{ modelValue: ProxyRoute | null | undefined; currentLabel: string; disabled?: boolean; help?: string; portalTarget?: HTMLElement }>();
const emit = defineEmits<{ 'update:modelValue': [value: ProxyRoute | null] }>();
const open = ref(false);
const query = ref('');
const rows = ref<ProxyRoute[]>([]);
const page = ref(0);
const pages = ref(0);
const loading = ref(false);
const error = ref('');
let timer: ReturnType<typeof setTimeout>;
let request: AbortController | undefined;
let generation = 0;
const label = computed(() => props.modelValue === undefined ? props.currentLabel : props.modelValue?.name ?? '直连');
/** 按公开字段查询，关闭和新查询撤销旧结果。@param more 是否追加分页。@return 完成。 */
async function load(more = false): Promise<void> {
  request?.abort(); request = new AbortController(); const current = ++generation;
  loading.value = true; error.value = '';
  try {
    const result = await api.listProxies(more ? page.value + 1 : 1, query.value, request.signal, false);
    if (current !== generation || !open.value) return;
    rows.value = more ? [...rows.value, ...result.data] : result.data; page.value = result.page; pages.value = result.total_pages;
  } catch (cause) { if (current === generation && (cause as Error).name !== 'AbortError') error.value = (cause as Error).message; }
  finally { if (current === generation) loading.value = false; }
}
watch(open, (value,_previous,onCleanup) => {
  if(value){
    query.value='';void load();
    const owner=props.portalTarget?.ownerDocument;
    if(owner&&owner!==document){
      // Reka在父文档创建，跨文档浮层补充宿主的外部点击监听。
      const outside=(event:PointerEvent)=>{const target=event.target as Element|null;if(!target?.closest?.('.proxy-picker-popup,.proxy-picker-trigger'))open.value=false;};
      owner.addEventListener('pointerdown',outside,true);onCleanup(()=>owner.removeEventListener('pointerdown',outside,true));
    }
  }else{generation++;request?.abort();clearTimeout(timer);}
});
watch(query, () => { clearTimeout(timer); if (open.value) timer = setTimeout(() => void load(), 250); });
/** 保留父编辑器，Esc仅关闭选线列表。@param event 按键。@return 无。 */
function escape(event: KeyboardEvent): void { event.preventDefault(); event.stopPropagation(); open.value = false; }
/** 选择线路不立即提交账号。@param value 代理或直连。@return 无。 */
function select(value: ProxyRoute | null): void { emit('update:modelValue', value); open.value = false; }
onUnmounted(() => { generation++; request?.abort(); clearTimeout(timer); });
</script>
<template>
  <div class="account-proxy-picker"><span class="fui-label">代理线路</span><PopoverRoot v-model:open="open"><PopoverTrigger class="proxy-picker-trigger" :disabled="disabled"><Globe :size="18" /><span><strong>{{ label }}</strong><small>{{ modelValue?.public_url ?? '点击搜索并选择线路' }}</small></span><ChevronDown :size="14" /></PopoverTrigger><PopoverPortal :to="portalTarget"><PopoverContent class="proxy-picker-popup" align="start" :side-offset="6" :collision-padding="16" @escape-key-down="escape" @keydown.esc="escape"><SearchInput v-model="query" label="搜索代理线路" placeholder="搜索名称、地址、出口或地区" maxlength="256" @search="load()" /><div class="proxy-picker-options" :aria-busy="loading"><button type="button" @click="select(null)"><Globe :size="16" /><span><strong>直连</strong><small>不使用代理</small></span><Check v-if="modelValue === null" :size="15" /></button><button v-for="row in rows" :key="row.id" type="button" @click="select(row)"><Globe :size="16" /><span><strong>{{ row.name }}</strong><small>{{ row.public_url }}<template v-if="row.observation"> · {{ row.observation.country || row.observation.country_code || '地区未知' }}</template></small></span><Check v-if="modelValue?.id === row.id" :size="15" /></button><p v-if="error" role="alert">{{ error }} <button type="button" @click="load()">重试</button></p><p v-else-if="loading">正在读取…</p><p v-else-if="!rows.length">没有匹配的代理</p><button v-if="page < pages" type="button" class="proxy-picker-more" :disabled="loading" @click="load(true)">加载更多线路</button></div><footer><router-link to="/proxies">前往代理管理</router-link><small>线路按搜索结果分批显示</small></footer></PopoverContent></PopoverPortal></PopoverRoot><p>{{ help || '选择代理或直连，保存账号后应用' }}</p></div>
</template>
