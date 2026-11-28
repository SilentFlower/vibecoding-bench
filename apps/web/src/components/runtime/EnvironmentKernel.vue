<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { Button } from '../ui/button';
import { ChoiceSelect, type ChoiceOption } from '../ui/controls';
import { agyToolContinuationLabels, runtimeRequest, type AgyKernelCatalog, type AgyToolContinuationPolicy, type RuntimeEnvironment } from './runtimeApi';
import { requestBackendLabel, tuiRuntimeLabel } from './environmentLabels';
import EnvironmentBasics from './EnvironmentBasics.vue';

/** 读取内核的实际运行状态，并按同一环境代次切换已登记的反重力候选。 */
const props = defineProps<{ environment: RuntimeEnvironment }>();
const emit = defineEmits<{ refresh: []; busy: [value: boolean] }>();
const catalog = ref<AgyKernelCatalog>();
const target = ref('');
const error = ref('');
const loading = ref(false);
const applying = ref(false);
const kernelPath = computed(() => `/environments/${props.environment.environment_id}/agy-kernel`);
const loaded = computed(() => props.environment.agy_runtime?.loaded_kernel);
/** 可选内核：平台内置、未登记的现选值（待核对）与宿主机已准备的候选，均显示摘要前 12 位。 */
const kernelOptions = computed<ChoiceOption[]>(() => {
  const observed = catalog.value;
  if (!observed) return [];
  const pending = observed.kernel && !observed.candidates.includes(observed.kernel) ? [{ value: observed.kernel, label: `${observed.kernel.slice(0, 12)}（待核对）` }] : [];
  return [{ value: '', label: '平台内置' }, ...pending, ...observed.candidates.map(item => ({ value: item, label: item.slice(0, 12) }))];
});
const toolPolicyPath = computed(() => `/environments/${props.environment.environment_id}/agy-tool-continuation`);
const toolPolicy = ref<AgyToolContinuationPolicy>();
const toolMode = ref('claim');
const toolError = ref('');
const toolLoading = ref(false);
const toolSaving = ref(false);
let toolRequest = 0;
const toolOptions = computed<ChoiceOption[]>(() => Object.entries(agyToolContinuationLabels).map(([value, label]) => ({
  value, label, disabled: value !== 'claim' && !toolPolicy.value?.supported,
})));

/** 读取当前环境的续轮策略，按请求序号忽略迟到响应。@return 已读取的界面状态。 */
async function loadToolPolicy() {
  if (props.environment.platform !== 'antigravity' || toolSaving.value) return;
  const request = ++toolRequest;
  toolLoading.value = true;
  toolError.value = '';
  try {
    const value = await runtimeRequest<AgyToolContinuationPolicy>(toolPolicyPath.value);
    if (request !== toolRequest) return;
    toolPolicy.value = value;
    toolMode.value = value.mode;
  } catch (cause) {
    if (request === toolRequest) toolError.value = (cause as Error).message;
  } finally {
    if (request === toolRequest) toolLoading.value = false;
  }
}

/** 用实际读取的代次和策略版本保存。@return 按服务端回执更新的状态。 */
async function saveToolPolicy() {
  const observed = toolPolicy.value;
  if (!observed || toolLoading.value || toolSaving.value || toolMode.value === observed.mode) return;
  const request = ++toolRequest;
  toolSaving.value = true;
  toolError.value = '';
  try {
    const value = await runtimeRequest<AgyToolContinuationPolicy>(toolPolicyPath.value, {
      method: 'POST', body: { expected_generation: observed.generation, expected_revision: observed.revision, mode: toolMode.value },
    });
    if (request !== toolRequest) return;
    toolPolicy.value = value;
    toolMode.value = value.mode;
  } catch (cause) {
    if (request === toolRequest) toolError.value = (cause as Error).message;
  } finally {
    if (request === toolRequest) toolSaving.value = false;
  }
}

