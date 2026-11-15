<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import { Copy, ShieldCheck, FileText } from '../ui/icon';
import { type RunCapture, readCaptureFile } from './runApi';
import { Pagination } from '../ui/controls';
import { tlsFields } from './captureEvidence';
import '../../../../legacy-web/capture-workspace.css';

/** 运行及工程共享的脱敏抓包工作区，文件接口由经过校验的宿主提供。 */
const props=defineProps<{capture:RunCapture;fileUrl:string}>();
const activeTab=ref('index');
const page=ref(1);
const pageSize=ref(20);
watch(pageSize,()=>{page.value=1;});
const selectedFlow=ref<number|null>(null);
const selectedFile=ref('');
const filePreview=ref('');
const fileError=ref('');
const reading=ref(false);
const copyMessage=ref('');
const entries=computed(()=>props.capture.index?.entries??[]);
const pages=computed(()=>Math.max(1,Math.ceil(entries.value.length/pageSize.value)));
const rows=computed(()=>entries.value.slice((page.value-1)*pageSize.value,page.value*pageSize.value));
let controller:AbortController|undefined;
let generation=0;
watch(pages,value=>{page.value=Math.min(page.value,value);});
watch(()=>props.fileUrl,()=>{controller?.abort();generation++;selectedFile.value='';filePreview.value='';fileError.value='';reading.value=false;activeTab.value='index';selectedFlow.value=null;page.value=1;});
onUnmounted(()=>{controller?.abort();generation++;});

