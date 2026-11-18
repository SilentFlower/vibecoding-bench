<script setup lang="ts">
import { computed } from 'vue';
import type { RuntimeEnvironment } from './runtimeApi';

/** 平台内置内核的只读信息，运行观察继续核对实际环境代次。 */
const props = defineProps<{ environment: RuntimeEnvironment }>();
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
      <p>请求内核随平台镜像统一交付。模型使用该账号已观测的 Gemini 与 Claude 能力。</p>
      <div class="workspace-properties">
        <div class="kv"><span>运行进程 / 上限</span><strong>{{ environment.agy_runtime?.workers ?? '未观测' }} / {{ environment.agy_runtime?.max_workers ?? '未观测' }}</strong></div>
        <div class="kv"><span>等待工具结果</span><strong>{{ environment.agy_runtime?.tool_waiting ?? '未观测' }}</strong></div>
        <div class="kv"><span>共享完整映像</span><strong>{{ environment.agy_runtime?.image_bytes == null ? '未观测' : `${Math.round(environment.agy_runtime.image_bytes / 1024 ** 2)} MiB` }}</strong></div>
        <div class="kv"><span>监督进程实际驻留</span><strong>{{ environment.agy_runtime?.controller?.Rss == null ? '未观测' : `${Math.round(environment.agy_runtime.controller.Rss / 1024)} MiB` }}</strong></div>
      </div>
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
