<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '../api';

const ready = ref(false);
const error = ref('');
const route = useRoute();
const router = useRouter();
const frame = ref<HTMLIFrameElement | null>(null);
const taskTabs = ['accounts', 'topics', 'tasks', 'runs', 'projects', 'warmup'];
const view = computed(() => route.name === 'environments' ? 'environments' : 'tasks');
const tab = computed(() => route.name === 'environments' ? 'environments'
  : typeof route.query.tab === 'string' && taskTabs.includes(route.query.tab) ? route.query.tab : 'accounts');
const source = computed(() => {
  const query = new URLSearchParams();
  for (const key of ['account', 'environment', 'gateway_account']) {
    if (typeof route.query[key] === 'string') query.set(key, route.query[key]);
  }
  return `/runtime/?view=${view.value}#${tab.value}${query.size ? `?${query}` : ''}`;
});
const documentSource = ref(source.value);
watch(view, () => { documentSource.value = source.value; });

/** 将顶层地址同步为同文档 hash，历史项由顶层路由统一管理。@return 无返回值。 */
function synchronizeFrame(): void {
  const child = frame.value?.contentWindow;
  if (!child) return;
  const target = new URL(source.value, location.origin);
  // 首次加载和文档视图切换交由 src；二级导航只替换 hash，避免重新初始化页面。
  if (child.location.pathname !== target.pathname || child.location.search !== target.search) return;
  if (child.location.hash !== target.hash) child.location.replace(target.href);
}
watch(source, synchronizeFrame, { flush: 'post' });

/**
 * 将同源嵌入页的导航写入顶层历史，保证刷新和后退保持当前位置。
 * @param event 当前 iframe 发出的受控路由消息。
 * @return 无返回值。
 */
function navigate(event: MessageEvent): void {
  if (event.origin !== location.origin || event.source !== frame.value?.contentWindow) return;
  const value = event.data;
  if (!value || value.type !== 'runtime:navigate' || typeof value.tab !== 'string') return;
  if (value.tab !== 'environments' && !taskTabs.includes(value.tab)) return;
  const query: Record<string, string> = {};
  if (!['environments', 'accounts'].includes(value.tab)) query.tab = value.tab;
  for (const key of ['account', 'environment', 'gateway_account']) {
    if (typeof value[key] === 'string') query[key] = value[key];
  }
  const target = { name: value.tab === 'environments' ? 'environments' : 'tasks', query };
  void (value.replace === true ? router.replace(target) : router.push(target));
}

/** 建立统一后台会话后再加载环境管理。@return 无返回值。 */
async function connect(): Promise<void> {
  try {
    await api.openRuntime();
    ready.value = true;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '环境管理暂不可用';
  }
}

onMounted(() => { window.addEventListener('message', navigate); void connect(); });
onUnmounted(() => window.removeEventListener('message', navigate));
</script>

<template>
  <div class="flex h-full min-h-0 w-full flex-col">
    <p v-if="error" class="p-4" role="alert">{{ error }}</p>
    <iframe v-if="ready" :key="view" ref="frame" :src="documentSource" :title="route.name === 'environments' ? '账号环境管理' : '任务与运行管理'" class="block min-h-0 w-full flex-1 border-0" @load="synchronizeFrame" />
    <p v-else-if="!error" class="p-4">正在连接环境管理…</p>
  </div>
</template>
