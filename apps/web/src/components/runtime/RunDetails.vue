<script setup lang="ts">
import CaptureWorkspace from './CaptureWorkspace.vue';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { LayoutGrid, Activity, Files, ShieldCheck, FileText, Settings2 } from '@/components/ui/icon';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { readRun, readRunLog, type RuntimeRun, type RunStats, type RunFile, type RunCapture, type RunFilePreview } from './runApi';

/** 顶层运行详情组件，可供任务列表、工程记录及旧地址入口复用。 */
const props = defineProps<{ runId: string; title: string; accountName: string }>();
const emit = defineEmits<{ close: [] }>();
const run = ref<RuntimeRun | null>(null);
const stats = ref<RunStats | null>(null);
const files = ref<RunFile[]>([]);
const log = ref({text:'等待运行日志',truncated:false});
const capture = ref<RunCapture | null>(null);
const selectedFile = ref('');
const filePreview = ref<RunFilePreview | null>(null);
const fileError = ref('');
const fileLoading = ref(false);
let fileGeneration = 0;
let fileController: AbortController | undefined;
const error = ref('');
const captureError = ref('');
const updated = ref('');
const tab = ref('overview');
const busy = ref(false);
let generation = 0;
let controller: AbortController | undefined;
let timer: ReturnType<typeof setTimeout>;
let lastFiles = 0;
let finalPending = true;
let alive = true;
const tabs = [{id:'overview',label:'概览',icon:LayoutGrid},{id:'logs',label:'日志',icon:Activity},{id:'files',label:'产物文件',icon:Files},{id:'capture',label:'抓包',icon:ShieldCheck}];
const live = computed(() => !!run.value && ['queued','running','stopping','quota_wait'].includes(run.value.status));
const statusLabel = computed(() => ({running:'执行中',queued:'排队中',stopping:'停止中',quota_wait:'等待额度',success:'已完成',done:'已完成',failed:'失败',timeout:'超时',cancelled:'已取消',stopped:'已停止'}[run.value?.status ?? ''] || run.value?.status || '读取中'));
const kind = computed(() => ({normal:'普通任务',capture:'抓包任务',warmup:'养号任务'}[run.value?.run_kind ?? 'normal'] || '运行记录'));
const metrics = computed(() => [
  {name:'输入 Token',value:stats.value?.available === false || stats.value?.usage_available === false ? null : stats.value?.tokens_in,note:'本次运行累计输入'},
  {name:'输出 Token',value:stats.value?.available === false || stats.value?.usage_available === false ? null : stats.value?.tokens_out,note:'本次运行累计输出'},
  {name:'请求数',value:stats.value?.available === false ? null : stats.value?.requests,note:'本次运行累计请求'},
  {name:'退出码',value:run.value?.exit_code,note:live.value?'执行结束后返回':'进程最终退出状态'},
]);
const followupLabel = computed(() => ({single:'单轮任务',not_started:'等待开始',awaiting:'当前轮执行中',pending:'补充投递待确认',complete:'全部轮次完成',unknown:'阶段状态待核对',invalid:'阶段证据无效，请查看运行错误'}[run.value?.followups?.phase ?? ''] || '阶段状态待核对'));
const followupItemLabels: Record<string,string> = {scheduled:'等待到点',pending:'投递待确认',queued:'已入队，等待消费',consumed:'已消费，执行中',completed:'已完成',unknown:'状态待核对'};
/** 保留原运行详情的时分及中文进度。@param seconds 相对开始秒数。@return 可读投递时间。 */
function followupOffset(seconds:number):string{return `${Math.floor(seconds/60)}分${seconds%60}秒`;}
const logLines = computed(() => log.value.text.split('\n').slice(-1500));
const duration = computed(() => {
  if (!run.value?.started_at) return '未开始';
  const seconds = Math.max(0,Math.floor((run.value.ended_at ?? Date.now()/1000) - run.value.started_at));
  return `${Math.floor(seconds/60)} 分 ${seconds%60} 秒`;
});

