<script setup lang="ts">
import { computed, ref } from 'vue';
import { ChoiceSelect } from './ui/controls';
import type { NativeCapture, NativeCaptureStage } from '../api';
import '../request-records.css';

const props = defineProps<{ snapshot: NonNullable<NativeCapture['snapshot']> }>();
const action = ref('all');
type RawStage = 'ingress' | 'decoded_gemini' | 'cc_prepared' | 'tui_provider_request' | 'wire_final';
const ingressOnly = computed(() => props.snapshot.stage === 'agy_ingress'
  || (props.snapshot.stage === 'ingress_rejected' && props.snapshot.stages?.length === 1
    && props.snapshot.stages[0]?.stage === 'ingress'));
const tuiProvider = computed(() => props.snapshot.stage === 'tui_provider_request');
const submissionFormat = computed(() => props.snapshot.stages?.find(item => item.stage === 'tui_provider_request')?.representation);
const oldTuiCapture = computed(() => tuiProvider.value && submissionFormat.value === 'http_request_to_local_provider');
const tuiHeaderRows = computed(() => {
  const snapshot = props.snapshot;
  if (snapshot.stage !== 'tui_provider_request' || !snapshot.ingress) return [];
  const incoming = new Set(snapshot.ingress.headers.map(([name]) => name.toLowerCase()));
  const submitted = new Set(snapshot.headers.map(([name]) => name.toLowerCase()));
  return [...new Set([...incoming, ...submitted])].sort().map(name => ({
    name, incoming: incoming.has(name), submitted: submitted.has(name),
  }));
});
const rawStage = ref<RawStage>(tuiProvider.value ? 'tui_provider_request'
  : ingressOnly.value || props.snapshot.stage === 'ingress_rejected' ? 'ingress' : props.snapshot.wire_final ? 'wire_final' : 'cc_prepared');
const rawStages = computed<RawStage[]>(() => {
  if (tuiProvider.value) return ['ingress', 'tui_provider_request', 'wire_final'];
  if (ingressOnly.value) return ['ingress'];
  if (props.snapshot.stage === 'agy_egress') return props.snapshot.ingress ? ['ingress', 'wire_final'] : ['wire_final'];
  if (props.snapshot.stage !== 'agy_prepared') return ['ingress', 'cc_prepared', 'wire_final'];
  return props.snapshot.wire_final ? ['ingress', 'decoded_gemini', 'cc_prepared', 'wire_final'] : ['ingress', 'decoded_gemini', 'cc_prepared'];
});
const tlsWire = computed(() => props.snapshot.wire_final?.source === 'native_tls_uprobe' ? props.snapshot.wire_final : undefined);
const agyWire = computed(() => {
  const wire = props.snapshot.wire_final;
  return wire?.source === 'agy_http_transport' || wire?.source === 'agy_native_tls' ? wire : undefined;
});
const decisions = computed(() => (props.snapshot.header_policy?.decisions ?? []).filter(item => action.value === 'all' || item.action === action.value));
const preview = computed(() => {
  const snapshot = props.snapshot;
  if (rawStage.value === 'ingress') return snapshot.ingress;
  if (rawStage.value === 'decoded_gemini') return snapshot.decoded_gemini;
  if (rawStage.value === 'wire_final') return snapshot.wire_final;
  return snapshot.stage === 'cc_prepared' || snapshot.stage === 'agy_prepared' || snapshot.stage === 'tui_provider_request' ? snapshot : undefined;
});
const missingStageNote = computed(() => stages.value.find(stage => stage.stage === rawStage.value)?.note);
const finalReason = computed(() => {
  const reason = props.snapshot.wire_final?.reason;
  if (!reason) return '';
  return ({ OBSERVER_NOT_CONFIGURED: '当前实例尚未配置原生TLS旁路采集器', IMAGE_NOT_ADMITTED: '当前执行体尚待挂点准入验证',
    CAPTURE_PENDING: '最终TLS采集已转入后台，结果待核对', CAPTURE_PREPARING: '本次请求到达时，后台采集器正在准备',
    OBSERVER_UNAVAILABLE: '原生TLS采集器启动失败，请核对探针权限与安装', EVENT_LOSS: '采集副本存在缺口，范围和哈希保持未知',
    HTTP_PARTIAL: '本次只观察到部分HTTP实体', REQUEST_NOT_OBSERVED: '本次没有取得与请求ID匹配的HTTP实体',
    OBSERVER_START_TIMEOUT: '采集器启动等待超时', OBSERVER_FINISH_TIMEOUT: '采集器收口等待超时' } as Record<string, string>)[reason] ?? '本次原生TLS采集未完整收口';
});
const stages = computed<NativeCaptureStage[]>(() => props.snapshot.stages?.map(stage => {
  // 旧版把两种提交路径写成了同一个来源，历史快照只能说明提交阶段。
  if (oldTuiCapture.value && stage.stage === 'tui_provider_request') return { ...stage, representation: '提交快照' };
  if (oldTuiCapture.value && stage.stage === 'wire_final' && stage.status === 'unavailable') {
    return { ...stage, note: '本次只保存到模型请求提交阶段。最终 TLS 写出未采集。' };
  }
  return stage;
}) ?? [
  { stage: 'ingress', source: 'unavailable', representation: 'unavailable', status: 'unavailable', note: '历史记录未保存入口阶段' },
  { stage: 'header_policy', source: 'unavailable', representation: 'unavailable', status: 'unavailable', note: '历史记录未保存逐字段决策' },
  { stage: 'cc_prepared', source: '历史组装快照', representation: 'json_before_native_transport', status: props.snapshot.body_truncated || props.snapshot.headers_truncated ? 'truncated' : 'complete' },
  { stage: 'wire_final', source: 'unavailable', representation: 'unavailable', status: 'unavailable', note: '本次未采集独立最终TLS写出' },
]);