/** 只为服务端公开文件白名单提供预览入口。@param path 清单相对路径。@return 是否支持。 */
function canPreview(path:string):boolean{return ['capture_index.json','capture-status.json','tls_clienthello.jsonl'].includes(path.split('/').at(-1)??'');}
/** 每次选择使用独立代次，关闭或切换文件后丢弃旧回执。@param path 公开清单路径。@return 读取结束。 */
async function preview(path:string):Promise<void>{
  if(!canPreview(path))return;
  controller?.abort();controller=new AbortController();const current=++generation,signal=controller.signal;
  selectedFile.value=path;reading.value=true;filePreview.value='';fileError.value='';
  try{const result=await readCaptureFile(props.fileUrl,path,signal);if(current===generation)filePreview.value=JSON.stringify(result,null,2);}
  catch(error){if(current===generation&&!signal.aborted)fileError.value=(error as Error).message;}
  finally{if(current===generation)reading.value=false;}
}
/** 复制公开索引，HTTP环境沿用当前文档的选中复制。@param event 点击事件。@return 复制结束。 */
async function copyIndex(event:MouseEvent):Promise<void>{
  const text=JSON.stringify(props.capture.index??{},null,2);let copied=false;
  try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);copied=true;}}catch{}
  if(!copied){const trigger=event.currentTarget as HTMLElement,doc=trigger.ownerDocument,input=doc.createElement('textarea');input.value=text;input.style.cssText='position:fixed;left:0;top:0;opacity:0';input.tabIndex=-1;(trigger.closest('[role=dialog],.modal-card')??doc.body).append(input);try{input.select();copied=doc.execCommand('copy');}catch{}finally{input.remove();trigger.focus();}}
  copyMessage.value=copied?'已复制索引':'复制失败，请手动选择索引内容';
}
</script>
<template>
  <div class="capture-workspace" data-capture-workspace>
    <div class="upgrade-capture-overview"><div><span>采集请求</span><strong>{{ capture.index?.total_flows ?? entries.length }}</strong></div><div><span>运行版本</span><strong>{{ capture.claude_code_version || '未观测' }}</strong></div><div><span>思考预算</span><strong>{{ capture.claude_effort_level || '未观测' }}</strong></div></div>
    <div class="upgrade-capture-toolbar"><div class="upgrade-reading-tabs" role="tablist" aria-label="抓包分类"><button v-for="item in [{id:'index',label:'请求索引'},{id:'files',label:'采集文件'},{id:'tls',label:'TLS 握手'}]" :key="item.id" type="button" role="tab" :aria-selected="activeTab===item.id" :class="{active:activeTab===item.id}" @click="activeTab=item.id">{{ item.label }}</button></div><button type="button" class="capture-button" @click="copyIndex"><Copy :size="13" />复制索引</button></div>
    <p class="work-note">{{ capture.message || '仅展示已落盘的脱敏数据' }}<template v-if="capture.permission_mode"> · {{ capture.permission_mode }}</template></p><p v-if="copyMessage" role="status" class="work-note">{{ copyMessage }}</p>
    <section v-show="activeTab==='index'" role="tabpanel" aria-label="请求索引"><div class="work-table-wrap"><table class="work-table"><thead><tr><th>请求</th><th>结果</th><th>请求 / 响应</th><th>详情</th></tr></thead><tbody><tr v-for="(entry,index) in rows" :key="(page-1)*pageSize+index"><td><strong>{{ entry.request?.method || '未观测' }} {{ entry.request?.host }}{{ entry.request?.path }}</strong><small>{{ entry.flow_id || '未观测' }} · {{ entry.client_connection_id || '连接未观测' }}</small></td><td>{{ entry.response?.status ?? '待终结' }} · {{ ({complete:'已完成',pending:'响应中',interrupted:'已中断'} as Record<string,string>)[entry.capture_state??''] || entry.capture_state || '状态未观测' }}</td><td>{{ entry.request?.body_bytes ?? '—' }} / {{ entry.response?.body_bytes ?? '—' }} B</td><td><button type="button" @click="selectedFlow=(page-1)*pageSize+index">查看</button></td></tr><tr v-if="!entries.length"><td colspan="4"><div class="capture-empty"><ShieldCheck :size="26" /><strong>{{ capture.available===false?'当前没有可用抓包':'尚未采集到目标请求' }}</strong><p>内容按发生时的采集配置保存。</p></div></td></tr></tbody></table></div><footer v-if="entries.length" class="capture-pager"><Pagination v-model:page="page" v-model:page-size="pageSize" :total="entries.length" unit="条已保存索引" label="抓包索引分页" /></footer><pre v-if="selectedFlow!==null && entries[selectedFlow]" class="work-log">{{ JSON.stringify(entries[selectedFlow],null,2) }}</pre></section>
    <section v-show="activeTab==='files'" role="tabpanel" aria-label="采集文件"><div v-for="file in capture.files??[]" :key="file.path" class="work-file"><FileText :size="16" /><code>{{ file.path }}</code><small>{{ file.size ?? '—' }} B</small><button type="button" :disabled="!canPreview(file.path)" @click="preview(file.path)">{{ canPreview(file.path)?'预览':'保留原文件' }}</button></div><p v-if="!capture.files?.length" class="work-note">暂无抓包文件。</p><p class="work-note">预览限于脱敏索引、收尾状态与 TLS 元数据。</p><div v-if="selectedFile" class="capture-file-preview"><header>{{ selectedFile }}</header><p v-if="reading" role="status">正在读取…</p><p v-else-if="fileError" role="alert">{{ fileError }} <button type="button" @click="preview(selectedFile)">重试</button></p><pre v-else class="work-log">{{ filePreview }}</pre></div></section>
    <section v-show="activeTab==='tls'" role="tabpanel" aria-label="TLS 握手"><section class="upgrade-card"><header><h3>ClientHello</h3><span>{{ capture.tls_clienthello?.count_exact?'全部':'已扫描' }} {{ capture.tls_clienthello?.count_exact?capture.tls_clienthello.total_records??0:capture.tls_clienthello?.scanned_records??0 }} 条握手</span></header><div class="upgrade-card-body"><p class="work-note">{{ capture.tls_clienthello?.message || '尚未保存握手观测，未采集的指纹保持空值。' }}</p><details v-for="(entry,index) in capture.tls_clienthello?.entries??[]" :key="index" class="capture-tls-entry"><summary>握手 {{ index+1 }}</summary><pre class="work-log">{{ JSON.stringify(tlsFields(entry),null,2) }}</pre></details></div></section></section>
    <details class="capture-metadata"><summary>完整采集配置</summary><dl><dt>模式</dt><dd>{{ capture.mode || '未提供' }}</dd><dt>权限模式</dt><dd>{{ capture.permission_mode || '未提供' }}</dd><dt>覆盖模型</dt><dd>{{ capture.model_override || '默认' }}</dd><dt>观测版本</dt><dd>{{ capture.index?.cc_versions?.join('、') || '未观测' }}</dd></dl></details>
  </div>
</template>