/** 按当前页签读取观测，旧请求取消后不得覆盖新状态。@return 完成。 */
async function load(): Promise<void> {
  clearTimeout(timer); controller?.abort(); controller = new AbortController();
  const current = ++generation, signal = controller.signal; busy.value = true; error.value = '';
  try {
    const [record, observation] = await Promise.all([readRun<RuntimeRun>(props.runId,'',signal),readRun<RunStats>(props.runId,'/stats',signal).catch(cause => ({error:(cause as Error).message}))]);
    if (current !== generation || !alive) return;
    run.value = record; stats.value = observation;
    const jobs: Promise<void>[] = [];
    if (!lastFiles || Date.now() - lastFiles > 10000 || !live.value) jobs.push(readRun<RunFile[]>(props.runId,'/files',signal).then(value => { if (current === generation) { files.value = value; lastFiles = Date.now(); } }).catch(cause => { if (!signal.aborted) error.value = `产物列表：${(cause as Error).message}`; }));
    if (tab.value === 'logs') jobs.push(readRunLog(props.runId,signal).then(value => { if (current === generation) log.value = value; }).catch(cause => { if (!signal.aborted) log.value = {text:(cause as Error).message,truncated:false}; }));
    if (tab.value === 'capture' && record.run_kind === 'capture') jobs.push(readRun<RunCapture>(props.runId,'/capture',signal).then(value => { if (current === generation) { capture.value = value; captureError.value = ''; } }).catch(cause => { if (!signal.aborted) captureError.value = (cause as Error).message; }));
    await Promise.all(jobs);
    if (current !== generation || !alive) return;
    updated.value = new Date().toLocaleTimeString('zh-CN',{hour12:false});
    if (live.value) timer = setTimeout(load,2500);
    else if (finalPending) { finalPending = false; timer = setTimeout(load,200); }
  } catch (cause) { if (current === generation && !signal.aborted) { error.value = (cause as Error).message; timer = setTimeout(load,2500); } }
  finally { if (current === generation) busy.value = false; }
}
/** 读取当前选择的有界产物文本，快速切换时丢弃旧回执。@param path 文件路径。@return 完成。 */
async function previewFile(path: string): Promise<void> {
  fileController?.abort();fileController = new AbortController();
  const current = ++fileGeneration, signal = fileController.signal;
  selectedFile.value = path;filePreview.value = null;fileError.value = '';fileLoading.value = true;
  try {
    const value = await readRun<RunFilePreview>(props.runId,'/file?path='+encodeURIComponent(path),signal);
    if (current === fileGeneration && alive) filePreview.value = value;
  } catch (cause) { if (current === fileGeneration && !signal.aborted) fileError.value = (cause as Error).message; }
  finally { if (current === fileGeneration) fileLoading.value = false; }
}
/** 文件列表刷新保持选择，已移除文件回到有效候选。@return 无。 */
function synchronizeFile(): void {
  if (tab.value !== 'files') return;
  const available = files.value.filter(file => file.type !== 'dir');
  if (available.some(file => file.path === selectedFile.value)) {
    if (!filePreview.value && !fileLoading.value && !fileError.value) void previewFile(selectedFile.value);
    return;
  }
  fileController?.abort();fileGeneration++;selectedFile.value = '';filePreview.value = null;fileError.value = '';fileLoading.value = false;
  if (available[0]) void previewFile(available[0].path);
}
/** 页签键盘导航。@param event 按键。@return 无。 */
function keys(event: KeyboardEvent): void {
  const index = tabs.findIndex(item => item.id === tab.value);
  const next = event.key === 'ArrowRight' ? (index+1)%4 : event.key === 'ArrowLeft' ? (index+3)%4 : event.key === 'Home' ? 0 : event.key === 'End' ? 3 : -1;
  if (next < 0) return; event.preventDefault(); tab.value = tabs[next]!.id;
  (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role=tab]')[next]?.focus();
}