/** 展示实际处理动作。@param value 持久动作。@return 中文标签。 */
function actionLabel(value: string): string {
  return ({ keep: '保留', drop: '删除', runtime: '运行时处理', context: '提取上下文', added: '新增', removed: '删除', changed: '改写' } as Record<string, string>)[value] ?? value;
}

/** 展示阶段及证据完整性。@param value 持久状态或阶段。@return 中文标签。 */
function label(value: string): string {
  if (value === 'tui_provider_request') {
    if (submissionFormat.value === 'request_to_account_sender') return '提交给账号发送器';
    if (submissionFormat.value === 'http_request_written_to_loopback_provider') return '提交给本地提供方';
    return '模型请求提交';
  }
  if(value==='cc_prepared' && props.snapshot.stage==='agy_prepared')return 'AGY原生提交';
  if(value==='wire_final' && props.snapshot.wire_final?.source==='agy_native_tls')return '最终 TLS 写出';
  if(value==='wire_final' && (props.snapshot.stage==='agy_prepared' || props.snapshot.stage==='agy_egress'))return '实际出站';
  return ({ decoded_gemini: '已解码Gemini', agy_prepared:'AGY原生提交', ingress: '入口原文', header_policy: '头部处理', cc_prepared: '原生组装后', wire_final: '最终TLS写出', complete: '完整', truncated: '已截断', unavailable: '未采集', failed: '采集失败', incomplete: '采集不完整' } as Record<string, string>)[value] ?? value;
}

/** 只格式化完整JSON，截断预览保持原始表示。@return 脱敏展示文本。 */
function bodyText(): string {
  const value = preview.value;
  if (!value) return '';
  if (value.body_truncated || value.body.length > 1024 * 1024) return value.body;
  try { return JSON.stringify(JSON.parse(value.body), null, 2); } catch { return value.body; }
}
</script>

