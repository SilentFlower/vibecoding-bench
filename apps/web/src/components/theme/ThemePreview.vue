<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { Fit, Minus, Plus } from '@/components/ui/icon';
import { applyTheme, createTheme, type ThemeScheme, type ThemeSeed } from '@/theme';

/**
 * 主题预览画板：同源 iframe 按 1440×900 渲染真实控制台首页，草稿只写进 iframe 的文档根，
 * 弹层、固定定位与媒体查询都留在画板内。iframe 不接收指针与焦点，指针事件交给画布缩放与平移。
 * @prop seed 草稿种子（响应式，深度变化即重新注入）。
 * @prop scheme 草稿模式解析出的深浅；画板文档根的 data-ui-scheme 与变量都按它写入。
 */
const props = defineProps<{ seed: ThemeSeed; scheme: ThemeScheme }>();

const BOARD_WIDTH = 1440;
const BOARD_HEIGHT = 900;
const MIN_SCALE = 0.1;
const MAX_SCALE = 1.5;
const STEP = 0.1;
const FIT_PADDING = 24;

const canvas = ref<HTMLElement>();
const frame = ref<HTMLIFrameElement>();
const loaded = ref(false);
const dragging = ref(false);
const view = reactive({ scale: 0.5, x: 0, y: 0 });
// 未手动缩放或平移时，画布尺寸变化后重新适应。
let fitted = true;
let drag: { id: number; x: number; y: number } | null = null;
let observer: ResizeObserver | undefined;

const percent = computed(() => `${Math.round(view.scale * 100)}%`);
const transform = computed(() => `translate(${view.x}px, ${view.y}px) scale(${view.scale})`);

/**
 * 把草稿写进 iframe 文档根：深浅标记加整组变量。iframe 自身的 initTheme 先应用了已保存的主题与模式，整组覆盖后不残留；
 * 嵌在画板里时它不跟随系统偏好，深浅只由这里写入。
 * @return 无。
 */
function inject(): void {
  const root = frame.value?.contentDocument?.documentElement;
  if (!root) return;
  root.dataset.uiScheme = props.scheme;
  applyTheme(root, createTheme(props.seed, props.scheme));
}

/** iframe 加载完成：模块脚本已在 load 之前执行，此时注入不会被首页初始化反向覆盖。@return 无。 */
function onFrameLoad(): void {
  loaded.value = true;
  inject();
}

/** 适应画布：整张画板放进画布并居中。@return 无。 */
function fit(): void {
  const element = canvas.value;
  if (!element) return;
  const scale = Math.min((element.clientWidth - FIT_PADDING * 2) / BOARD_WIDTH, (element.clientHeight - FIT_PADDING * 2) / BOARD_HEIGHT);
  view.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
  view.x = (element.clientWidth - BOARD_WIDTH * view.scale) / 2;
  view.y = (element.clientHeight - BOARD_HEIGHT * view.scale) / 2;
  fitted = true;
}

/**
 * 以画布内一点为锚缩放：锚点下的画板内容保持不动。
 * @param scale 目标比例，超出范围时取边界。
 * @param anchorX 锚点相对画布左边的距离。
 * @param anchorY 锚点相对画布上边的距离。
 * @return 无。
 */
function zoomAt(scale: number, anchorX: number, anchorY: number): void {
  const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.round(scale * 100) / 100));
  view.x = anchorX - (anchorX - view.x) * next / view.scale;
  view.y = anchorY - (anchorY - view.y) * next / view.scale;
  view.scale = next;
  fitted = false;
}

/** 按钮缩放，以画布中心为锚。@param delta 比例增量。@return 无。 */
function zoomBy(delta: number): void {
  const element = canvas.value;
  if (element) zoomAt(view.scale + delta, element.clientWidth / 2, element.clientHeight / 2);
}

/** 滚轮缩放，以指针为锚；标准鼠标每格约 100 像素即 10 个百分点，触控板小增量随之平滑。@param event 滚轮事件。@return 无。 */
function onWheel(event: WheelEvent): void {
  const element = canvas.value;
  if (!element) return;
  const rect = element.getBoundingClientRect();
  const pixels = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? event.deltaY * 33 : event.deltaY;
  zoomAt(view.scale - pixels / 1000, event.clientX - rect.left, event.clientY - rect.top);
}

/** 主键按下开始平移，并捕获指针以便拖出画布后继续跟随。@param event 指针事件。@return 无。 */
function onPointerDown(event: PointerEvent): void {
  if (event.button !== 0) return;
  drag = { id: event.pointerId, x: event.clientX - view.x, y: event.clientY - view.y };
  dragging.value = true;
  canvas.value?.setPointerCapture(event.pointerId);
}

/** 平移画板。@param event 指针事件。@return 无。 */
function onPointerMove(event: PointerEvent): void {
  if (drag?.id !== event.pointerId) return;
  view.x = event.clientX - drag.x;
  view.y = event.clientY - drag.y;
  fitted = false;
}

/** 结束平移。@param event 指针事件。@return 无。 */
function onPointerEnd(event: PointerEvent): void {
  if (drag?.id !== event.pointerId) return;
  drag = null;
  dragging.value = false;
}

watch(() => [props.seed, props.scheme], inject, { deep: true });
onMounted(() => {
  fit();
  observer = new ResizeObserver(() => { if (fitted) fit(); });
  if (canvas.value) observer.observe(canvas.value);
});
onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <section class="fui-card theme-preview" aria-labelledby="theme-preview-title">
    <header class="theme-preview-head">
      <div>
        <h2 id="theme-preview-title">实时预览</h2>
        <p>草稿在隔离画板中渲染，保存前不影响控制台。</p>
      </div>
      <div class="theme-zoom" role="group" aria-label="画板缩放">
        <button type="button" aria-label="缩小" title="缩小" :disabled="view.scale <= MIN_SCALE" @click="zoomBy(-STEP)"><Minus :size="14" /></button>
        <output aria-live="polite" data-theme-zoom>{{ percent }}</output>
        <button type="button" aria-label="放大" title="放大" :disabled="view.scale >= MAX_SCALE" @click="zoomBy(STEP)"><Plus :size="14" /></button>
        <button type="button" aria-label="适应画布" title="适应画布" @click="fit"><Fit :size="14" /></button>
      </div>
    </header>
    <div ref="canvas" class="theme-canvas" :class="{ 'is-dragging': dragging }" @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerEnd" @pointercancel="onPointerEnd" @wheel.prevent="onWheel">
      <div class="theme-artboard" :style="{ transform }">
        <iframe ref="frame" src="/?theme-preview=1" title="主题预览画板" tabindex="-1" inert @load="onFrameLoad" />
      </div>
      <p v-if="!loaded" class="theme-canvas-loading">正在载入控制台首页…</p>
      <span class="theme-canvas-hint">拖动画布平移 · 滚轮缩放</span>
    </div>
  </section>
</template>