/** 格式化实际字节数。@param value 字节。@return 可读大小。 */
function size(value?: number): string { return value == null ? '—' : value < 1024 ? `${value} B` : `${(value/1024).toFixed(1)} KB`; }
watch(tab, () => { void load();if (tab.value === 'files') synchronizeFile();else {fileController?.abort();fileGeneration++;fileLoading.value = false;} });
watch(files, synchronizeFile);

onMounted(() => void load());
onUnmounted(() => { alive = false; generation++; clearTimeout(timer); controller?.abort();fileGeneration++;fileController?.abort(); });
</script>

<template>
  <Dialog :open="true" @update:open="value => { if (!value) emit('close'); }"><DialogContent class="approved-run-dialog">
    <DialogHeader><DialogTitle>{{ title || '运行详情' }}</DialogTitle><DialogDescription class="sr-only">本次运行的状态、日志、产物和抓包观测</DialogDescription></DialogHeader>
    <div class="work-run-detail"><div class="run-detail-meta"><div><span class="run-status" :data-status="run?.status">{{ statusLabel }}</span><span>{{ kind }}</span><span>{{ accountName || '账号信息未提供' }}</span></div><code>{{ runId }}</code></div>
      <div class="run-detail-tabs" role="tablist" aria-label="运行详情" @keydown="keys"><button v-for="item in tabs" :id="`native-run-tab-${item.id}`" :key="item.id" type="button" role="tab" :aria-controls="`native-run-panel-${item.id}`" :aria-selected="tab === item.id" :tabindex="tab === item.id ? 0 : -1" :class="{active:tab === item.id}" @click="tab = item.id"><component :is="item.icon" :size="14" />{{ item.label }}<small v-if="item.id === 'files'">{{ files.length }}</small></button></div>
      <div class="run-detail-scroll"><p v-if="error" role="alert" class="run-read-error">{{ error }}<Button variant="outline" size="sm" :disabled="busy" @click="load">重试</Button></p>
        <section v-show="tab === 'overview'" id="native-run-panel-overview" role="tabpanel" aria-labelledby="native-run-tab-overview"><div class="run-stat-grid"><article v-for="(metric,index) in metrics" :key="metric.name"><span>{{ metric.name }}</span><strong :class="{unknown:metric.value == null}">{{ metric.value == null ? index === 3 && live ? '待结束' : '未采集' : metric.value.toLocaleString() }}</strong><small>{{ metric.note }}</small></article></div><p v-if="stats?.error" role="status" class="run-read-error">统计加载失败：{{ stats.error }}</p>
          <div v-if="run?.error" class="run-state-notice" :class="{failure:run.status !== 'quota_wait'}"><div><strong>{{ run.status === 'quota_wait' ? '等待额度恢复' : '运行提示' }}</strong><p>{{ run.error }}</p><p v-if="run.quota_resume_at">恢复机会 {{ new Date(run.quota_resume_at*1000).toLocaleString('zh-CN') }}</p><p v-if="run.passive_quota?.observed_at">观察于 {{ new Date(run.passive_quota.observed_at*1000).toLocaleString('zh-CN') }}</p></div></div>
          <div class="run-overview-grid"><article class="run-info-panel"><header><h3><FileText :size="14" />需求与自动补充</h3><span>本次运行记录</span></header><div class="run-prompt"><span>初始需求</span><p>{{ run?.prompt || '本次运行需求尚未读取' }}</p></div><div class="run-followups"><p class="run-subtle">{{ followupLabel }} · 已完成补充 {{ run?.followups?.completed ?? '待确认' }}/{{ run?.followups?.planned ?? '未知' }}</p><p v-if="run?.followups?.mode === 'timed'" class="run-subtle">按时间投递 · 已投递 {{ run.followups.delivered ?? '待确认' }}/{{ run.followups.planned ?? '未知' }} · 已消费 {{ run.followups.consumed ?? '待确认' }}/{{ run.followups.planned ?? '未知' }}</p><div v-for="(message,index) in run?.followups?.messages ?? []" :key="index"><span>{{ index+1 }}</span><p>{{ message }}<small v-if="run?.followups?.offsets_sec?.[index] != null">启动后 {{ followupOffset(run.followups.offsets_sec[index]!) }} · {{ followupItemLabels[run.followups.items?.[index] ?? 'unknown'] || '状态待核对' }}</small></p></div></div></article>
          <aside class="run-info-panel"><header><h3><Settings2 :size="14" />执行配置</h3></header><dl class="run-config-list"><div><dt>执行节点</dt><dd>{{ run?.execution_node?.name || '未记录' }}</dd></div><div v-if="run?.execution_node"><dt>环境代次</dt><dd>{{ run.execution_node.environment_id }} · {{ run.execution_node.generation }}</dd></div><div><dt>运行版本</dt><dd>{{ run?.claude_code_version ? `Claude Code ${run.claude_code_version}` : '未采集' }}</dd></div><div><dt>冻结模型</dt><dd>{{ run?.execution_model ?? run?.capture_model_override ?? '默认' }}</dd></div><div><dt>思考预算</dt><dd>{{ run?.claude_effort_level || '未采集' }}</dd></div><div><dt>运行耗时</dt><dd>{{ duration }}</dd></div></dl><p class="run-config-note">配置以本次运行保存的记录为准。</p></aside></div>
        </section>
        <section v-show="tab === 'logs'" id="native-run-panel-logs" role="tabpanel" aria-labelledby="native-run-tab-logs"><div class="run-log-panel"><header><div><Activity :size="15" />运行日志</div><span>{{ log.truncated ? '最近 128 KB · 最多 1500 行' : `${logLines.length} 行` }}</span></header><ol><li v-for="(line,index) in logLines" :key="index"><code>{{ line || ' ' }}</code></li></ol><footer>{{ live ? '等待后续运行观测' : '本次运行已结束' }}</footer></div></section>
        <section v-show="tab === 'files'" id="native-run-panel-files" role="tabpanel" aria-labelledby="native-run-tab-files"><div v-if="files.length" class="run-file-browser"><aside class="run-file-list"><header><span>产物文件</span><small>{{ files.length }}</small></header><div class="run-files"><div v-for="file in files" :key="file.path" class="work-file"><button type="button" :disabled="file.type === 'dir'" :class="{ selected: selectedFile === file.path }" :aria-pressed="selectedFile === file.path" @click="previewFile(file.path)"><FileText :size="14" /><span>{{ file.path }}</span><small>{{ file.type === 'dir' ? '目录' : size(file.size) }}</small></button></div></div></aside><article class="run-file-reader" :aria-busy="fileLoading"><header><span>文件预览</span><small>{{ selectedFile || '选择文件' }}</small></header><div v-if="fileLoading" class="run-file-placeholder" role="status">正在读取文件…</div><div v-else-if="fileError" class="run-file-placeholder"><p role="alert">{{ fileError }}</p><Button variant="outline" size="sm" @click="previewFile(selectedFile)">重新读取</Button></div><div v-else-if="filePreview?.binary" class="run-file-placeholder"><FileText :size="28" /><strong>二进制文件</strong><p>此文件不提供文本预览。</p></div><template v-else-if="filePreview"><pre class="work-file-preview">{{ filePreview.text || '（空文件）' }}</pre><p v-if="filePreview.truncated" class="run-file-truncated">文件较大，当前显示前 64 KiB。</p></template><div v-else class="run-file-placeholder"><FileText :size="28" /><p>选择左侧文件查看内容</p></div></article></div><div v-else class="run-empty-state"><Files :size="32" /><h3>产物尚未提供</h3><p>文件生成后可在这里选择并预览。</p></div></section>
        <section v-show="tab === 'capture'" id="native-run-panel-capture" role="tabpanel" aria-labelledby="native-run-tab-capture"><div v-if="run?.run_kind !== 'capture'" class="run-empty-state"><ShieldCheck :size="32" /><h3>本次运行未启用抓包</h3><p>抓包运行的请求索引与 TLS 观测会展示在这里。</p></div><p v-else-if="captureError" role="alert" class="run-read-error">{{ captureError }}</p><CaptureWorkspace v-else-if="capture" :capture="capture" :file-url="`/runtime/api/runs/${encodeURIComponent(runId)}/capture`" /><div v-else class="run-empty-state"><ShieldCheck :size="32" /><p>正在读取抓包观测…</p></div></section>
      </div><footer class="run-detail-footer"><span><ShieldCheck :size="12" />运行记录与实际观测</span><span>{{ updated ? `更新于 ${updated}` : '正在读取…' }}</span></footer>
    </div>
  </DialogContent></Dialog>
