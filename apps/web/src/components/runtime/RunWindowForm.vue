<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue';
import { Button } from '../ui/button';
import { TimeControl } from '../ui/controls';
import { Plus, Trash2 } from '../ui/icon';
import { runtimeRequest, type RunWindow, type RunWindowConfig } from './runtimeApi';

/** 环境与任务共用时段编辑，关闭限制保留已保存的星期和区间。 */
const props=defineProps<{accountId:number}>();
const emit=defineEmits<{saved:[];busy:[value:boolean]}>();
const policy=ref<RunWindow|null>(null),form=ref<RunWindowConfig>({enabled:false,days:[],intervals:[]});
const loading=ref(false),saving=ref(false),error=ref(''),message=ref('');
let controller:AbortController|undefined,version=0;
/** 读取新账号的独立草稿，丢弃旧回执。@return 读取完成。 */
async function load():Promise<void>{controller?.abort();controller=new AbortController();const current=++version;loading.value=true;error.value='';try{const value=await runtimeRequest<RunWindow>(`/accounts/${props.accountId}/run-window`,{signal:controller.signal});if(current!==version)return;policy.value=value;form.value=structuredClone(value.config);if(!form.value.intervals.length)form.value.intervals=[{start:'09:00',end:'18:00'}];}catch(cause){if(current===version&&(cause as Error).name!=='AbortError')error.value=(cause as Error).message;}finally{if(current===version)loading.value=false;}}
/** 保存冻结账号的有效时段，离页后不更新新表单。@return 保存结束。 */
async function save():Promise<void>{if(!policy.value||saving.value)return;const current=version,account=props.accountId;const chosen=form.value.enabled?form.value:policy.value.config;const snapshot={enabled:form.value.enabled,days:[...chosen.days],intervals:chosen.intervals.map(value=>({...value}))};saving.value=true;emit('busy',true);error.value='';message.value='';try{await runtimeRequest(`/accounts/${account}/run-window`,{method:'PUT',body:snapshot});if(current!==version)return;policy.value.config=snapshot;message.value='运行时段已保存';emit('saved');}catch(cause){if(current===version)error.value=(cause as Error).message;}finally{if(current===version){saving.value=false;emit('busy',false);}}}
watch(()=>props.accountId,()=>{policy.value=null;void load();},{immediate:true});
onUnmounted(()=>{version++;controller?.abort();});
</script>
<template>
  <form class="runtime-run-window" @submit.prevent="save">
    <p v-if="loading" role="status">正在读取运行时段…</p><p v-if="error" class="runtime-error" role="alert">{{ error }} <Button v-if="!policy" type="button" variant="outline" @click="load">重新读取</Button></p>
    <template v-if="policy"><div class="runtime-setting-row"><div><strong>限制运行时段</strong><p>按 {{ policy.timezone }} 当地时间安排后续执行</p></div><input v-model="form.enabled" type="checkbox" role="switch" aria-label="启用运行时段" :disabled="saving" /></div><fieldset :disabled="!form.enabled||saving"><div class="runtime-weekdays"><label v-for="(day,index) in ['一','二','三','四','五','六','日']" :key="day"><input v-model="form.days" type="checkbox" :value="index" />周{{ day }}</label></div><div v-for="(interval,index) in form.intervals" :key="index" class="runtime-time-interval"><TimeControl v-model="interval.start" :label="`时段 ${index+1} 开始`" :disabled="!form.enabled||saving" /><TimeControl v-model="interval.end" :label="`时段 ${index+1} 结束`" :disabled="!form.enabled||saving" /><Button type="button" variant="ghost" :aria-label="`删除时段 ${index+1}`" :disabled="!form.enabled||saving" @click="form.intervals.splice(index,1)"><Trash2 :size="14" /></Button></div><Button type="button" variant="outline" :disabled="!form.enabled||saving||form.intervals.length>=8" @click="form.intervals.push({start:'09:00',end:'18:00'})"><Plus :size="14" />添加时段</Button></fieldset><footer class="workspace-form-footer"><span>跨午夜的区间归属开始当天，当前执行继续完成。</span><Button type="submit" :disabled="saving">{{ saving?'保存中…':'保存时段' }}</Button></footer><p v-if="message" role="status">{{ message }}</p></template>
  </form>
</template>
