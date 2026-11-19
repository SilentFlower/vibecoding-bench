<script setup lang="ts">
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../dialog';

/**
 * 居中弹窗：标题与说明的头部、可滚动的内容区、通栏浅灰底栏（设计稿 .modal / .mh / .mb / .mf）。
 * 内容区单独滚动，头部与底栏始终可见。
 * @prop title 标题。
 * @prop description 说明；省略时以标题作为读屏描述。
 * @prop width 最大宽度（px），默认 820；窄屏不超过视口宽减 32px。
 * v-model:open 控制打开状态。插槽 media：标题左侧的头像或图标块；title-extra：标题后的徽标；默认插槽：内容区；footer：底栏。
 */
// 根节点 Dialog 不渲染元素，class、data-* 等属性转给弹窗面板。
defineOptions({ inheritAttrs: false });
const props = withDefaults(defineProps<{ title: string; description?: string; width?: number }>(), { width: 820 });
const open = defineModel<boolean>('open', { default: false });
</script>

<template>
  <Dialog v-model:open="open">
    <!-- flex/max-w 工具类覆盖 DialogContent 的 grid 与默认宽度上限；尺寸外观见 kit.css 的 fui-modal。 -->
    <DialogContent v-bind="$attrs" class="fui-modal flex flex-col max-w-none sm:max-w-none" :style="{ width: `min(${props.width}px, calc(100vw - 32px))` }">
      <header class="fui-modal-head">
        <slot name="media" />
        <div class="fui-modal-heading">
          <DialogTitle class="fui-modal-title">{{ title }}<slot name="title-extra" /></DialogTitle>
          <DialogDescription :class="description ? 'fui-modal-description' : 'sr-only'">{{ description ?? title }}</DialogDescription>
        </div>
      </header>
      <div class="fui-modal-body"><slot /></div>
      <footer v-if="$slots.footer" class="fui-modal-foot"><slot name="footer" /></footer>
    </DialogContent>
  </Dialog>
</template>