</template>

<style scoped>
.work-run-detail{display:flex;flex-direction:column;flex:1;min-height:0;min-width:0}.run-detail-meta{display:flex;justify-content:space-between;align-items:center;gap:15px;padding:18px 26px 14px;flex-shrink:0}.run-detail-meta>div{display:flex;gap:13px;align-items:center;flex-wrap:wrap;font-size:var(--ui-font-size-sm);color:var(--ui-color-text-3)}.run-detail-meta>div>span{display:inline-flex;gap:6px;align-items:center}.run-detail-meta svg{width:13px}.run-detail-meta>code{color:var(--ui-color-text-4);font-size:var(--ui-font-size-sm);overflow-wrap:anywhere}.run-detail-tabs{flex-shrink:0;gap:26px;margin:0;padding:0 26px;border-bottom:1px solid var(--ui-color-line)}.run-detail-tabs button{display:flex;align-items:center;gap:7px;padding:13px 0;font-size:var(--ui-font-size-sm)}.run-detail-tabs svg{width:14px}.run-detail-tabs small{font-size:var(--ui-font-size-sm);padding:1px 5px;border-radius:var(--ui-radius-btn);background:var(--ui-color-primary-container);color:var(--ui-color-primary-text)}.run-detail-scroll{flex:1;min-height:0;overflow:auto;padding:22px 24px;background:var(--ui-color-fill-subtle)}.run-stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:20px}.run-stat-grid article{min-width:0;padding:17px 18px;background:var(--ui-color-surface);border:1px solid var(--ui-color-line);border-radius:var(--ui-radius-block);box-shadow:var(--ui-shadow-card)}.run-stat-grid article>span{display:block;font-size:var(--ui-font-size-sm);color:var(--ui-color-text-3)}.run-stat-grid strong{display:block;font-size:var(--ui-font-size-page);font-weight:550;line-height:1.3;font-variant-numeric:tabular-nums;color:var(--ui-color-text-2);margin:12px 0 9px;letter-spacing:-.5px}.run-stat-grid strong.unknown{font-size:calc(var(--ui-font-size-card) + 2px);font-weight:500;line-height:1.78;letter-spacing:0;color:var(--ui-color-text-4)}.run-stat-grid article>small{display:block;font-size:var(--ui-font-size-sm);line-height:1.6;color:var(--ui-color-text-4)}.run-overview-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);gap:18px;align-items:start}.run-info-panel{min-width:0;border:1px solid var(--ui-color-line);background:var(--ui-color-surface);border-radius:var(--ui-radius-block);overflow:hidden}.run-info-panel>header{padding:18px 20px;border-bottom:1px solid var(--ui-color-line);display:flex;justify-content:space-between;align-items:center;gap:10px}.run-info-panel>header h3{display:flex;gap:7px;align-items:center;font-size:var(--ui-font-size-md);color:var(--ui-color-text-2)}.run-info-panel>header svg{width:14px;color:var(--ui-color-primary-text)}.run-info-panel>header>span{font-size:var(--ui-font-size-sm);white-space:nowrap;color:var(--ui-color-text-4)}.run-prompt{padding:20px}.run-prompt>span{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4)}.run-prompt p{font-size:var(--ui-font-size-md);line-height:1.9;color:var(--ui-color-text-3);margin:9px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}.run-followups{padding:0 20px 8px}.run-followups>div{display:flex;gap:10px;align-items:flex-start;padding:14px 0;border-top:1px solid var(--ui-color-line)}.run-followups>div>span{width:22px;height:22px;flex:none;display:grid;place-items:center;border-radius:var(--ui-radius-btn);background:var(--ui-color-primary-container);color:var(--ui-color-primary-text);font-size:var(--ui-font-size-sm)}.run-followups p{margin:0;flex:1;font-size:var(--ui-font-size-sm);line-height:1.9;color:var(--ui-color-text-3);overflow-wrap:anywhere}.run-followups small{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4);line-height:2.5;white-space:nowrap}.run-followups .run-subtle{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4);margin:0 0 12px}.run-config-list{margin:0;padding:5px 20px}.run-config-list>div{padding:14px 0;border-bottom:1px solid var(--ui-color-line)}.run-config-list>div:last-child{border:0}.run-config-list dt{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4);margin-bottom:7px}.run-config-list dd{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-3);overflow-wrap:anywhere;margin:0;font-weight:500}.run-config-note{margin:0;padding:12px 20px;font-size:var(--ui-font-size-sm);line-height:1.7;color:var(--ui-color-text-4);background:var(--ui-color-surface);border-top:1px solid var(--ui-color-line)}.run-state-notice{display:flex;gap:12px;background:var(--ui-color-fill-subtle);color:var(--ui-color-warning-text);border:1px solid color-mix(in srgb, var(--ui-color-warning) 28%, var(--ui-color-surface));border-radius:var(--ui-radius-control);padding:15px 18px;margin-bottom:18px}.run-state-notice>svg{width:17px;flex:none}.run-state-notice strong{font-size:var(--ui-font-size-sm);font-weight:550}.run-state-notice p{font-size:var(--ui-font-size-sm);line-height:1.8;margin:7px 0 0}.run-state-notice.failure{background:var(--ui-color-fill-subtle);color:var(--ui-color-danger-text);border-color:color-mix(in srgb, var(--ui-color-danger) 28%, var(--ui-color-surface))}.run-detail-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-shrink:0;padding:12px 26px;border-top:1px solid var(--ui-color-line);font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4)}.run-detail-footer>span:first-child{display:flex;align-items:center;gap:6px}.run-detail-footer svg{width:12px}.run-log-panel{border:1px solid var(--ui-color-line);border-radius:var(--ui-radius-block);background:var(--ui-color-surface);overflow:hidden}.run-log-panel>header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid var(--ui-color-line);font-size:var(--ui-font-size-sm);color:var(--ui-color-text-3)}.run-log-panel>header>div{display:flex;align-items:center;gap:8px}.run-log-panel>header svg{width:15px;color:var(--ui-color-primary-text)}.run-log-panel>header>span{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4)}.run-log-panel ol{counter-reset:run-log;list-style:none;margin:0;padding:14px 0;min-height:240px;background:repeating-linear-gradient(var(--ui-color-fill-subtle),var(--ui-color-fill-subtle) 30px,var(--ui-color-surface) 30px,var(--ui-color-surface) 60px)}.run-log-panel li{display:flex;gap:16px;min-height:30px;padding:5px 20px;font-size:var(--ui-font-size-sm);line-height:20px;color:var(--ui-color-text-3)}.run-log-panel li:before{counter-increment:run-log;content:counter(run-log);width:20px;flex:none;color:var(--ui-color-text-4);font:var(--ui-font-size-sm)/20px 'JetBrains Mono Variable',monospace;text-align:right}.run-log-panel code{white-space:pre-wrap;overflow-wrap:anywhere;min-width:0;font-size:var(--ui-font-size-sm)}.run-log-panel>footer{border-top:1px solid var(--ui-color-line);padding:12px 20px;font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4);background:var(--ui-color-surface)}.run-file-browser{display:grid;grid-template-columns:minmax(180px,.8fr) minmax(0,1.2fr);border:1px solid var(--ui-color-line);border-radius:var(--ui-radius-block);background:var(--ui-color-surface);overflow:hidden;min-height:320px}.run-file-browser>aside{border-right:1px solid var(--ui-color-line);background:var(--ui-color-surface);min-width:0}.run-file-browser header{padding:16px 18px;border-bottom:1px solid var(--ui-color-line);font-size:var(--ui-font-size-sm);color:var(--ui-color-text-3);display:flex;justify-content:space-between;gap:10px;min-height:50px;align-items:center}.run-file-browser header>span{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4);overflow-wrap:anywhere}.run-file-browser .work-file{padding:0;border-bottom:1px solid var(--ui-color-line)}.run-file-browser .work-file button{display:flex;align-items:center;gap:8px;padding:14px;width:100%;text-align:left;color:var(--ui-color-text-3);font-size:var(--ui-font-size-sm);min-width:0}.run-file-browser .work-file button>span{flex:1;min-width:0;overflow-wrap:anywhere}.run-file-browser .work-file button svg{width:14px;flex:none}.run-file-browser .work-file button.selected{background:var(--ui-color-primary-container);color:var(--ui-color-primary-text)}.run-file-reader{min-width:0;display:flex;flex-direction:column}.run-file-placeholder{display:grid;align-content:center;justify-items:center;gap:12px;flex:1;padding:35px 25px;text-align:center;color:var(--ui-color-text-4)}.run-file-placeholder>svg{width:32px;height:32px;color:var(--ui-color-primary-text)}.run-file-placeholder strong{font-size:var(--ui-font-size-md);font-weight:500;color:var(--ui-color-text-4)}.run-file-placeholder p{font-size:var(--ui-font-size-sm);line-height:1.8;margin:0}.run-file-reader .work-file-preview{flex:1;border:0;border-radius:0;margin:0;padding:20px;background:var(--ui-color-ink);color:var(--ui-color-ink-text);font-size:var(--ui-font-size-sm);min-height:250px}.run-empty-state{min-height:320px;border:1px solid var(--ui-color-line);border-radius:var(--ui-radius-block);background:var(--ui-color-surface);display:flex;align-items:center;justify-content:center;flex-direction:column;gap:14px;text-align:center;padding:35px}.run-empty-state>svg{width:35px;height:35px;color:var(--ui-color-primary-text)}.run-empty-icon{display:grid;place-items:center;width:54px;height:54px;background:var(--ui-color-primary-container);border-radius:var(--ui-radius-card)}.run-empty-icon svg{width:24px;color:var(--ui-color-primary-text)}.run-empty-tag{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4);background:var(--ui-color-fill-muted);padding:3px 7px;border-radius:var(--ui-radius-btn)}.run-empty-state h3{font-size:var(--ui-font-size-card);margin:0}.run-empty-state p{font-size:var(--ui-font-size-sm);line-height:1.8;color:var(--ui-color-text-4);max-width:350px;margin:0}.run-empty-state>div{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4);padding-top:12px}.run-empty-state code{font-size:var(--ui-font-size-sm);margin-left:8px;overflow-wrap:anywhere}