<template>
  <div data-native-stages>
    <div class="request-stages"><article v-for="stage in stages" :key="stage.stage"><span>{{ label(stage.stage) }}</span><strong :class="{ready:stage.status==='complete'}">{{ label(stage.status) }}</strong><small>{{ stage.source }} · {{ stage.representation }}</small><small v-if="stage.note">{{ stage.note }}</small></article></div>
    <section v-if="tuiProvider && snapshot.stage === 'tui_provider_request' && !snapshot.header_policy" class="request-section">
      <h3>请求头对照</h3><p class="form-help">按字段名对照入口与提交时的快照。逐字段处理原因未采集。</p>
      <p v-if="snapshot.ingress?.headers_truncated || snapshot.headers_truncated" class="form-help">请求头已截断，仅展示已记录的字段。</p>
      <div v-if="tuiHeaderRows.length" class="request-evidence-table"><table><thead><tr><th>字段</th><th>入口</th><th>提交</th></tr></thead>
        <tbody><tr v-for="row in tuiHeaderRows" :key="row.name"><td><code>{{ row.name }}</code></td><td>{{ row.incoming ? '已记录' : '—' }}</td><td>{{ row.submitted ? '已记录' : '—' }}</td></tr></tbody></table>
      </div><p v-else class="form-help">本次没有可对照的请求头。</p>
    </section>
    <section v-else-if="!ingressOnly" class="request-section"><div class="request-section-head"><h3>头部处理</h3><ChoiceSelect v-model="action" label="筛选头部处理动作" :options="[{value:'all',label:'全部动作'},{value:'drop',label:'只看删除'},{value:'runtime',label:'运行时处理'},{value:'context',label:'提取上下文'},{value:'keep',label:'保留'}]" /></div>
      <template v-if="snapshot.header_policy && snapshot.header_policy.status!=='unavailable'">
        <p class="request-header-summary">{{ label(snapshot.header_policy.status) }} · 保存 {{ snapshot.header_policy.stored_count ?? '未观测' }} / 实际 {{ snapshot.header_policy.observed_count ?? '未观测' }} 项<span>删除 {{ snapshot.header_policy.decisions.filter(item=>item.action==='drop').length }} 项</span></p>
        <div class="request-evidence-table"><table><thead><tr><th>字段</th><th>动作</th><th v-if="agyWire">阶段</th><th>原因</th></tr></thead><tbody><tr v-for="(item,index) in decisions" :key="index" :class="['keep','drop','runtime','context'].includes(item.action)?'request-header-'+item.action:''"><td><code>{{ item.name }}</code></td><td><span class="request-header-badge">{{ actionLabel(item.action) }}</span></td><td v-if="agyWire">{{ item.stage === 'egress' ? '出站适配' : '网关入口' }}</td><td>{{ item.reason }}</td></tr><tr v-if="!decisions.length"><td :colspan="agyWire ? 4 : 3">当前筛选下没有已保存的处理项。</td></tr></tbody></table></div>
      </template><p v-else class="form-help">{{ snapshot.header_policy?.note ?? '历史记录未保存逐字段处理明细。' }}</p>
    </section>
    <section v-if="!ingressOnly && (!tuiProvider || snapshot.body_changes)" class="request-section"><h3>正文变化</h3>
      <template v-if="snapshot.body_changes && snapshot.body_changes.status!=='unavailable'"><p class="form-help">{{ label(snapshot.body_changes.status) }} · {{ tuiProvider ? '对比入口与提交给提供方的正文。' : '对比入口与组装后的正文。' }}路径使用 JSON Pointer。</p><dl class="request-definitions"><template v-for="(item,index) in snapshot.body_changes.items" :key="index"><dt><code>{{ item.path || '/' }}</code></dt><dd>{{ actionLabel(item.action) }} · {{ item.reason }}</dd></template></dl><p v-if="!snapshot.body_changes.items.length" class="form-help">本次观察到的正文内容保持一致。</p></template><p v-else class="form-help">{{ snapshot.body_changes?.note ?? '历史记录未保存正文变化证据。' }}</p>
    </section>
    <details v-if="tlsWire" class="request-code-block request-wire-evidence" data-native-wire-final><summary>原生TLS接受证据</summary><div class="request-wire-content">

      <p>实体完整性：{{ label(tlsWire.status) }} · 网络刷出：未独立观测</p>
      <p v-if="finalReason" role="status" class="break-words request-wire-reason">{{ finalReason }}（{{ tlsWire.reason }}）</p>
      <p class="break-all request-wire-note">进程 {{ tlsWire.worker_pid ?? '未观测' }} · 连接 {{ tlsWire.connection_id ?? '未观测' }} · 环境代次 {{ tlsWire.binding_generation ?? '未观测' }}</p>
      <p v-if="tlsWire.http_sha256" class="break-all request-wire-note">整体HTTP {{ tlsWire.observed_http_bytes }} 字节 · SHA256 {{ tlsWire.http_sha256 }}</p>
      <p v-if="tlsWire.complete">正文与组装阶段的SHA256：{{ tlsWire.body_sha256 === snapshot.original_body_sha256 ? '一致' : '不同' }}。比较依据为同次实际观测摘要。</p>
      <p class="request-wire-note">此处记录原生TLS接受的HTTP明文。上游接收与模型执行分别由对应响应证据说明。</p>
      <div v-if="snapshot.final_header_changes" class="overflow-auto">
        <p class="request-wire-note">头部变化分析：{{ label(snapshot.final_header_changes.status) }}</p>
        <table class="w-full text-left"><thead><tr class="border-b"><th class="p-2">组装至TLS的头部变化</th><th class="p-2">动作</th></tr></thead><tbody>
          <tr v-for="(item, index) in snapshot.final_header_changes.items" :key="index" class="border-b"><td class="p-2 break-all font-mono">{{ item.name }}</td><td class="p-2">{{ actionLabel(item.action) }}</td></tr>
        </tbody></table>
      </div>
      <div v-if="snapshot.final_body_changes" class="overflow-auto">
        <p class="request-wire-note">正文变化分析：{{ label(snapshot.final_body_changes.status) }}</p>
        <table class="w-full text-left"><thead><tr class="border-b"><th class="p-2">组装至TLS的正文变化</th><th class="p-2">动作</th></tr></thead><tbody>
          <tr v-for="(item, index) in snapshot.final_body_changes.items" :key="index" class="border-b"><td class="p-2 break-all font-mono">{{ item.path || '/' }}</td><td class="p-2">{{ actionLabel(item.action) }}</td></tr>
        </tbody></table>
        <p v-if="snapshot.final_body_changes.status === 'complete' && !snapshot.final_body_changes.items.length" class="request-wire-note">同次观察到的JSON字段保持一致。</p>
      </div>
    </div></details>
    <details v-if="agyWire" class="request-code-block request-wire-evidence" data-agy-wire-final>
      <summary>实际出站证据</summary>
      <div class="request-wire-content"><p>实体完整性 {{ label(agyWire.status) }}<template v-if="agyWire.http_status != null"> · 上游 HTTP {{ agyWire.http_status }}</template></p><p class="request-wire-note">{{ agyWire.source === 'agy_native_tls' ? '请求头和正文来自 AGY 原生 TLS 写入实际接受的 HTTP 字节。' : '请求头和正文来自账号出站适配层的实际 HTTP 传输记录。' }}</p></div>
    </details>
    <section class="request-section"><div class="request-section-head"><h3>脱敏原文</h3><div class="request-stage-tabs" role="group" aria-label="原文阶段"><button v-for="stage in rawStages" :key="stage" type="button" :class="{active:rawStage===stage}" :aria-pressed="rawStage===stage" @click="rawStage=stage">{{ label(stage) }}</button></div></div>
      <template v-if="preview"><p class="form-help request-evidence-hash">原正文 {{ preview.original_body_bytes ?? '未观测' }} 字节 · SHA256 {{ preview.original_body_sha256 ?? '未观测' }}</p><p v-if="preview.body_truncated || preview.headers_truncated" role="status" class="form-help">内容已截断。正文：{{ preview.body_truncated ? '已截断' : '完整' }}，请求头：{{ preview.headers_truncated ? '已截断' : '完整' }}。</p><details open class="request-code-block"><summary>请求头</summary><pre>{{ preview.headers.map(([name,value])=>name+': '+value).join('\n') }}</pre></details><details :open="preview.body.length <= 1024 * 1024" class="request-code-block"><summary>请求正文</summary><pre>{{ bodyText() }}</pre></details></template><div v-else class="request-empty-capture"><strong>本次未保存所选阶段的原文</strong><p v-if="missingStageNote">{{ missingStageNote }}</p></div>
    </section>
  </div>
</template>
