<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { Button } from '../ui/button';
import { runtimeRequest, type AgyKernelCatalog, type RuntimeEnvironment } from './runtimeApi';

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
  } catch (cause) {
    error.value = (cause as Error).message;
  } finally {
    applying.value = false;
    emit('busy', false);
  }
}

onMounted(loadKernels);
watch(() => props.environment.generation, loadKernels);
const versions = ['2.1.280', '2.1.293'] as const;
const states: Record<string, string> = {
  ready: '暖进程就绪', busy: '暖进程使用中', preparing: '准备中', unprepared: '等待按需准备',
  sleeping: '环境休眠', maintenance: '环境维护中', failed: '准备失败', disabled: '原生方式已关闭', unknown: '运行状态待核对',
};
const kernels = computed(() => versions.map(version => ({
  version,
  kernel: props.environment.native_kernels?.[version] ?? (version === '2.1.293' ? props.environment.native_kernel : null),
  observation: props.environment.native_preparation?.versions?.[version]
    ?? (version === '2.1.293' ? props.environment.native_preparation : null),
})));
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
        <label v-if="catalog"><span>请求内核 </span><select v-model="target" :disabled="applying" aria-label="请求内核">
          <option value="">平台内置</option>
          <option v-if="catalog.kernel && !catalog.candidates.includes(catalog.kernel)" :value="catalog.kernel">{{ catalog.kernel.slice(0, 12) }}（待核对）</option>
          <option v-for="item in catalog.candidates" :key="item" :value="item">{{ item.slice(0, 12) }}</option>
        </select></label>
        <Button v-if="catalog" variant="outline" :disabled="applying || loading || environment.busy || (target || null) === catalog.kernel" @click="applyKernel">{{ target ? '切换内核' : '恢复内置' }}</Button>
        <Button variant="outline" :disabled="loading || applying" @click="loadKernels">刷新候选</Button>
      </div>
      <p v-if="error" role="alert" class="runtime-error">{{ error }}</p>
      <p v-else-if="catalog && catalog.kernel !== loaded && (catalog.kernel || loaded !== undefined)">下一条请求将载入所选内核。</p>
      <p v-else-if="catalog && !catalog.candidates.length">在宿主机准备候选包后刷新。</p>
      <details class="runtime-technical"><summary>固定原版身份</summary><code>{{ environment.agy_runtime?.source_sha256 || '未提供' }}</code></details>
    </template>
    <template v-else>
    <div class="kernel-version"><span>管理方式</span><strong>随 flower2api 版本统一交付</strong></div>
    <p>升级或回退平台时，账号自动采用目标镜像配套的请求内核。280 / 293 继续按请求画像自动匹配。</p>
    <section v-for="item in kernels" :key="item.version" :aria-label="`Claude Code ${item.version} 内核`">
      <div class="kernel-version"><strong>Claude Code {{ item.version }}</strong><span class="environment-state-label">{{ item.kernel ? states[item.observation?.state ?? 'unknown'] || '运行状态待核对' : '安装信息未提供' }}</span></div>
      <template v-if="item.kernel">
        <div class="workspace-properties">
          <div class="kv"><span>内置内核版本</span><strong>{{ item.version }}</strong></div>
          <div class="kv"><span>制品摘要</span><strong><code>{{ item.kernel.builtin?.launcher_sha256?.slice(0, 12) || '未提供' }}</code></strong></div>
          <div class="kv"><span>所属平台批次</span><strong>{{ item.kernel.platform_release || '未提供' }}</strong></div>
          <div class="kv"><span>空闲 / 存活进程</span><strong>{{ item.observation?.idle_workers ?? '—' }} / {{ item.observation?.live_workers ?? '—' }}</strong></div>
          <div class="kv"><span>实际空闲 PID</span><strong>{{ item.observation?.pid ?? '未观测' }}</strong></div>
        </div>
        <p v-if="item.kernel.state === 'migration_required'">历史独立选择等待空闲环境重建，平台升级将在维护阶段完成迁移。</p>
        <p v-if="item.kernel.state === 'reconcile' || item.kernel.error" role="alert" class="runtime-error">{{ item.kernel.error || '历史内核维护待核对，请在环境维护中执行对账。' }}</p>
        <details class="runtime-technical"><summary>完整制品摘要</summary><dl><dt>镜像内置分发 SHA256</dt><dd><code>{{ item.kernel.builtin?.launcher_sha256 || '未提供' }}</code></dd></dl></details>
      </template>
    </section>
    <p v-if="environment.request_backend !== 'native293'">此环境当前使用基础转发方式。</p>
    </template>
  </section>
</template>