.run-detail-tabs{display:flex;gap:24px;flex-shrink:0;padding:0 26px;border-bottom:1px solid var(--ui-color-line)}.run-detail-tabs button{border-bottom:2px solid transparent;color:var(--ui-color-text-4)}.run-detail-tabs button.active{border-bottom-color:var(--ui-color-primary);color:var(--ui-color-primary-text)}.run-detail-tabs button:hover{background:var(--ui-color-fill-subtle);color:var(--ui-color-primary-text)}.run-detail-tabs button:focus-visible{outline:2px solid var(--ui-color-primary);outline-offset:-2px}
.run-status{display:inline-flex;align-items:center;padding:5px 8px;background:var(--ui-color-fill-muted);color:var(--ui-color-text-4);border-radius:var(--ui-radius-btn);font-size:var(--ui-font-size-sm)}.run-status[data-status=running],.run-status[data-status=success]{background:var(--ui-color-success-bg);color:var(--ui-color-success-text)}.run-status[data-status=failed],.run-status[data-status=timeout]{background:var(--ui-color-fill-muted);color:var(--ui-color-danger-text)}.run-status[data-status=quota_wait]{background:var(--ui-color-warning-bg);color:var(--ui-color-warning-text)}
.run-files{padding:6px 20px}.run-files>div{display:flex;align-items:center;gap:10px;padding:13px 0;border-bottom:1px solid var(--ui-color-line);font-size:var(--ui-font-size-sm);color:var(--ui-color-text-3)}.run-files>div:last-child{border:0}.run-files span{flex:1;min-width:0;overflow-wrap:anywhere}.run-files small{color:var(--ui-color-text-4);font-size:var(--ui-font-size-sm)}.run-files p{padding:15px;font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4)}
.run-read-error{padding:12px 15px;background:var(--ui-color-fill-subtle);color:var(--ui-color-danger-text);border:1px solid color-mix(in srgb, var(--ui-color-danger) 28%, var(--ui-color-surface));border-radius:var(--ui-radius-control);font-size:var(--ui-font-size-sm);display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:15px}.run-capture-panel{margin-bottom:16px}.run-capture-panel>p{padding:15px 20px;font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4)}.run-capture-meta{display:grid;grid-template-columns:110px minmax(0,1fr);gap:12px;padding:0 20px 20px;font-size:var(--ui-font-size-sm)}.run-capture-meta dt{color:var(--ui-color-text-4)}.run-capture-meta dd{color:var(--ui-color-text-3);overflow-wrap:anywhere}.run-capture-table{overflow:auto}.run-capture-table table{min-width:640px;width:100%;font-size:var(--ui-font-size-sm);text-align:left}.run-capture-table th{font-weight:500;background:var(--ui-color-fill-subtle);color:var(--ui-color-text-4)}.run-capture-table td,.run-capture-table th{padding:12px;border-top:1px solid var(--ui-color-line);max-width:220px;overflow-wrap:anywhere}.run-capture-table small{display:block;color:var(--ui-color-text-4);margin-top:4px}.run-capture-panel details{padding:12px 20px;border-top:1px solid var(--ui-color-line);font-size:var(--ui-font-size-sm);color:var(--ui-color-text-3)}.run-capture-panel summary{cursor:pointer}.run-capture-panel pre{padding:14px;margin-top:10px;background:var(--ui-color-fill-subtle);border-radius:var(--ui-radius-control);max-height:280px;overflow:auto;font-size:var(--ui-font-size-sm);white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:700px){.run-stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.run-overview-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:520px){.run-detail-meta{padding:14px 18px;gap:9px;align-items:flex-start;flex-direction:column}.run-detail-tabs{padding:0 18px;gap:18px;overflow-x:auto}.run-detail-tabs button{white-space:nowrap;font-size:var(--ui-font-size-sm)}.run-detail-scroll{padding:16px}.run-stat-grid article{padding:14px}.run-stat-grid strong{font-size:23px}.run-detail-footer{padding:11px 18px}}