/** 加载宿主机已为当前环境准备的候选。@return 完成后的界面状态。 */
async function loadKernels() {
  if (props.environment.platform !== 'antigravity' || loading.value || applying.value) return;
  loading.value = true;
  error.value = '';
  try {
    catalog.value = await runtimeRequest<AgyKernelCatalog>(kernelPath.value);
    target.value = catalog.value.kernel ?? '';
  } catch (cause) {
    error.value = (cause as Error).message;
  } finally {
    loading.value = false;
  }
}

/** 用已展示的代次和原选择请求切换。@return 保存后的界面状态。 */
async function applyKernel() {
  const observed = catalog.value;
  if (!observed || applying.value || props.environment.busy) return;
  applying.value = true;
  error.value = '';
  emit('busy', true);
  try {
    catalog.value = await runtimeRequest<AgyKernelCatalog>(kernelPath.value, {
      method: 'POST', body: { expected_generation: observed.generation, expected_kernel: observed.kernel, kernel: target.value || null },
    });
    target.value = catalog.value.kernel ?? '';
    emit('refresh');
    void loadToolPolicy();
  } catch (cause) {
    error.value = (cause as Error).message;
  } finally {
    applying.value = false;
    emit('busy', false);
  }
}

onMounted(loadKernels);
watch(() => props.environment.generation, loadKernels);
watch([() => props.environment.environment_id, () => props.environment.generation], () => {
  toolRequest += 1;
  toolPolicy.value = undefined;
  toolSaving.value = false;
  toolLoading.value = false;
  void loadToolPolicy();
}, { immediate: true });
const states: Record<string, string> = {
  ready: '暖进程就绪', busy: '暖进程使用中', preparing: '准备中', unprepared: '等待按需准备',
  sleeping: '环境休眠', maintenance: '环境维护中', failed: '准备失败', disabled: '原生方式已关闭', unknown: '运行状态待核对',
};
const kernel = computed(() => props.environment.native_kernels?.['2.1.293'] ?? props.environment.native_kernel);
const observation = computed(() => props.environment.native_preparation?.versions?.['2.1.293'] ?? props.environment.native_preparation);
</script>
<template>
  <section class="environment-kernel">
    <template v-if="environment.platform === 'antigravity'">
      <div class="kernel-version"><strong>Antigravity {{ environment.agy_runtime?.version || '1.5.9' }}</strong><span>{{ states[environment.agy_runtime?.state ?? 'unknown'] || '运行状态待核对' }}</span></div>
      <div class="workspace-properties">
        <div class="kv"><span>当前已加载</span><strong>{{ loaded === undefined ? '等待进程报告' : loaded?.slice(0, 12) || '平台内置' }}</strong></div>
        <div class="kv"><span>运行进程 / 上限</span><strong>{{ environment.agy_runtime?.workers ?? '未观测' }} / {{ environment.agy_runtime?.max_workers ?? '未观测' }}</strong></div>
        <div class="kv"><span>等待工具结果</span><strong>{{ environment.agy_runtime?.tool_waiting ?? '未观测' }}</strong></div>
        <div class="kv"><span>共享完整映像</span><strong>{{ environment.agy_runtime?.image_bytes == null ? '未观测' : `${Math.round(environment.agy_runtime.image_bytes / 1024 ** 2)} MiB` }}</strong></div>
        <div class="kv"><span>监督进程实际驻留</span><strong>{{ environment.agy_runtime?.controller?.Rss == null ? '未观测' : `${Math.round(environment.agy_runtime.controller.Rss / 1024)} MiB` }}</strong></div>
      </div>
      <div class="workspace-inline-actions">
        <ChoiceSelect v-if="catalog" v-model="target" class="environment-kernel-select" label="请求内核" :options="kernelOptions" :disabled="applying" />
        <Button v-if="catalog" variant="outline" :disabled="applying || loading || environment.busy || (target || null) === catalog.kernel" @click="applyKernel">{{ target ? '切换内核' : '恢复内置' }}</Button>
        <Button variant="outline" :disabled="loading || applying" @click="loadKernels">刷新候选</Button>
      </div>
      <p v-if="error" role="alert" class="runtime-error">{{ error }}</p>
      <p v-else-if="catalog && catalog.kernel !== loaded && (catalog.kernel || loaded !== undefined)">下一条请求将载入所选内核。</p>
      <p v-else-if="catalog && !catalog.candidates.length">在宿主机准备候选包后刷新。</p>
      <div class="workspace-inline-actions">
        <ChoiceSelect v-model="toolMode" class="environment-kernel-select" :options="toolOptions" label="工具续轮模式" :disabled="toolLoading || toolSaving || !toolPolicy" />
        <Button variant="outline" :disabled="toolLoading || toolSaving || !toolPolicy || toolMode === toolPolicy.mode || (!toolPolicy.supported && toolMode !== 'claim')"
          @click="saveToolPolicy">{{ toolSaving ? '正在保存' : '保存模式' }}</Button>
        <Button v-if="toolError" variant="outline" :disabled="toolLoading || toolSaving" @click="loadToolPolicy">刷新模式</Button>
      </div>
      <p v-if="toolError" role="alert" class="runtime-error">{{ toolError }}</p>
      <p v-else-if="toolPolicy && !toolPolicy.supported">当前发送器或请求内核暂不支持历史续轮。</p>
      <p v-else-if="toolPolicy">保存后对新派发的请求生效。</p>
      <details class="runtime-technical"><summary>固定原版身份</summary><code>{{ environment.agy_runtime?.source_sha256 || '未提供' }}</code></details>
    </template>
    <template v-else>
      <div class="kernel-version">
        <strong>{{ requestBackendLabel(environment.request_backend) }}</strong>
        <span v-if="environment.request_backend === 'tui_v2'">{{ tuiRuntimeLabel(environment.tui_runtime) }}</span>
      </div>
      <div v-if="environment.request_backend === 'tui_v2'" class="workspace-properties">
        <div class="kv"><span>模型投递</span><strong>{{ environment.tui_runtime?.direct == null ? '未观测' : environment.tui_runtime.direct ? '受管 CLI 直发' : '直发能力未就绪' }}</strong></div>
      </div>
      <EnvironmentBasics :environment="environment" />
      <section v-if="environment.request_backend === 'native293'" aria-label="Claude Code 2.1.293 内核">
        <div class="kernel-version"><span>管理方式</span><strong>随 flower2api 版本统一交付</strong></div>
        <p>升级或回退平台时，账号自动采用目标镜像配套的请求内核。</p>
        <div class="kernel-version"><strong>Claude Code 2.1.293</strong><span class="environment-state-label">{{ kernel ? states[observation?.state ?? 'unknown'] || '运行状态待核对' : '安装信息未提供' }}</span></div>
        <template v-if="kernel">
          <div class="workspace-properties">
            <div class="kv"><span>内置内核版本</span><strong>2.1.293</strong></div>
            <div class="kv"><span>制品摘要</span><strong><code>{{ kernel.builtin?.launcher_sha256?.slice(0, 12) || '未提供' }}</code></strong></div>
            <div class="kv"><span>所属平台批次</span><strong>{{ kernel.platform_release || '未提供' }}</strong></div>
            <div class="kv"><span>空闲 / 存活进程</span><strong>{{ observation?.idle_workers ?? '—' }} / {{ observation?.live_workers ?? '—' }}</strong></div>
            <div class="kv"><span>实际空闲 PID</span><strong>{{ observation?.pid ?? '未观测' }}</strong></div>
          </div>
          <p v-if="kernel.state === 'migration_required'">历史独立选择等待空闲环境重建，平台升级将在维护阶段完成迁移。</p>
          <p v-if="kernel.state === 'reconcile' || kernel.error" role="alert" class="runtime-error">{{ kernel.error || '历史内核维护待核对，请在环境维护中执行对账。' }}</p>
          <details class="runtime-technical"><summary>完整制品摘要</summary><dl><dt>镜像内置分发 SHA256</dt><dd><code>{{ kernel.builtin?.launcher_sha256 || '未提供' }}</code></dd></dl></details>
        </template>
      </section>
    </template>
  </section>
</template>
