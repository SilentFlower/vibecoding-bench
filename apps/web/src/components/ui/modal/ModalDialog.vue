<script setup lang="ts">
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../dialog';

/**
 * 居中弹窗：标题与说明的头部、可滚动的内容区、通栏浅灰底栏（设计稿 .modal / .mh / .mb / .mf）。
 * 内容区单独滚动，头部与底栏始终可见。
 * @prop title 标题。
 * @prop description 说明；省略时以标题作为读屏描述。description 插槽可放带按钮的说明（如完整 ID 与复制）。
 * @prop width 最大宽度（px），默认 820；窄屏不超过视口宽减 32px（靠右时减 28px）。
 * @prop placement center 居中；side 贴右、上下右各留 14px、占满视口高的抽屉，结构与居中相同。
 * v-model:open 控制打开状态。插槽 media：标题左侧的头像或图标块；title-extra：标题后的徽标；
 * nav：头部下方不随内容滚动的页签带；默认插槽：内容区；footer：底栏。
 */
// 根节点 Dialog 不渲染元素，class、data-* 等属性转给弹窗面板。
defineOptions({ inheritAttrs: false });
const props = withDefaults(defineProps<{ title: string; description?: string; width?: number; placement?: 'center' | 'side' }>(), { width: 820, placement: 'center' });
const open = defineModel<boolean>('open', { default: false });
// 定位工具类位于 utilities 层，组件层规则压不过，靠右摆放须同样用工具类覆盖 DialogContent 的居中定位。
const sideClass = 'top-[14px] right-[14px] left-auto translate-x-0 translate-y-0';
</script>

<template>
  <Dialog v-model:open="open">
    <!-- flex/max-w 工具类覆盖 DialogContent 的 grid 与默认宽度上限；尺寸外观见 kit.css 的 fui-modal。 -->
    <DialogContent v-bind="$attrs" class="fui-modal flex flex-col max-w-none sm:max-w-none" :class="props.placement === 'side' ? sideClass : undefined" :data-placement="props.placement" :style="{ width: `min(${props.width}px, calc(100vw - ${props.placement === 'side' ? 28 : 32}px))` }">
      <header class="fui-modal-head">
        <slot name="media" />
        <div class="fui-modal-heading">
          <DialogTitle class="fui-modal-title">{{ title }}<slot name="title-extra" /></DialogTitle>
          <DialogDescription :class="description || $slots.description ? 'fui-modal-description' : 'sr-only'"><slot name="description">{{ description ?? title }}</slot></DialogDescription>
        </div>
      </header>
      <div v-if="$slots.nav" class="fui-modal-nav"><slot name="nav" /></div>
      <div class="fui-modal-body"><slot /></div>
      <footer v-if="$slots.footer" class="fui-modal-foot"><slot name="footer" /></footer>
    </DialogContent>
  </Dialog>
</template>