.run-file-browser{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,3fr);min-height:320px;overflow:hidden;border:1px solid var(--ui-color-line);border-radius:var(--ui-radius-block);background:var(--ui-color-surface)}
.run-file-list{min-width:0;border-right:1px solid var(--ui-color-line);background:var(--ui-color-surface)}
.run-file-browser :is(aside,article)>header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px;font-size:var(--ui-font-size-sm);color:var(--ui-color-text-3);min-height:50px;border-bottom:1px solid var(--ui-color-line)}
.run-file-browser header small{font-size:var(--ui-font-size-sm);color:var(--ui-color-text-4);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.run-file-browser .run-files{padding:0;max-height:430px;overflow:auto}
.run-file-browser .work-file{padding:0}
.run-file-reader .work-file-preview{white-space:pre-wrap;overflow-wrap:anywhere;overflow:auto;max-height:430px;font-family:var(--ui-font-family-mono);line-height:1.9}
.run-file-truncated{padding:10px 18px;font-size:var(--ui-font-size-sm);color:var(--ui-color-primary-text);background:var(--ui-color-fill-muted)}
@media(max-width:600px){.run-file-browser{grid-template-columns:minmax(0,1fr)}.run-file-list{border-right:0}.run-file-browser .run-files{max-height:150px}.run-file-reader .work-file-preview{min-height:230px}}
</style>
